"""The audit log: what it records, and that it cannot be rewritten.

An audit log is only worth having if two things hold. Every state change writes exactly one event,
in the same transaction as the change — otherwise the log and the record can disagree, and neither
can be trusted. And nothing can edit or remove an event afterwards — otherwise the log says whatever
the last person to touch it wanted it to say.

Both are tested here: the first by driving the store and the API and reading the log back, the second
by trying to mutate a stored event and asserting it is refused. The refusal is enforced by the ORM
(`app/db/models.py::_reject_mutation`), which is the half this service can enforce; the other half is
`REVOKE UPDATE, DELETE` for the application role, which belongs to the deployment's grants and is
documented in the migration.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import AuditEvent, AuditEventType, AuditLogIsAppendOnly, ProposalRecord
from app.services.proposal_store import ANONYMOUS_ACTOR, SYSTEM_ACTOR, ProposalStore
from tests.conftest import solve_proposal
from tests.factories import make_proposal

# ==========================================================================================
# what gets recorded
# ==========================================================================================


async def test_creating_a_proposal_writes_exactly_one_created_event(store):
    created = await store.create_proposal(make_proposal(case_id="ENC-audit"))

    events = await store.audit_events(created.proposal_id)

    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "CREATED"
    assert event["actor"] == SYSTEM_ACTOR, "a solve is not a person"
    assert event["proposal_id"] == created.proposal_id
    assert event["metadata"]["receipt_hash"] == created.receipt_hash
    assert event["metadata"]["case_id"] == "ENC-audit"
    assert event["timestamp"] is not None


async def test_approval_records_the_approver_as_the_actor(store):
    created = await store.create_proposal(make_proposal())

    await store.approve_proposal(
        created.proposal_id, approved_by="Dr. Beispiel", note="Befund liegt vor"
    )
    events = await store.audit_events(created.proposal_id)

    approval = events[-1]
    assert approval["event_type"] == "APPROVED"
    assert approval["actor"] == "Dr. Beispiel", (
        "the actor is the whole point: an approval nobody signed is not an approval"
    )
    assert approval["metadata"]["from_status"] == "DRAFT"
    assert approval["metadata"]["note"] == "Befund liegt vor"


async def test_the_note_is_omitted_rather_than_stored_empty(store):
    """An absent optional field, not a field present and blank.

    `metadata_json` is context a reader interprets; `{"note": ""}` reads as "a note was left and it
    was empty", which is not what happened.
    """
    created = await store.create_proposal(make_proposal())
    await store.approve_proposal(created.proposal_id, approved_by="Dr. B")

    approval = (await store.audit_events(created.proposal_id))[-1]
    assert "note" not in approval["metadata"]


async def test_the_log_is_ordered_and_complete_across_a_whole_lifecycle(store):
    """One proposal, every legal transition, in order — plus the read that happened between them."""
    created = await store.create_proposal(make_proposal())
    await store.get_proposal(created.proposal_id, record_view=True, actor="Dr. Leser")
    await store.approve_proposal(created.proposal_id, approved_by="Dr. Beispiel")
    await store.export_proposal(created.proposal_id, actor="pvs-export")

    events = await store.audit_events(created.proposal_id)

    assert [e["event_type"] for e in events] == ["CREATED", "VIEWED", "APPROVED", "EXPORTED"]
    assert [e["actor"] for e in events] == [
        SYSTEM_ACTOR,
        "Dr. Leser",
        "Dr. Beispiel",
        "pvs-export",
    ]
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps), "the log must read in the order things happened"


async def test_a_read_writes_a_viewed_event_only_when_asked(store):
    """`record_view` is opt-in, so an approval does not leave a VIEWED row in front of itself.

    Every transition reads the row first. If that read logged, the log would be half noise and the
    APPROVED event — which already proves somebody looked — would be harder to find.
    """
    created = await store.create_proposal(make_proposal())

    await store.get_proposal(created.proposal_id)
    assert [e["event_type"] for e in await store.audit_events(created.proposal_id)] == ["CREATED"]

    await store.get_proposal(created.proposal_id, record_view=True)
    assert [e["event_type"] for e in await store.audit_events(created.proposal_id)] == [
        "CREATED",
        "VIEWED",
    ]

    await store.approve_proposal(created.proposal_id, approved_by="Dr. B")
    assert [e["event_type"] for e in await store.audit_events(created.proposal_id)] == [
        "CREATED",
        "VIEWED",
        "APPROVED",
    ]


async def test_an_event_is_never_written_without_an_actor(store):
    """An unattributed audit row is indistinguishable from a missing one."""
    created = await store.create_proposal(make_proposal())

    # An empty actor is possible only where the caller does not have to name one: a read (nothing
    # authenticates it) and an export (a system action). `approve` and `reject` refuse an empty
    # name outright rather than substituting one — see test_db_persistence.py.
    await store.get_proposal(created.proposal_id, record_view=True, actor="")
    await store.approve_proposal(created.proposal_id, approved_by="Dr. Beispiel")
    await store.export_proposal(created.proposal_id, actor="")

    events = await store.audit_events(created.proposal_id)
    assert all(e["actor"] for e in events), "no event may carry an empty actor"
    assert [e["actor"] for e in events] == [
        SYSTEM_ACTOR,
        SYSTEM_ACTOR,
        "Dr. Beispiel",
        SYSTEM_ACTOR,
    ], "an empty actor falls back to the system identity rather than being stored blank"


async def test_events_belong_to_their_own_proposal_only(store):
    left = await store.create_proposal(make_proposal())
    right = await store.create_proposal(make_proposal())

    await store.approve_proposal(left.proposal_id, approved_by="Dr. Links")
    await store.reject_proposal(right.proposal_id, rejected_by="Dr. Rechts", reason="nein")

    left_events = await store.audit_events(left.proposal_id)
    right_events = await store.audit_events(right.proposal_id)

    assert [e["event_type"] for e in left_events] == ["CREATED", "APPROVED"]
    assert [e["event_type"] for e in right_events] == ["CREATED", "REJECTED"]
    assert {e["id"] for e in left_events}.isdisjoint({e["id"] for e in right_events})


# ==========================================================================================
# append-only
# ==========================================================================================


async def test_an_audit_event_cannot_be_modified(database, store):
    """The ORM refuses the UPDATE. A "correction" has to be a new event, which is the point."""
    created = await store.create_proposal(make_proposal())
    await store.approve_proposal(created.proposal_id, approved_by="Dr. Beispiel")

    with pytest.raises(AuditLogIsAppendOnly, match="append-only"):
        async with database.session() as session:
            event = (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.event_type == "APPROVED")
                )
            ).scalar_one()
            event.actor = "Somebody Else"
            await session.flush()

    surviving = await store.audit_events(created.proposal_id)
    assert [e["actor"] for e in surviving] == [SYSTEM_ACTOR, "Dr. Beispiel"], (
        "the refused update must have rolled back, not half-applied"
    )


async def test_an_audit_event_cannot_be_deleted(database, store):
    created = await store.create_proposal(make_proposal())

    with pytest.raises(AuditLogIsAppendOnly, match="append-only"):
        async with database.session() as session:
            event = (await session.execute(select(AuditEvent))).scalar_one()
            await session.delete(event)
            await session.flush()

    assert len(await store.audit_events(created.proposal_id)) == 1


async def test_the_stored_result_and_receipt_are_never_rewritten_by_a_decision(database, store):
    """Approving must not touch a single column that identifies the result.

    This is what makes "this receipt hash is what was approved" checkable: the identity columns and
    the solver output are written once and the decision only ever adds to the lifecycle columns.
    """
    created = await store.create_proposal(make_proposal())

    async def snapshot() -> dict:
        async with database.session() as session:
            record = (
                await session.execute(
                    select(ProposalRecord).where(
                        ProposalRecord.proposal_id == created.proposal_id
                    )
                )
            ).scalar_one()
            return {
                "receipt_hash": record.receipt_hash,
                "input_hash": record.input_hash,
                "catalog_version": record.catalog_version,
                "catalog_sha256": record.catalog_sha256,
                "rules_hash": record.rules_hash,
                "logic_version": record.logic_version,
                "solver_version": record.solver_version,
                "solver_result_json": record.solver_result_json,
                "rule_coverage_json": record.rule_coverage_json,
                "created_at": record.created_at,
            }

    before = await snapshot()
    await store.approve_proposal(created.proposal_id, approved_by="Dr. Beispiel")
    await store.export_proposal(created.proposal_id)

    assert await snapshot() == before


# ==========================================================================================
# through HTTP — the log the API actually produces
# ==========================================================================================


async def test_the_api_writes_the_audit_trail_for_a_real_solve(client, manual_case):
    """End to end: solve, read, approve, export — and check the log the endpoints left behind.

    Driven through `client`, so it exercises the store the app built rather than a test-owned one.
    """
    draft = solve_proposal(client, manual_case("case_001_knee"), case_id="ENC-http")
    proposal_id = draft["proposal_id"]

    assert client.get(f"/api/v1/proposals/{proposal_id}").status_code == 200
    assert (
        client.post(
            f"/api/v1/proposals/{proposal_id}/approve",
            json={"approved_by": "Dr. Beispiel", "note": "geprüft"},
        ).status_code
        == 200
    )
    exported = client.post(
        f"/api/v1/proposals/{proposal_id}/export", json={"exported_by": "PVS-Anbindung"}
    )
    assert exported.status_code == 200, exported.text

    from app.api import deps

    events = await deps.proposals().audit_events(proposal_id)

    assert [e["event_type"] for e in events] == ["CREATED", "VIEWED", "APPROVED", "EXPORTED"]
    assert events[0]["metadata"]["case_id"] == "ENC-http"
    assert events[1]["actor"] == ANONYMOUS_ACTOR, (
        "the service authenticates nobody, and the log must say so rather than invent a name"
    )
    assert events[2]["actor"] == "Dr. Beispiel"
    assert events[2]["metadata"]["note"] == "geprüft"
    # The export is attributed too: `exported_by` is required by the endpoint and is what the
    # EXPORTED row records. An export nobody is named for cannot be accounted for later.
    assert events[3]["actor"] == "PVS-Anbindung"


async def test_a_rejection_through_the_api_records_the_rejecter_not_just_the_reason(
    client, manual_case
):
    """`rejected_by` used to be accepted by the schema and then dropped on the floor.

    The old in-memory `transition()` took `reason` but never `by` for a rejection, so the API
    validated a required `rejected_by` and discarded it — the one field that makes a rejection
    attributable. It is now the audit event's actor.
    """
    draft = solve_proposal(client, manual_case("case_001_knee"))
    proposal_id = draft["proposal_id"]

    response = client.post(
        f"/api/v1/proposals/{proposal_id}/reject",
        json={"rejected_by": "Dr. Streng", "reason": "Sonographie nicht dokumentiert"},
    )
    assert response.status_code == 200
    assert response.json()["rejected_reason"] == "Sonographie nicht dokumentiert"

    from app.api import deps

    rejection = (await deps.proposals().audit_events(proposal_id))[-1]
    assert rejection["event_type"] == "REJECTED"
    assert rejection["actor"] == "Dr. Streng"
    assert rejection["metadata"]["reason"] == "Sonographie nicht dokumentiert"


async def test_approving_a_rejected_proposal_is_409_through_the_api(client, manual_case):
    """The illegal transition the brief names, at the HTTP boundary."""
    draft = solve_proposal(client, manual_case("case_001_knee"))
    proposal_id = draft["proposal_id"]

    client.post(
        f"/api/v1/proposals/{proposal_id}/reject",
        json={"rejected_by": "Dr. Streng", "reason": "nicht dokumentiert"},
    )
    conflict = client.post(
        f"/api/v1/proposals/{proposal_id}/approve", json={"approved_by": "Dr. Optimist"}
    )

    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["error"] == "illegal_transition"
    assert detail["current_status"] == "REJECTED"
    assert detail["requested_status"] == "APPROVED"

    unchanged = client.get(f"/api/v1/proposals/{proposal_id}").json()
    assert unchanged["status"] == "REJECTED"
    assert unchanged["approved_by"] is None

    from app.api import deps

    events = await deps.proposals().audit_events(proposal_id)
    assert "APPROVED" not in [e["event_type"] for e in events]


async def test_an_approval_is_still_there_after_the_store_is_rebuilt(client, manual_case):
    """A restart of the *application* layer, short of restarting the database.

    `deps.reset()` throws away the store singleton — which is what a worker restart does to it. The
    approval is read back through a store built from scratch, so nothing in the assertion can be
    coming from an in-process cache.
    """
    draft = solve_proposal(client, manual_case("case_001_knee"))
    proposal_id = draft["proposal_id"]
    client.post(
        f"/api/v1/proposals/{proposal_id}/approve", json={"approved_by": "Dr. Beispiel"}
    )

    from app.api import deps
    from app.db.session import get_database

    deps.reset()
    rebuilt = ProposalStore(get_database())
    reloaded = await rebuilt.get_proposal(proposal_id)

    assert reloaded.status.value == "APPROVED"
    assert reloaded.approved_by == "Dr. Beispiel"
    assert [e["event_type"] for e in await rebuilt.audit_events(proposal_id)] == [
        "CREATED",
        "APPROVED",
    ]


def test_every_transition_has_an_audit_event_type():
    """A new transition cannot be added without deciding what it records."""
    from app.services.proposal_store import ALLOWED, EVENT_FOR_STATUS

    reachable = {target for targets in ALLOWED.values() for target in targets}
    assert reachable <= set(EVENT_FOR_STATUS), (
        f"no audit event type for: {sorted(str(s) for s in reachable - set(EVENT_FOR_STATUS))}"
    )
    assert set(EVENT_FOR_STATUS.values()) <= set(AuditEventType)
