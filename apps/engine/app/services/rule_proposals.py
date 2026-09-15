"""Where a pilot's "this Ziffer has no rule" report is stored.

The only thing this module does is write and read `rule_proposals`. There is no merge into the
running engine, unlike `app.services.rule_reviews` — a report is not a decision, it is a data point
towards deciding which rule to write next. Turning the accumulated reports into a prioritised
worklist is a query somebody runs against this table later, not a responsibility of this module.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import RuleProposalRecord, utcnow
from app.db.session import Database, get_database

#: Default and maximum page size for `GET /rules/proposals`. Same figures `ProposalStore` uses for
#: its listing, for no reason stronger than consistency — a row here is far smaller than a
#: `Proposal` (five short fields, no solver result), so the ceiling is not protecting against a
#: heavy row the way it does there.
DEFAULT_RULE_PROPOSAL_LIST_LIMIT = 50
MAX_RULE_PROPOSAL_LIST_LIMIT = 100


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
        self, organization_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[RuleProposalRecord]:
        """The calling practice's reports, newest first. Used by tests, ad-hoc triage and the
        `GET /rules/proposals` listing."""
        async with self.database.session() as session:
            statement = (
                select(RuleProposalRecord)
                .where(RuleProposalRecord.organization_id == organization_id)
                .order_by(RuleProposalRecord.created_at.desc(), RuleProposalRecord.id.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(statement)).scalars().all()
            for row in rows:
                _ = (row.id, row.ziffer, row.context, row.receipt_hash, row.created_at)
            return list(rows)

    async def count_for_organization(self, organization_id: str) -> int:
        """How many reports the organisation has filed in total, ignoring any page.

        What `RuleProposalList.total` is built from — the same reason `ProposalStore.count` exists
        beside `list_proposals`: a page cannot say "50 of how many" from its own length alone.
        """
        async with self.database.session() as session:
            statement = select(func.count()).select_from(RuleProposalRecord).where(
                RuleProposalRecord.organization_id == organization_id
            )
            return int((await session.execute(statement)).scalar_one())


__all__ = [
    "DEFAULT_RULE_PROPOSAL_LIST_LIMIT",
    "MAX_RULE_PROPOSAL_LIST_LIMIT",
    "RuleProposalStore",
]
