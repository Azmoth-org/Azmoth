"""Two tables: what was proposed, and what happened to it.

`proposals` is mutable in exactly four columns — the status and the decision stamps. Nothing that
identifies the *result* can be updated: the receipt hash, the versions and the solver output are
written once, by `create_proposal`, and never touched again. That is what makes "this receipt is
what was approved" a checkable statement rather than a hopeful one.

`audit_events` is append-only, and that is enforced rather than documented: the ORM refuses an
UPDATE or a DELETE on the mapper (see `_reject_mutation` below), so a mistake in a service has to
become a deliberate raw-SQL statement before it can rewrite history. The database should refuse it
too — a `REVOKE UPDATE, DELETE ON audit_events` for the application role is the other half, and it
belongs in the deployment's grants rather than in a migration this service runs as an owner.

    proposals 1 ─── n audit_events        ON DELETE CASCADE

The cascade is on the foreign key because the alternative is worse: an audit row pointing at a
proposal that no longer exists is a record nobody can interpret. Deleting a proposal at all is a
retention decision that no code path here performs — there is no `delete_proposal`.

Two more tables were added for the batch PADnext audit:

    batch_jobs 1 ─── n batch_files        ON DELETE CASCADE

They are ordinary mutable rows, unlike the two above, and the difference is deliberate. A proposal
records that a human took responsibility for a billing draft, so what it holds is written once. A
batch job records the progress and the result of a computation the engine ran on its own: the
status moves PENDING → PROCESSING → COMPLETED, each file's verdict is written as it lands, and
re-running the same files would simply produce another batch. There is nothing here for an audit
log to protect, and no approval boundary to enforce — which is exactly why these two tables are
plain and `proposals` is not.

And one standalone table:

    rule_reviews        one row per rule a billing expert has decided about

It has no foreign key because the thing it points at is not in this database: `rule_id` names a row
in `data/rules/*.csv`, which is versioned source data the API must never write. The reviews are an
*overlay* merged onto the CSVs at load time (`RuleStore.with_reviews`), which is what lets a
reviewer promote a machine-extracted rule to verified without anyone editing a file that git tracks
and a second approver has to sign off.

And two that describe *who is billing*, written by the web tier's onboarding endpoint:

    doctor_profiles     one row per Better Auth user     — name, title, LANR, Facharzt
    practices           one row per Better Auth organisation — name, BSNR, city, PLZ

They are here, and not as extra columns on Better Auth's `user` and `organization`, because those
two tables belong to a migrator this one does not control: Better Auth computes its schema from the
library's own field definitions and `alembic/env.py` excludes its tables from autogenerate, so a
business column added to either would be owned by nobody and dropped by the next upgrade. Keeping
the identity tier pure is what lets two migrators share one database safely — `apps/web/lib/db.ts`
is the seam the web tier reaches these two through, and it says the same thing from the other side.

Neither has a foreign key into Better Auth's tables, for the same reason `proposals.created_by` has
none: `alembic upgrade head` does not create `user` or `organization`, and a constraint on a table
this migration cannot create would make the schema unappliable wherever the engine runs alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONVariant, TimestampVariant, UUIDVariant


class AuditEventType(StrEnum):
    """What an audit row records.

    A closed set, because an audit log whose vocabulary grows per caller cannot be queried. Stored
    as a string rather than a native enum: adding a member to a Postgres enum needs a migration and
    a lock, and the constraint that matters (only these values are written) lives in this class.
    """

    CREATED = "CREATED"
    VIEWED = "VIEWED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPORTED = "EXPORTED"


def utcnow() -> datetime:
    """Application-side UTC.

    Deliberately not `server_default=func.now()`: the receipt, the audit trail and these rows all
    have to agree about when something happened, and the application clock is the one the rest of
    the engine already stamps with. A database default would introduce a second clock and a skew
    nobody would look for.
    """
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Re-attach UTC to a timestamp SQLite handed back naive.

    Postgres returns an aware datetime and this is a no-op. SQLite has no timestamp type, so it
    returns exactly the naive value that was written — which was UTC, per `utcnow`. Treating that
    as local time is the classic way to make an audit log off by an hour twice a year.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ProposalRecord(Base):
    """One solve, and the decision taken on it."""

    __tablename__ = "proposals"

    #: Surrogate UUID key. The audit log references this, not the public id, so the join survives
    #: any future change to how a proposal is named on the wire.
    id: Mapped[uuid.UUID] = mapped_column(UUIDVariant, primary_key=True, default=uuid.uuid4)

    #: The identifier the API returns and the frontend holds — `prop_<hex>`.
    #:
    #: Not folded into `id`, and not derived from it. It is an opaque public handle whose format is
    #: part of a contract already shipped, and it is 16 hex characters where a UUID is 32, so it
    #: cannot be recovered from one. Keeping both is a column; changing the wire format to suit the
    #: schema would be a breaking change to a client that is not asking for one.
    proposal_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    #: The caller's own identifier for the encounter, so a proposal can be matched back to it.
    case_id: Mapped[str | None] = mapped_column(String(128), index=True, default=None)

    #: DRAFT | APPROVED | REJECTED | EXPORTED. Indexed: `GET /proposals?status=` filters on it,
    #: and so does every "what is still awaiting a decision" query a reviewer will want.
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    # -- identity of what produced the result (write-once) ----------------------------------

    #: SHA-256 over the catalog, rule tables, logic programs, solver versions, policy and input.
    #: Indexed because "show me every proposal produced by this exact engine state" is the query a
    #: Rechnungsprüfer asks, and the one that makes a recall tractable.
    receipt_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    #: SHA-256 over the canonical clinical input alone. The receipt hash covers the input *and*
    #: the output and the engine's identity, so it cannot answer "was this the same case?" across
    #: a catalog bump. This can.
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    catalog_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    catalog_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    rules_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    rules_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    logic_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    solver_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    rules_engine_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # -- the result itself (write-once) ------------------------------------------------------

    #: The full `CodingResponse`: extraction, coding, audit trail, proof trees. Stored whole rather
    #: than normalised into position/proof tables, because what has to be reproducible is the
    #: response as served — a normalised copy re-serialised by later code is a different document,
    #: and the receipt hash would no longer match it.
    solver_result_json: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False)

    warnings_json: Mapped[list[Any]] = mapped_column(JSONVariant, nullable=False, default=list)
    missing_documentation_json: Mapped[list[Any]] = mapped_column(
        JSONVariant, nullable=False, default=list
    )

    #: The rule-coverage snapshot. The five counts the API flattens onto the proposal are read back
    #: out of this rather than stored twice, so they cannot disagree with it.
    rule_coverage_json: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, default=None)

    #: Whether the response this row was built from came out of the content-addressed cache. Part
    #: of the record because it explains why two proposals with one receipt hash have different
    #: `created_at` values and only one of them cost a solve.
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # -- lifecycle ---------------------------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(TimestampVariant, nullable=False, default=utcnow)

    #: The authenticated user who ran the solve that produced this draft — a Better Auth `user.id`
    #: forwarded by the web tier in `X-User-ID` (see `app.api.identity`), or `system` when the call
    #: carried no session.
    #:
    #: The Better Auth `organization.id` this proposal belongs to — the tenancy boundary.
    #:
    #: Every read is filtered on it and every write sets it from the `X-Organization-ID` header the
    #: web tier forwards (`app.api.tenancy`), so one practice cannot see or decide another's drafts.
    #: Like `created_by` it is deliberately **not** a foreign key: `organization` is Better Auth's
    #: table, created by its own migrator, and a constraint here would make this schema depend on a
    #: table `alembic upgrade head` does not create.
    #:
    #: **Nullable, and that is about history rather than about policy.** Rows written before this
    #: column existed have no organisation and none can be invented for them — a backfill would have
    #: to guess which practice a draft belonged to, and guessing wrong assigns somebody's billing
    #: record to a stranger. So legacy rows keep `NULL` and are matched by no tenant's filter: they
    #: are unreachable through the API rather than visible to everyone, which is the safe direction
    #: for the ambiguity to fail in. Every row this code writes carries a value, because the header
    #: is required before a write is accepted at all.
    organization_id: Mapped[str | None] = mapped_column(String(256), default=None)

    #: Write-once, like everything above it: who produced a draft is part of what the draft *is*,
    #: not part of what was later decided about it. Deliberately **not** a foreign key — the `user`
    #: table is Better Auth's and is created by its own migrations, so a constraint here would make
    #: this schema depend on a table `alembic upgrade head` does not create. The id is opaque and
    #: stable, which is all a join needs.
    #:
    #: Nullable because every row written before this column existed has no answer, and inventing
    #: one would be worse than admitting it. New rows always carry a value.
    created_by: Mapped[str | None] = mapped_column(String(256), index=True, default=None)

    approved_at: Mapped[datetime | None] = mapped_column(TimestampVariant, default=None)
    approved_by: Mapped[str | None] = mapped_column(String(256), default=None)

    rejected_at: Mapped[datetime | None] = mapped_column(TimestampVariant, default=None)
    rejected_by: Mapped[str | None] = mapped_column(String(256), default=None)
    rejected_reason: Mapped[str | None] = mapped_column(String(2048), default=None)

    exported_at: Mapped[datetime | None] = mapped_column(TimestampVariant, default=None)

    #: Present so that attaching an event to a proposal resolves the foreign key without the
    #: caller having to flush first for an id. Deliberately NOT eagerly loaded: the log for a
    #: proposal only grows, and reading a proposal must not cost a scan of its whole history.
    #: `proposal_store.audit_events` queries the table directly when the log is what is wanted.
    events: Mapped[list[AuditEvent]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by="AuditEvent.timestamp",
    )

    __table_args__ = (
        # The list endpoint is "the most recent proposals, optionally in this status". Both halves
        # of that in one index, so the common query does not sort a table scan.
        Index("ix_proposals_status_created_at", "status", "created_at"),
        # Every listing is now organisation-scoped first and ordered by `created_at` second, so the
        # tenant is the leading column. A plain index on `organization_id` alone would be redundant
        # with this one — a composite's leading column serves the equality lookup on its own — and a
        # second index on the same column is write cost for no read.
        Index("ix_proposals_organization_id_created_at", "organization_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<ProposalRecord {self.proposal_id} {self.status}>"


class AuditEvent(Base):
    """One thing that happened to one proposal. Written once, never changed."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUIDVariant, primary_key=True, default=uuid.uuid4)

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUIDVariant,
        ForeignKey("proposals.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    #: One of `AuditEventType`. Indexed: "every approval last quarter" must not scan the log.
    event_type: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    #: Who did it. `system` for events no human triggered. Never empty — an unattributed audit row
    #: is indistinguishable from a missing one, so `record_event` refuses to write one.
    actor: Mapped[str] = mapped_column(String(256), nullable=False)

    timestamp: Mapped[datetime] = mapped_column(
        TimestampVariant, index=True, nullable=False, default=utcnow
    )

    #: Free-form context: the rejection reason, the note on an approval, the status the transition
    #: came from. `metadata` is taken by SQLAlchemy's declarative API, hence the suffix.
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, default=None)

    proposal: Mapped[ProposalRecord] = relationship(back_populates="events")

    __table_args__ = (
        # The audit view for one proposal, in order — the only read this table has to be fast at.
        Index("ix_audit_events_proposal_id_timestamp", "proposal_id", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<AuditEvent {self.event_type} by {self.actor} at {self.timestamp}>"


class BatchJobRecord(Base):
    """One batch upload: what was asked for, how far it got, and the roll-up when it is done."""

    __tablename__ = "batch_jobs"

    #: Surrogate UUID key. `batch_files` references this, not the public id, for the same reason
    #: `audit_events` references `proposals.id`: the join must survive a change to the wire format.
    id: Mapped[uuid.UUID] = mapped_column(UUIDVariant, primary_key=True, default=uuid.uuid4)

    #: The identifier the API returns and the frontend polls — `batch_<hex>`. Same shape and same
    #: reasoning as `ProposalRecord.proposal_id`: an opaque public handle, not the surrogate key.
    batch_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    #: One of `BatchJobStatus`. Indexed because "which batches are still running" is the query an
    #: operator asks after a restart — see the note on orphaned jobs in `app.services.batch_audit`.
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(TimestampVariant, nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(TimestampVariant, default=None)

    #: The Better Auth `organization.id` this batch belongs to. Same boundary, same reasoning and
    #: the same nullability as `ProposalRecord.organization_id` — see the note there.
    organization_id: Mapped[str | None] = mapped_column(String(256), default=None)

    #: Who uploaded the batch — the same forwarded Better Auth `user.id` as
    #: `ProposalRecord.created_by`, and nullable for the same reason. A batch is the one action here
    #: that costs real compute on somebody's behalf, so "who asked for this" is the question an
    #: operator looking at a busy queue actually has.
    created_by: Mapped[str | None] = mapped_column(String(256), index=True, default=None)

    #: The serialised `BatchAggregateSummary`. Stored rather than recomputed on every read: it is
    #: the answer to "what did this batch conclude", and recomputing it from the per-file reports
    #: each time would mean a later change to the aggregation silently restating a finished job.
    aggregate_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, default=None)

    #: Why the batch itself failed. A file that could not be read does NOT populate this — that is
    #: `BatchFileRecord.error_message`, and the two must not be conflated: one is a broken run, the
    #: other is a result.
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    #: Eagerly usable via the relationship because a batch is always read whole — the API returns
    #: every file's status with the job, and there is no "just the header" read of a batch.
    files: Mapped[list[BatchFileRecord]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="BatchFileRecord.filename",
    )

    __table_args__ = (
        # "The most recent batches, optionally in this status" — the same list query shape as
        # `proposals`, and the same reason for the composite index.
        Index("ix_batch_jobs_status_created_at", "status", "created_at"),
        # And the same tenant-leading composite, for the same reason as on `proposals`.
        Index("ix_batch_jobs_organization_id_created_at", "organization_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<BatchJobRecord {self.batch_id} {self.status}>"


class BatchFileRecord(Base):
    """One uploaded delivery inside a batch, and the report it produced."""

    __tablename__ = "batch_files"

    id: Mapped[uuid.UUID] = mapped_column(UUIDVariant, primary_key=True, default=uuid.uuid4)

    batch_job_id: Mapped[uuid.UUID] = mapped_column(
        UUIDVariant,
        ForeignKey("batch_jobs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    #: The name the client uploaded, used for display and for the audit trail. Not unique within a
    #: batch: uploading two files of the same name is a thing a file picker will happily do, and
    #: refusing the batch over it would be worse than showing the name twice.
    #:
    #: It is not treated as a path and never touches the filesystem — nothing here writes an
    #: uploaded file to disk, so a `../` in this column is a display curiosity, not a traversal.
    filename: Mapped[str] = mapped_column(String(512), nullable=False)

    #: One of `BatchFileStatus`.
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    #: The serialised `PadnextAuditReport`, exactly as `POST /padnext/audit` would have returned it
    #: for this file. Stored whole for the same reason `proposals.solver_result_json` is: a
    #: normalised copy re-serialised by later code is a different document, and the report carries
    #: its own `receipt_hash` over the data and policy that produced it.
    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, default=None)

    #: Why this file could not be audited — an unreadable container, a delivery flagged as
    #: production data, a rules engine that was not available. `Text`, not `String(n)`: truncating
    #: the one explanation a user gets to a column width would be a poor trade.
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    job: Mapped[BatchJobRecord] = relationship(back_populates="files")

    __table_args__ = (
        # The background task walks one job's files in order, and the API reads them all back.
        Index("ix_batch_files_batch_job_id_filename", "batch_job_id", "filename"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<BatchFileRecord {self.filename} {self.status}>"


class RuleReviewRecord(Base):
    """One rule, and what a billing expert decided about it.

    Deliberately **not** append-only, unlike `audit_events`. A reviewer changing their mind about a
    machine-extracted exclusion is a normal event, not a falsification of a record — nobody's
    liability attaches to it the way it attaches to an approval, and the rule set is a working
    document rather than a decision that was taken once. `updated_at` says when the current answer
    was reached; if the *history* of a rule's verdict ever matters, that is a second table, not a
    reinterpretation of this one.

    There is no foreign key. `rule_id` identifies a row in `data/rules/*.csv`, and those files are
    versioned source data outside this database — see the module docstring.
    """

    __tablename__ = "rule_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUIDVariant, primary_key=True, default=uuid.uuid4)

    #: The rule this decision is about — `excl_auto_30_4`, `ziel_man_301_200`, and so on.
    #:
    #: Unique, because the merge resolves `rule_id -> status` and two rows answering to one id
    #: would make the effective verification state depend on row order. The endpoint upserts.
    rule_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    #: VERIFIED | REJECTED | PENDING — one of `app.rules.rule_store.RuleReviewStatus`.
    #:
    #: `PENDING` is a real, storable state: a reviewer who has read a rule and cannot decide should
    #: be able to say so. It merges exactly like no row at all, because an undecided rule is still
    #: an unchecked one.
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    #: Who decided. Nullable only because a `PENDING` row can precede a decision; the API requires
    #: it for VERIFIED and REJECTED. Recorded, never authenticated: it is a name the caller typed,
    #: not the `X-User-ID` the web tier forwards, and this service verifies neither.
    reviewed_by: Mapped[str | None] = mapped_column(String(256), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(TimestampVariant, default=None)

    #: Why. The most valuable column in the table and the reason it is `Text`: a reviewer's
    #: reasoning about a GOÄ Anmerkung is the thing a second reviewer needs, and truncating it to a
    #: column width would be a poor trade.
    review_notes: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(TimestampVariant, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampVariant, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        # "Everything decided one way", which is what the merge reads and what the dashboard counts.
        Index("ix_rule_reviews_status_rule_id", "status", "rule_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<RuleReviewRecord {self.rule_id} {self.status}>"


class AuditLogIsAppendOnly(RuntimeError):
    """Raised when something tries to change or remove an audit row.

    A programming error, not a user error: nothing in the API can reach this. It exists so that a
    future service method which "fixes up" an event fails in the developer's own test run instead
    of quietly rewriting the record a reviewer will be shown.
    """


@event.listens_for(AuditEvent, "before_update")
def _reject_update(_mapper, _connection, target: AuditEvent) -> None:
    raise AuditLogIsAppendOnly(
        f"audit_events is append-only: {target.event_type} event {target.id} cannot be modified. "
        "Record a new event describing the correction instead."
    )


@event.listens_for(AuditEvent, "before_delete")
def _reject_delete(_mapper, _connection, target: AuditEvent) -> None:
    raise AuditLogIsAppendOnly(
        f"audit_events is append-only: {target.event_type} event {target.id} cannot be deleted. "
        "Retention deletion is a policy decision and has no code path here."
    )


__all__ = [
    "AuditEvent",
    "AuditEventType",
    "AuditLogIsAppendOnly",
    "BatchFileRecord",
    "BatchJobRecord",
    "ProposalRecord",
    "RuleReviewRecord",
    "as_utc",
    "utcnow",
]


class DoctorProfileRecord(Base):
    """The person behind a Better Auth account: who they are on an invoice.

    Better Auth's `user` table holds an email, a display name and a password hash — everything
    needed to *sign somebody in* and nothing needed to *bill in their name*. This table holds the
    second half, and it is a separate table rather than four more columns on `user` for one blunt
    reason: that table is Better Auth's, created and altered by its own migrator from the Next.js
    app (`pnpm --filter web auth:migrate`). Business columns added to it would be columns neither
    migrator owns — Alembic is told to keep its hands off `user` (`alembic/env.py`), and Better Auth
    computes its schema from the library's own field definitions, so it would drop them on the next
    upgrade. Keeping the identity tier pure is what makes both migrators safe to run.

    **`user_id` is a Better Auth `user.id` and deliberately not a foreign key**, for exactly the
    reason `ProposalRecord.created_by` is not one: `alembic upgrade head` does not create `user`, so
    a constraint here would make this schema unappliable against any database the engine runs in
    without the web tier — the test suite included. It is unique instead, which is the constraint
    that actually matters: a doctor has one professional identity, and two rows answering to one
    account would make "who is billing this" depend on which row was read first.

    Nothing in the engine reads this table yet. It is written by `POST /api/onboarding` in the web
    tier and lives here because it is business data, and because the LANR is what a PADnext export
    will have to carry when invoice generation lands — at which point the alternative (a second
    database, or a round-trip to the web tier) would be a join this service cannot make.
    """

    __tablename__ = "doctor_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUIDVariant, primary_key=True, default=uuid.uuid4)

    #: The Better Auth `user.id` this profile belongs to. Unique — see the class docstring.
    user_id: Mapped[str] = mapped_column(String(256), unique=True, index=True, nullable=False)

    #: `Dr.`, `Prof. Dr.`, `Dr. med. dent.` — or nothing at all.
    #:
    #: The only nullable column of the five, because a physician without an academic title is not an
    #: incomplete record and a required field would make them type a placeholder. Everything else
    #: here is something every practising doctor has.
    title: Mapped[str | None] = mapped_column(String(64), default=None)

    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)

    #: Lebenslange Arztnummer — nine digits, issued once and kept for a career.
    #:
    #: Unique, and this is the one uniqueness constraint here with teeth: the LANR identifies the
    #: physician on a claim, so two accounts carrying one LANR is either a duplicate registration or
    #: somebody typing a colleague's number. Both are things a billing system should refuse at the
    #: point of entry rather than discover in a rejected invoice. `String(16)` rather than
    #: `String(9)`: the format is fixed today and a column width is a poor place to enforce it — the
    #: check that a caller sees a message about lives in `apps/web/lib/onboarding/validate.ts`.
    lanr: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)

    #: The Facharzt designation as free text — "Allgemeinmedizin", "Innere Medizin", "Chirurgie".
    #:
    #: Not an enum and not a foreign key into a catalog. The Weiterbildungsordnung is per-Kammer and
    #: revised, so a closed set maintained here would be wrong for somebody on the day it shipped;
    #: nothing branches on this value, and when something does it will need a mapped code rather
    #: than a tightened string.
    specialty: Mapped[str] = mapped_column(String(128), nullable=False)

    created_at: Mapped[datetime] = mapped_column(TimestampVariant, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampVariant, nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<DoctorProfileRecord {self.user_id} lanr={self.lanr}>"


class PracticeRecord(Base):
    """The Betriebsstätte a Better Auth organisation stands for.

    Same split as `DoctorProfileRecord`, one tier up: Better Auth's `organization` table holds a
    name, a slug and a logo, and this holds what a practice *is* for billing purposes. The
    organisation is the tenant boundary; the practice is the business behind it.

    `organization_id` is unique and, again, not a foreign key — `organization` is created by Better
    Auth's migrator, not by `alembic upgrade head`. One organisation is one Betriebsstätte.

    **`bsnr` is indexed and NOT unique, which is the opposite of `lanr` and deliberate.** A BSNR
    names a place, and several organisations legitimately answer to one: a Berufsausübungs-
    gemeinschaft where each physician has their own tenant, a practice that re-registers after a
    handover. A LANR names a person and there is only ever one of those. Making the place unique
    would refuse the first shared-premises sign-up with an error nobody could act on, so the index
    is there for the lookup and the constraint is not.
    """

    __tablename__ = "practices"

    id: Mapped[uuid.UUID] = mapped_column(UUIDVariant, primary_key=True, default=uuid.uuid4)

    #: The Better Auth `organization.id` this practice belongs to. Unique — see above.
    organization_id: Mapped[str] = mapped_column(
        String(256), unique=True, index=True, nullable=False
    )

    #: The name on the Praxisschild. Also mirrored onto `organization.name` by the onboarding
    #: endpoint, so the organisation switcher shows a practice rather than an empty label — the
    #: mirror is one-way and this column is the source of truth.
    practice_name: Mapped[str] = mapped_column(String(256), nullable=False)

    #: Betriebsstättennummer — nine digits identifying the premises. Indexed, not unique.
    bsnr: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    city: Mapped[str] = mapped_column(String(128), nullable=False)

    #: Postleitzahl. `String`, never an integer: German PLZ are five characters and a third of them
    #: begin with a zero, which is exactly the leading digit an integer column eats.
    plz: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(TimestampVariant, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampVariant, nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<PracticeRecord {self.organization_id} bsnr={self.bsnr}>"
