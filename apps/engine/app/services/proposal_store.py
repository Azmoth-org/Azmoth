"""Where proposals live between being produced and being approved.

**This used to be a dictionary, and the module argued for it.** The argument was that inventing a
schema would mean inventing the retention policy, the access control and the audit log with it, and
that all three are legal questions before they are engineering ones. Half of that was right and half
of it was backwards. The audit log is not a reason to postpone a database — it is the thing a
database is for, and an approval that dies with the process cannot answer the one question a billing
system must always be able to answer: *who accepted this, and when.* So the record is now durable and
the log is now written; retention and access control remain open, and are tracked as open in
`docs/compliance/PRIVATE_DATA_WARNING.md` rather than used as a reason not to persist anything.

What this layer is responsible for:

* **Nothing above it holds a session.** Every method opens one unit of work, converts rows into
  Pydantic models *inside* it, and returns those. No ORM object escapes, so no lazy load can fire
  from a closed session — which under an async driver surfaces as `MissingGreenlet` in production
  and nowhere else.
* **The lifecycle is enforced here, not in the router.** `ALLOWED` is the whole state machine, the
  row is locked before it is read (`SELECT … FOR UPDATE`, a no-op on SQLite), and the check and the
  write happen in one transaction. Two simultaneous approvals cannot both win.
* **Every decision writes an audit row in the same transaction as the decision.** Not afterwards and
  not in a background task: a status that changed without a matching event, or an event without the
  status change, would each be a record nobody can defend.
* **An export is built inside the transaction that records it.** `export_proposal_document` marks
  the row `EXPORTED`, writes the audit event and assembles the downloadable document from that same
  row, before the commit. Reading the row back afterwards would be simpler and subtly wrong in two
  ways: the file could disagree with the record it claims to be, and a read that failed after a
  successful transition would leave a proposal permanently `EXPORTED` with no file ever delivered —
  unrecoverable, because `EXPORTED` is terminal.

What it deliberately does not do: delete. There is no `delete_proposal` and no eviction. The old
dictionary dropped its oldest entry past 512 to bound memory; a durable store that silently discarded
approvals would be worse than one that ran out of disk, because only one of those is noticed.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.canonical import sha256_of
from app.db.models import AuditEvent, AuditEventType, ProposalRecord, as_utc, utcnow
from app.db.retry import retry_database
from app.db.session import Database, get_database
from app.schemas import Proposal, ProposalList, ProposalStatus, RuleCoverage
from app.schemas.export import ProposalExport
from app.services.export import build_proposal_export

#: What a transition's projector returns. See `_transition`.
T = TypeVar("T")

log = logging.getLogger(__name__)

#: The actor recorded for an action no authenticated identity was attached to.
#:
#: There is no authentication in this service, so a read cannot be attributed and this is what a
#: `VIEWED` event carries. It is a deliberately conspicuous value: an audit log full of
#: `anonymous` is a visible statement that access control is still missing, which is exactly the
#: gap `docs/compliance/PRIVATE_DATA_WARNING.md` lists. Writing a plausible-looking name here
#: instead would be the one genuinely dangerous option.
ANONYMOUS_ACTOR = "anonymous"

#: The actor for events the engine itself causes — a `CREATED` row follows a solve, not a person.
SYSTEM_ACTOR = "system"

#: Default and maximum page size for `GET /proposals`.
#:
#: The ceiling is 100 rather than the 500 the batch listing started with, and it is lower for a
#: reason that is specific to this table: a listing row is a whole `Proposal`, `solver_result` and
#: proof trees included, so a page here is one to two orders of magnitude larger per row than a
#: batch header. `total` travels in the response, so a page never hides how many proposals exist.
DEFAULT_PROPOSAL_LIST_LIMIT = 50
MAX_PROPOSAL_LIST_LIMIT = 100


class ProposalNotFound(KeyError):
    def __init__(self, proposal_id: str) -> None:
        super().__init__(proposal_id)
        self.proposal_id = proposal_id


class IllegalTransitionError(RuntimeError):
    """A status change the lifecycle does not allow. Refused, never silently applied."""

    def __init__(self, current: ProposalStatus, requested: ProposalStatus) -> None:
        super().__init__(
            f"A proposal in status {current} cannot become {requested}. "
            f"Allowed from {current}: {', '.join(str(s) for s in ALLOWED[current]) or 'nothing'}."
        )
        self.current = current
        self.requested = requested


#: Kept under its original name because `tests/` and any external caller import it. The `…Error`
#: spelling is the one the class now carries; both names are the same object, so `except
#: IllegalTransition` still catches it.
IllegalTransition = IllegalTransitionError


#: DRAFT is the only state a decision can be made in, and an APPROVED proposal can only go on to
#: be EXPORTED. A REJECTED or EXPORTED proposal is terminal: re-deciding one would mean the
#: approval record no longer describes what was billed.
ALLOWED: dict[ProposalStatus, tuple[ProposalStatus, ...]] = {
    ProposalStatus.DRAFT: (ProposalStatus.APPROVED, ProposalStatus.REJECTED),
    ProposalStatus.APPROVED: (ProposalStatus.EXPORTED,),
    ProposalStatus.REJECTED: (),
    ProposalStatus.EXPORTED: (),
}

#: Which audit event a transition writes. Derived from the target status rather than passed in, so
#: a new transition cannot be added without deciding what it records.
EVENT_FOR_STATUS: dict[ProposalStatus, AuditEventType] = {
    ProposalStatus.APPROVED: AuditEventType.APPROVED,
    ProposalStatus.REJECTED: AuditEventType.REJECTED,
    ProposalStatus.EXPORTED: AuditEventType.EXPORTED,
}


def input_hash_of(proposal: Proposal) -> str:
    """SHA-256 over the canonical clinical input alone.

    Computed here rather than threaded through the pipeline because it is a property of the stored
    record, not of the response — adding it to the `Proposal` schema would change the API contract
    for a value no client asked for.

    It is the same digest the receipt hash takes over its `facts` component (`canonical()` of the
    extraction), which is what makes the pair useful together: two rows with one `input_hash` and
    two `receipt_hash` values are the same case coded by two different engine states. Nothing about
    the receipt's own computation is touched — see `app/services/receipt.py`.
    """
    return sha256_of(proposal.solver_result.extraction)


def _to_record(proposal: Proposal) -> ProposalRecord:
    """Pydantic → row. Called once, by `create_proposal`; everything after that is an UPDATE."""
    return ProposalRecord(
        proposal_id=proposal.proposal_id,
        case_id=proposal.case_id,
        status=str(proposal.status),
        receipt_hash=proposal.receipt_hash,
        input_hash=input_hash_of(proposal),
        catalog_version=proposal.catalog_version,
        catalog_sha256=proposal.catalog_sha256,
        rules_version=proposal.rules_version,
        rules_hash=proposal.rules_hash,
        logic_version=proposal.logic_version,
        solver_version=proposal.solver_version,
        rules_engine_version=proposal.rules_engine_version,
        solver_result_json=proposal.solver_result.model_dump(mode="json"),
        warnings_json=[w.model_dump(mode="json") for w in proposal.warnings],
        missing_documentation_json=[
            m.model_dump(mode="json") for m in proposal.missing_documentation
        ],
        rule_coverage_json=(
            proposal.rule_coverage.model_dump(mode="json") if proposal.rule_coverage else None
        ),
        cached=proposal.cached,
        created_at=proposal.created_at,
        approved_at=proposal.approved_at,
        approved_by=proposal.approved_by,
        rejected_reason=proposal.rejected_reason,
    )


def _to_proposal(record: ProposalRecord) -> Proposal:
    """Row → Pydantic, reproducing the response the API served when the proposal was created.

    The five rule-coverage counts, `solver_status` and the two timing metrics are *derived*, not
    stored twice: the counts come out of `rule_coverage_json`, the status and the timings out of
    the solver result's own audit trail.
    Storing them again in their own columns would create two places for one fact, and the API
    flattens them precisely so a client cannot render a proposal without seeing them — a flattened
    copy that disagreed with its source would defeat the point.
    """
    coverage = (
        RuleCoverage.model_validate(record.rule_coverage_json) if record.rule_coverage_json else None
    )
    audit_trail = (record.solver_result_json or {}).get("audit_trail") or {}
    solver_status = audit_trail.get("solver_status", "") or ""

    return Proposal(
        proposal_id=record.proposal_id,
        case_id=record.case_id,
        status=ProposalStatus(record.status),
        created_at=as_utc(record.created_at),
        approved_at=as_utc(record.approved_at),
        approved_by=record.approved_by,
        rejected_reason=record.rejected_reason,
        receipt_hash=record.receipt_hash,
        catalog_version=record.catalog_version,
        catalog_sha256=record.catalog_sha256,
        rules_version=record.rules_version,
        rules_hash=record.rules_hash,
        solver_version=record.solver_version,
        rules_engine_version=record.rules_engine_version,
        logic_version=record.logic_version,
        solver_result=record.solver_result_json,
        warnings=record.warnings_json or [],
        missing_documentation=record.missing_documentation_json or [],
        solver_status=solver_status,
        solver_timed_out=solver_status == "TIMEOUT_PARTIAL",
        # Derived, not stored in their own columns, for the reason above: the audit trail already
        # holds them, and a stored copy that drifted from it would be a second answer to one
        # question. It also means a proposal read back next year still reports what its own run
        # cost, rather than how long the SELECT took.
        solve_time_ms=float(audit_trail.get("solve_time_ms") or 0.0),
        total_time_ms=float(audit_trail.get("total_time_ms") or 0.0),
        enforced_rule_count=coverage.enforced_rule_count if coverage else 0,
        advisory_rule_count=coverage.advisory_rule_count if coverage else 0,
        unverified_rule_count=coverage.unverified_rule_count if coverage else 0,
        analog_candidate_count=coverage.analog_candidate_count if coverage else 0,
        suppressed_unverified_rule_count=(
            coverage.suppressed_unverified_rule_count if coverage else 0
        ),
        rule_coverage=coverage,
        cached=record.cached,
    )


class ProposalStore:
    """The repository. Async because the driver is; no SQL leaks upward.

    Constructed with a `Database` or with none, in which case the process-wide one is used. Passing
    one explicitly is how a test points the store at its own schema without touching global state.
    """

    def __init__(self, database: Database | None = None) -> None:
        self._database = database

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    # -- reads -----------------------------------------------------------------------------

    @retry_database("ProposalStore.get_proposal")
    async def get_proposal(
        self,
        proposal_id: str,
        *,
        record_view: bool = False,
        actor: str = ANONYMOUS_ACTOR,
    ) -> Proposal:
        """One proposal, or `ProposalNotFound`.

        `record_view` is off by default and on for exactly one caller: `GET /proposals/{id}`. Every
        approval and rejection also has to read the row first, and a `VIEWED` row in front of every
        `APPROVED` row would be noise in the log a reviewer actually reads — the approval already
        records that somebody looked.
        """
        async with self.database.session() as session:
            record = await self._require(session, proposal_id)
            if record_view:
                self._add_event(
                    session,
                    record,
                    AuditEventType.VIEWED,
                    actor=actor,
                    metadata={"status": record.status},
                )
            return _to_proposal(record)

    async def list_proposals(
        self,
        *,
        status: ProposalStatus | None = None,
        case_id: str | None = None,
        limit: int = DEFAULT_PROPOSAL_LIST_LIMIT,
        offset: int = 0,
    ) -> ProposalList:
        """One page of proposals, newest first, with the filtered total beside it.

        **The order is now descending, and that is a change.** This method used to select the newest
        `limit` rows and re-sort them ascending, to reproduce what the in-memory store returned.
        That reasoning does not survive paging: with `offset` in the picture, ascending-within-page
        means page 0 runs old→new, page 1 runs old→new over *older* rows, and the sequence a caller
        reads by walking the pages is not sorted at all. A paged listing needs one global order, and
        newest-first is both the useful one for a review queue and the one `GET /padnext/batch`
        already serves.

        `created_at DESC` with `id DESC` as the tie-break. The tie-break is load-bearing rather than
        decorative: `created_at` comes from the application clock (`utcnow`), two proposals written
        in the same microsecond are possible, and an order that could differ between two reads of
        the same rows would make paging skip or repeat one.

        `total` counts everything matching the filters, not the page — the same statement minus the
        window — so `status=DRAFT` reports the whole backlog and not how much of it fitted.

        `case_id` matches **exactly**. A substring search is what a filter box suggests, and it
        would be the wrong trade here: `ix_proposals_case_id` is a plain B-tree, `LIKE '%x%'` cannot
        use it, and making it usable means a trigram index — a schema change, for a column that
        holds the caller's own opaque handle for an encounter rather than prose anybody skims. An
        empty or whitespace-only value is treated as no filter, so a cleared input box does not
        become a search for the empty string.

        Two statements, one session, no N+1: the page is a single `SELECT` and `_to_proposal` reads
        only columns of the row it was handed. `ProposalRecord.events` is lazily loaded and never
        touched here, which is what keeps a page of fifty from also reading fifty audit logs.
        """
        limit = max(1, min(limit, MAX_PROPOSAL_LIST_LIMIT))
        offset = max(0, offset)

        filters = []
        if status is not None:
            filters.append(ProposalRecord.status == str(status))
        if case_id is not None and case_id.strip():
            filters.append(ProposalRecord.case_id == case_id.strip())

        async with self.database.session() as session:
            total = int(
                (
                    await session.execute(
                        select(func.count()).select_from(ProposalRecord).where(*filters)
                    )
                ).scalar_one()
            )

            records = (
                (
                    await session.execute(
                        select(ProposalRecord)
                        .where(*filters)
                        .order_by(
                            ProposalRecord.created_at.desc(),
                            ProposalRecord.id.desc(),
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .scalars()
                .all()
            )

            return ProposalList(
                items=[_to_proposal(record) for record in records],
                total=total,
                limit=limit,
                offset=offset,
            )

    async def audit_events(self, proposal_id: str) -> list[dict[str, Any]]:
        """The append-only log for one proposal, oldest first.

        Returned as plain dicts rather than as ORM rows or a new Pydantic model: this is not on the
        API surface — adding an endpoint for it would change the OpenAPI document — and it exists so
        the suite and an operator can read the log without a SQL client.
        """
        async with self.database.session() as session:
            record = await self._require(session, proposal_id)
            return await self._events_for(session, record)

    @staticmethod
    async def _events_for(
        session: AsyncSession, record: ProposalRecord
    ) -> list[dict[str, Any]]:
        """The log for one proposal, oldest first, read on a session the caller already holds.

        Split out so the export can read the log inside its own transaction — including the
        `EXPORTED` row it just wrote, which a separate session would not see until after the commit.
        """
        statement = (
            select(AuditEvent)
            .where(AuditEvent.proposal_id == record.id)
            .order_by(AuditEvent.timestamp, AuditEvent.id)
        )
        events = (await session.execute(statement)).scalars().all()
        return [
            {
                "id": str(event.id),
                "proposal_id": record.proposal_id,
                "event_type": event.event_type,
                "actor": event.actor,
                "timestamp": as_utc(event.timestamp),
                "metadata": event.metadata_json,
            }
            for event in events
        ]

    async def count(
        self, *, status: ProposalStatus | None = None, case_id: str | None = None
    ) -> int:
        """How many proposals match, ignoring any page. The same filters `list_proposals` applies.

        Kept as a public method even though the listing now reports its own `total`: it is what a
        health check and the suite use to assert on a table without materialising a page of whole
        solver results.
        """
        statement = select(func.count()).select_from(ProposalRecord)
        if status is not None:
            statement = statement.where(ProposalRecord.status == str(status))
        if case_id is not None and case_id.strip():
            statement = statement.where(ProposalRecord.case_id == case_id.strip())
        async with self.database.session() as session:
            return int((await session.execute(statement)).scalar_one())

    # -- writes ----------------------------------------------------------------------------

    @retry_database("ProposalStore.create_proposal")
    async def create_proposal(self, proposal: Proposal, *, actor: str = SYSTEM_ACTOR) -> Proposal:
        """Persist a fresh DRAFT and its `CREATED` event, in one transaction.

        The returned value is read back off the row rather than echoed from the argument, so the
        response a caller gets is the record that was actually written. A serialisation that lost a
        field would then fail the first request instead of the first restart.
        """
        record = _to_record(proposal)
        async with self.database.session() as session:
            session.add(record)
            self._add_event(
                session,
                record,
                AuditEventType.CREATED,
                actor=actor,
                metadata={
                    "receipt_hash": proposal.receipt_hash,
                    "case_id": proposal.case_id,
                    "cached": proposal.cached,
                },
            )
            await session.flush()
            await session.refresh(record)
            return _to_proposal(record)

    async def approve_proposal(
        self, proposal_id: str, *, approved_by: str, note: str = ""
    ) -> Proposal:
        """Accept a DRAFT. `approved_by` is required — an unattributed approval is not one."""
        if not approved_by or not approved_by.strip():
            raise ValueError("approved_by is required: an approval nobody signed is not an approval")
        return await self._transition(
            proposal_id,
            ProposalStatus.APPROVED,
            actor=approved_by.strip(),
            metadata={"note": note} if note else None,
        )

    async def reject_proposal(
        self, proposal_id: str, *, rejected_by: str, reason: str
    ) -> Proposal:
        """Refuse a DRAFT, attributed and with a reason. Terminal."""
        if not rejected_by or not rejected_by.strip():
            raise ValueError("rejected_by is required")
        if not reason or not reason.strip():
            raise ValueError("reason is required: a rejection without one cannot be acted on")
        return await self._transition(
            proposal_id,
            ProposalStatus.REJECTED,
            actor=rejected_by.strip(),
            reason=reason.strip(),
        )

    async def export_proposal(
        self, proposal_id: str, *, actor: str = SYSTEM_ACTOR
    ) -> Proposal:
        """Record that an APPROVED proposal left the system. Only reachable from APPROVED.

        Returns the updated proposal and no document. Kept for callers that only need the status
        change; the endpoint uses `export_proposal_document`, which does the same transition and
        additionally builds the file.
        """
        return await self._transition(
            proposal_id, ProposalStatus.EXPORTED, actor=actor or SYSTEM_ACTOR
        )

    @retry_database("ProposalStore.export_proposal_document")
    async def export_proposal_document(
        self, proposal_id: str, *, exported_by: str, note: str = ""
    ) -> ProposalExport:
        """Mark an APPROVED proposal `EXPORTED` and return the file, from one transaction.

        `exported_by` is required for the same reason `approved_by` is: an export is something a
        person did, and the audit log has to be able to say who. It is recorded, not authenticated
        — there is no login in front of this service.

        The audit events are read *after* the `EXPORTED` row has been flushed and *before* the
        commit, so the document contains the event describing its own creation. That is not a trick
        for its own sake: an exported file whose log stops at `APPROVED` cannot prove it is the
        export it claims to be.
        """
        if not exported_by or not exported_by.strip():
            raise ValueError(
                "exported_by is required: an export nobody is recorded as having taken cannot be "
                "accounted for later"
            )
        actor = exported_by.strip()

        async def project(session: AsyncSession, record: ProposalRecord) -> ProposalExport:
            # `record.exported_at` was set by the transition a few lines up, so the document's
            # timestamp is the one in the row rather than a second `utcnow()` that would differ
            # from it by however long the flush took.
            return build_proposal_export(
                record,
                events=await self._events_for(session, record),
                exported_by=actor,
                exported_at=as_utc(record.exported_at),
            )

        return await self._transition(
            proposal_id,
            ProposalStatus.EXPORTED,
            actor=actor,
            metadata={"note": note.strip()} if note and note.strip() else None,
            project=project,
        )

    # -- internals -------------------------------------------------------------------------

    @retry_database("ProposalStore._transition")
    async def _transition(
        self,
        proposal_id: str,
        to: ProposalStatus,
        *,
        actor: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        project: Callable[[AsyncSession, ProposalRecord], Awaitable[T]] | None = None,
    ) -> T | Proposal:
        """Read-check-write plus the audit row, in one transaction, under a row lock.

        The lock is what makes the check meaningful. Without it, two approvals arriving together
        both read `DRAFT`, both pass, and both write — leaving one proposal with two approvers and
        an audit log that records both as having taken responsibility.

        `project` turns the written row into whatever the caller needs *before* the commit, and
        exists for exactly one caller: the export, which has to produce a document that cannot
        disagree with the record. Everything else takes the default and gets a `Proposal`. It is a
        parameter rather than a second copy of this method because the lifecycle check and the lock
        are the part that must not be duplicated — a second write path that forgot either would be
        a bug nobody notices until two people export the same proposal.
        """
        async with self.database.session() as session:
            record = await self._require(session, proposal_id, for_update=True)
            current = ProposalStatus(record.status)
            if to not in ALLOWED[current]:
                raise IllegalTransitionError(current, to)

            now = utcnow()
            record.status = str(to)
            if to is ProposalStatus.APPROVED:
                record.approved_at = now
                record.approved_by = actor
            elif to is ProposalStatus.REJECTED:
                record.rejected_at = now
                record.rejected_by = actor
                record.rejected_reason = reason
            elif to is ProposalStatus.EXPORTED:
                record.exported_at = now

            # Always the status it came from — the log has to say what was re-decided, not only
            # what it became. The reason and any note are folded in when present, and omitted
            # rather than stored empty: `{"note": ""}` reads as "a note was left and it was blank".
            context: dict[str, Any] = {"from_status": str(current)}
            if reason:
                context["reason"] = reason
            context.update(metadata or {})

            self._add_event(
                session,
                record,
                EVENT_FOR_STATUS[to],
                actor=actor,
                timestamp=now,
                metadata=context,
            )
            await session.flush()
            log.info("proposal %s %s by %s", proposal_id, to, actor)
            if project is not None:
                return await project(session, record)
            return _to_proposal(record)

    async def _require(
        self, session: AsyncSession, proposal_id: str, *, for_update: bool = False
    ) -> ProposalRecord:
        statement = select(ProposalRecord).where(ProposalRecord.proposal_id == proposal_id)
        if for_update:
            # Emitted as `FOR UPDATE` on Postgres and omitted by the SQLite dialect, which has no
            # row locks and does not need them: one writer at a time is a property of the file.
            statement = statement.with_for_update()
        record = (await session.execute(statement)).scalar_one_or_none()
        if record is None:
            raise ProposalNotFound(proposal_id)
        return record

    @staticmethod
    def _add_event(
        session: AsyncSession,
        record: ProposalRecord,
        event_type: AuditEventType,
        *,
        actor: str,
        timestamp: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Append one event to the same session — and therefore the same commit — as the change.

        `session.add` rather than `record.events.append`: the relationship is `selectin`-loaded, and
        appending would trigger a load of every prior event on a row whose log only grows. Attaching
        the event to the parent object is what makes the FK resolve without a flush order problem.
        """
        event = AuditEvent(
            proposal=record,
            event_type=str(event_type),
            actor=actor or SYSTEM_ACTOR,
            timestamp=timestamp or utcnow(),
            metadata_json=metadata or None,
        )
        session.add(event)
        return event


__all__ = [
    "ALLOWED",
    "ANONYMOUS_ACTOR",
    "DEFAULT_PROPOSAL_LIST_LIMIT",
    "EVENT_FOR_STATUS",
    "MAX_PROPOSAL_LIST_LIMIT",
    "SYSTEM_ACTOR",
    "IllegalTransition",
    "IllegalTransitionError",
    "ProposalExport",
    "ProposalList",
    "ProposalNotFound",
    "ProposalStore",
    "input_hash_of",
]
