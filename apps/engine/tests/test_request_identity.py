"""`X-User-ID`: the web tier's session, turned into an actor the audit log can name.

The engine still authenticates nobody. What changed is that the Next.js application in front of it
holds a Better Auth session and forwards the signed-in user's id on every call it proxies, so an
audit row can say *who* instead of `anonymous`. These tests pin the four things that have to hold
for that to be worth anything.

**The header reaches the record.** A solve writes the id onto the `CREATED` event and onto
`proposals.created_by`; a read writes it onto `VIEWED`; a batch upload writes it onto
`batch_jobs.created_by`.

**No header is still a valid request.** `curl`, `/docs` and this suite call the API with no session
at all, and they must keep working — attribution is a recording, not an authorisation gate. What
they get is the conspicuous `anonymous`, never a plausible-looking name.

**A hostile value cannot forge a log line.** The header is a string that anyone reaching the engine
directly controls, so an embedded newline must not be able to write a second entry into a log, and
an over-long value must not reach a `String(256)` column at its full length.

**It stays out of the published contract.** `X-User-ID` is transport between two of our own tiers.
If it ever appeared in the OpenAPI document it would become part of the contract the frontend
generates its types from, and `app/api/identity.py` takes a `Request` rather than declaring a
`Header` parameter precisely to prevent that. The assertion is here because the reason is easy to
forget and the regression is silent.

The events are read back through `POST /proposals/{id}/export`, which serves the whole log as part
of the export document — the only place the audit rows are exposed over HTTP, and the same view a
Rechnungsprüfer would be handed.

See `app/api/identity.py` for why the header is recorded but deliberately not trusted, and why only
the opaque id travels rather than the user's name or address.
"""

from __future__ import annotations

from sqlalchemy import select

from app.api.identity import MAX_ACTOR_LENGTH, USER_ID_HEADER, _sanitise
from app.db.models import BatchJobRecord, ProposalRecord
from app.services.batch_audit import BatchAuditService
from app.services.proposal_store import ANONYMOUS_ACTOR, SYSTEM_ACTOR, ProposalStore
from tests.factories import make_proposal

#: A Better Auth id — 32 characters of its own alphabet. Opaque on purpose: nothing in the engine
#: parses it, and a test that used an email here would assert a shape the header does not have.
USER_ID = "kQ7fX2mNp4LrT8vB6cD1sW9yZ0aE3hJu"


def _audit_log(client, proposal_id: str) -> list[dict]:
    """Every event on one proposal, read back the only way HTTP exposes them: the export document."""
    approved = client.post(
        f"/api/v1/proposals/{proposal_id}/approve", json={"approved_by": "Dr. Beispiel"}
    )
    assert approved.status_code == 200, approved.text
    exported = client.post(
        f"/api/v1/proposals/{proposal_id}/export", json={"exported_by": "Dr. Beispiel"}
    )
    assert exported.status_code == 200, exported.text
    return exported.json()["audit_events"]


def _actor_of(events: list[dict], event_type: str) -> str:
    return next(event for event in events if event["event_type"] == event_type)["actor"]


# ==========================================================================================
# the header reaches the record
# ==========================================================================================


def test_a_solve_records_the_forwarded_user_on_its_created_event(client):
    solved = client.post(
        "/api/v1/solve", json={"extraction": {}}, headers={USER_ID_HEADER: USER_ID}
    )
    assert solved.status_code == 200, solved.text

    events = _audit_log(client, solved.json()["proposal_id"])

    assert _actor_of(events, "CREATED") == USER_ID


def test_a_read_records_the_forwarded_user_as_the_viewer(client):
    proposal_id = client.post("/api/v1/solve", json={"extraction": {}}).json()["proposal_id"]

    client.get(f"/api/v1/proposals/{proposal_id}", headers={USER_ID_HEADER: USER_ID})

    assert _actor_of(_audit_log(client, proposal_id), "VIEWED") == USER_ID


async def test_a_created_proposal_carries_the_actor_in_a_queryable_column(database):
    """`created_by`, not only the `CREATED` event.

    "Every draft this user produced" is a filter on the proposals table; answering it by scanning an
    append-only log would be the wrong shape for the one query a data-subject request asks.
    """
    store = ProposalStore(database)

    created = await store.create_proposal(make_proposal(), actor=USER_ID)

    async with database.session() as session:
        statement = select(ProposalRecord.created_by).where(
            ProposalRecord.proposal_id == created.proposal_id
        )
        assert (await session.execute(statement)).scalar_one() == USER_ID


async def test_a_batch_job_carries_the_actor_that_uploaded_it(database):
    service = BatchAuditService(database=database)

    accepted, _ = await service.create_batch([("one_padx.xml", b"<x/>")], actor=USER_ID)

    async with database.session() as session:
        statement = select(BatchJobRecord.created_by).where(
            BatchJobRecord.batch_id == accepted.batch_id
        )
        assert (await session.execute(statement)).scalar_one() == USER_ID


# ==========================================================================================
# no header is still a valid request
# ==========================================================================================


def test_a_call_with_no_session_is_accepted_and_recorded_as_anonymous(client):
    """The suite itself is the caller this protects: attribution is a recording, not a gate."""
    solved = client.post("/api/v1/solve", json={"extraction": {}})
    assert solved.status_code == 200, solved.text

    events = _audit_log(client, solved.json()["proposal_id"])

    # `anonymous`, not `system`: a solve that arrived over HTTP had a caller, and the honest record
    # is that we do not know who they were — not that the engine did this to itself.
    assert _actor_of(events, "CREATED") == ANONYMOUS_ACTOR


async def test_the_store_still_defaults_to_system_when_nothing_names_an_actor(database):
    """The default belongs to the store, and it is `system` — a `CREATED` row written by code that
    no request reached, such as a future backfill, is not the same claim as `anonymous`."""
    store = ProposalStore(database)

    created = await store.create_proposal(make_proposal())

    events = await store.audit_events(created.proposal_id)
    assert events[0]["actor"] == SYSTEM_ACTOR


def test_an_empty_header_is_anonymous_rather_than_an_empty_actor():
    """An unattributed row must be visibly unattributed. `""` would look like a missing column."""
    assert _sanitise(None) == ANONYMOUS_ACTOR
    assert _sanitise("") == ANONYMOUS_ACTOR
    assert _sanitise("   ") == ANONYMOUS_ACTOR


# ==========================================================================================
# a hostile value cannot forge a log line
# ==========================================================================================


def test_control_characters_are_stripped_so_a_header_cannot_write_a_second_log_line():
    forged = "alice\nWARNING  proposal approved by chief physician"

    cleaned = _sanitise(forged)

    assert "\n" not in cleaned
    assert cleaned == "aliceWARNING  proposal approved by chief physician"


def test_an_over_long_value_is_truncated_to_the_column_width():
    """`actor` and both `created_by` columns are `String(256)`. Postgres raises on a longer value;
    SQLite stores it whole, and the two backends then disagree about what the log says."""
    assert len(_sanitise("u" * (MAX_ACTOR_LENGTH * 3))) == MAX_ACTOR_LENGTH


# ==========================================================================================
# it stays out of the published contract
# ==========================================================================================


def test_the_identity_header_is_absent_from_the_openapi_document(client):
    document = client.get("/openapi.json")
    assert document.status_code == 200

    assert USER_ID_HEADER not in document.text.lower(), (
        "X-User-ID leaked into the OpenAPI document. It is transport between the web tier and the "
        "engine, not part of the contract @workspace/contracts generates types from — declare it "
        "with a Request dependency, never as a Header parameter."
    )
