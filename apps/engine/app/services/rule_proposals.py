"""Where a pilot's "this Ziffer has no rule" report is stored.

The only thing this module does is write and read `rule_proposals`. There is no merge into the
running engine, unlike `app.services.rule_reviews` — a report is not a decision, it is a data point
towards deciding which rule to write next. Turning the accumulated reports into a prioritised
worklist is a query somebody runs against this table later, not a responsibility of this module.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import RuleProposalRecord, utcnow
from app.db.session import Database, get_database


class RuleProposalStore:
    """Reads and writes `rule_proposals`. The only module that knows the table exists."""

    def __init__(self, database: Database | None = None) -> None:
        self._database = database

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    async def create(
        self,
        *,
        ziffer: str,
        context: str,
        organization_id: str,
        receipt_hash: str | None = None,
        created_by: str | None = None,
    ) -> RuleProposalRecord:
        """Record one report. Always an insert — there is nothing here to upsert onto."""
        record = RuleProposalRecord(
            ziffer=ziffer,
            context=context,
            receipt_hash=receipt_hash,
            organization_id=organization_id,
            created_by=created_by,
            created_at=utcnow(),
        )
        async with self.database.session() as session:
            session.add(record)
            await session.flush()
            await session.refresh(record)
            return record

    async def list_for_organization(
        self, organization_id: str, *, limit: int = 100
    ) -> list[RuleProposalRecord]:
        """The calling practice's reports, newest first. Used by tests and by ad-hoc triage."""
        async with self.database.session() as session:
            statement = (
                select(RuleProposalRecord)
                .where(RuleProposalRecord.organization_id == organization_id)
                .order_by(RuleProposalRecord.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(statement)).scalars().all()
            for row in rows:
                _ = (row.id, row.ziffer, row.context, row.receipt_hash, row.created_at)
            return list(rows)


__all__ = ["RuleProposalStore"]
