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
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String, event
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
    "ProposalRecord",
    "as_utc",
    "utcnow",
]
