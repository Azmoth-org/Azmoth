"""Where a billing expert's verdict on a rule is stored, and how it reaches the engine.

The rules themselves live in `data/rules/*.csv`, which this service never writes. They are
versioned source data: a change to them is a reviewed pull request needing a second approver, and
an API that edited them would route around exactly that control. So a decision is stored here, in
`rule_reviews`, and merged onto the parsed CSVs at load time by `RuleStore.with_reviews`. The CSV
is what the GOÄ import produced; the table is what a human concluded about it; the merged store is
what the engine runs.

    data/rules/*.csv  ─┐
                       ├─►  RuleStore.with_reviews(…)  ─►  the store the pipeline holds
    rule_reviews      ─┘

**Why the merge does not live in `RuleStore.load()`.** The brief's instinct was to have the store
query the database itself, and it cannot: `load()` is synchronous and `lru_cache`d, the database
driver is async, and `import app.main` has to work on a machine with no Postgres — for an OpenAPI
export, in CI, on a laptop. A store that opened a connection would break all three and would still
have to decide what to do when the query fails. Instead the rules layer stays pure and takes a
plain mapping, and this module is the only place that knows a database exists.

**Refreshing, and its honest limit.** The pipeline holds one merged store for the process, because
Soufflé, Clingo and the validator are each handed it at construction and a store that changed under
them mid-solve would make the three disagree about what the rules are. `refresh_pipeline_rules`
rebuilds it, and the review endpoint calls it after every write. Under more than one worker process
that is per-process: a review taken on worker A is live there immediately and on worker B at its
next restart. Stated rather than hidden — the fix is a shared invalidation channel, which is
exactly the Redis this MVP is not allowed to add, and the failure mode meanwhile is a rule being
enforced slightly later than the dashboard says, never a wrong answer.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.db.models import RuleReviewRecord, as_utc, utcnow
from app.db.session import Database, get_database
from app.rules.rule_store import (
    ExclusionRule,
    FactorCapRule,
    Rule,
    RuleReviewStatus,
    RuleStore,
    SpecificityRule,
    ZielleistungRule,
)
from app.schemas.rules import ReviewableRule, RuleKind

log = logging.getLogger(__name__)


class RuleNotFound(KeyError):
    """A review was submitted for a rule id no loaded CSV contains."""

    def __init__(self, rule_id: str) -> None:
        super().__init__(rule_id)
        self.rule_id = rule_id


# ------------------------------------------------------------------------------------------
# describing a rule for the queue
# ------------------------------------------------------------------------------------------

#: Which rule table each concrete class came from, and how to read its Ziffern.
#:
#: A table rather than a chain of `isinstance` branches scattered across the service, so adding a
#: rule type is one entry here and a compile-time failure at `RuleKind` rather than a queue that
#: silently omits it.
_KINDS: dict[type, tuple[RuleKind, tuple[str, ...]]] = {
    ExclusionRule: ("exclusion", ("from_ziffer", "to_ziffer")),
    ZielleistungRule: ("zielleistung", ("parent_ziffer", "child_ziffer")),
    SpecificityRule: ("specificity", ("specific_ziffer", "general_ziffer")),
    FactorCapRule: ("factor_cap", ("ziffer",)),
}

#: Extra fields worth showing per type. `direction` decides whether an exclusion is mutual, which
#: is the difference between "5 excludes 7" and "5 and 7 exclude each other" — a reviewer checking
#: an extraction against the GOÄ sentence needs to see which one the extractor chose.
_DETAIL: dict[type, tuple[str, ...]] = {
    ExclusionRule: ("direction",),
    FactorCapRule: ("max_factor",),
}


def kind_of(rule: Rule) -> RuleKind | None:
    """The rule's table, or `None` for a type the queue does not review (analog candidates)."""
    entry = _KINDS.get(type(rule))
    return entry[0] if entry else None


def describe(rule: Rule, record: RuleReviewRecord | None = None) -> ReviewableRule:
    """One rule as the queue presents it: the evidence, not a summary of it.

    The quote is carried in full and never truncated. A reviewer deciding whether the extractor
    read "ist neben den Leistungen nach den Nummern …" correctly is doing so *from that sentence*,
    and a shortened one would turn the review into a rubber stamp.

    The review fields come from `record` when one exists, and from the merged rule otherwise. They
    are not the same thing and the difference is exactly `PENDING`: the rule carries what the merge
    *applied*, and a parked rule applies nothing, so a reviewer who bookmarked a rule yesterday
    would see no trace of it if this read the rule. The row is what was decided; the rule is what
    that decision did.
    """
    entry = _KINDS.get(type(rule))
    if entry is None:  # pragma: no cover - callers filter first; belt and braces
        raise ValueError(f"{type(rule).__name__} is not a reviewable rule type")
    kind, fields = entry

    roles = {field.removesuffix("_ziffer"): getattr(rule, field) for field in fields}
    detail: dict[str, Any] = {
        field: str(getattr(rule, field)) for field in _DETAIL.get(type(rule), ())
    }

    return ReviewableRule(
        rule_id=rule.rule_id,
        kind=kind,
        legal_basis=rule.legal_basis,
        quote=rule.quote,
        source=rule.source,
        ziffern=[value for value in roles.values() if value],
        ziffer_roles=roles,
        detail=detail,
        csv_verified=rule.csv_verified,
        verified=rule.verified,
        review_status=(record.status if record else rule.review_status) or None,
        reviewed_by=(record.reviewed_by if record else rule.reviewed_by) or None,
        reviewed_at=as_utc(record.reviewed_at) if record else None,
        review_notes=(record.review_notes if record else None) or None,
    )


# ------------------------------------------------------------------------------------------
# the identity of a merged rule set
# ------------------------------------------------------------------------------------------


def effective_rules_hash(csv_hash: str, statuses: dict[str, str]) -> str:
    """The rules identity, once reviews are part of what the engine enforces.

    This exists because `rules_hash` is not decoration. It feeds the **receipt hash** and the
    **result cache key**, so if a review changed which rules are enforced and this did not move,
    two things would break at once: two proposals with one receipt hash could have been produced
    under different rule sets — the receipt would be lying, which is the one thing it must not do —
    and the cache would keep serving an answer computed before a rule was verified.

    With no decided reviews it returns the CSV digest **unchanged**, byte for byte. That is not an
    optimisation, it is the property that keeps every existing golden receipt valid: a deployment
    that has never used the review queue must hash exactly as it did before this feature existed.

    `PENDING` rows are excluded along with everything else that does not change enforcement — a
    bookmark is not a rule change, and letting one invalidate every cached solve would be a
    surprising amount of work for a decision nobody has taken.
    """
    decided = {
        rule_id: status
        for rule_id, status in statuses.items()
        if status in {str(RuleReviewStatus.VERIFIED), str(RuleReviewStatus.REJECTED)}
    }
    if not decided:
        return csv_hash

    digest = hashlib.sha256()
    digest.update(csv_hash.encode("utf-8"))
    digest.update(b"\0rule_reviews\0")
    for rule_id in sorted(decided):
        digest.update(rule_id.encode("utf-8"))
        digest.update(b"=")
        digest.update(decided[rule_id].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


# ------------------------------------------------------------------------------------------
# the store
# ------------------------------------------------------------------------------------------


class RuleReviewStore:
    """Reads and writes `rule_reviews`. The only module that knows the table exists."""

    def __init__(self, database: Database | None = None) -> None:
        self._database = database

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    async def statuses(self) -> dict[str, str]:
        """`rule_id -> status` for every review row. What `RuleStore.with_reviews` consumes.

        Returns a plain dict rather than ORM rows so nothing above this can lazy-load from a closed
        session — the same rule the proposal store follows, and the same reason.
        """
        async with self.database.session() as session:
            rows = (await session.execute(select(RuleReviewRecord))).scalars().all()
            return {row.rule_id: row.status for row in rows}

    async def records(self) -> dict[str, RuleReviewRecord]:
        """Every review row, keyed by rule id, detached into plain data for the queue.

        SQLAlchemy objects would be expired the moment the session closes; these are read inside it
        and the attributes are touched here, so what escapes is safe to read.
        """
        async with self.database.session() as session:
            rows = (await session.execute(select(RuleReviewRecord))).scalars().all()
            # Touch every attribute inside the session. `expire_on_commit=False` already makes this
            # safe, but relying on a sessionmaker setting three layers away is how `MissingGreenlet`
            # gets into production.
            for row in rows:
                _ = (row.rule_id, row.status, row.reviewed_by, row.reviewed_at, row.review_notes)
            return {row.rule_id: row for row in rows}

    async def upsert(
        self,
        rule_id: str,
        *,
        status: RuleReviewStatus | str,
        reviewed_by: str = "",
        review_notes: str = "",
    ) -> RuleReviewRecord:
        """Record a verdict, replacing any earlier one for the same rule.

        Upsert rather than insert because `rule_id` is unique and a reviewer changing their mind is
        a normal event — see `RuleReviewRecord` for why this table is not append-only. `reviewed_at`
        is re-stamped on every write, so it always says when the *current* answer was reached rather
        than when the rule was first looked at.
        """
        status = str(status)
        now = utcnow()

        async with self.database.session() as session:
            statement = select(RuleReviewRecord).where(RuleReviewRecord.rule_id == rule_id)
            record = (await session.execute(statement)).scalar_one_or_none()

            if record is None:
                record = RuleReviewRecord(rule_id=rule_id, status=status, created_at=now)
                session.add(record)

            record.status = status
            record.reviewed_by = reviewed_by or None
            record.review_notes = review_notes or None
            # A decision is stamped; a PENDING bookmark is not, because nothing was decided.
            record.reviewed_at = (
                now
                if status in {str(RuleReviewStatus.VERIFIED), str(RuleReviewStatus.REJECTED)}
                else None
            )
            record.updated_at = now

            await session.flush()
            await session.refresh(record)
            return record

    async def count_by_status(self) -> dict[str, int]:
        """How many rows sit in each status. For diagnostics and the startup log."""
        counts: dict[str, int] = {}
        for rule_id, status in (await self.statuses()).items():  # noqa: B007 - id unused
            counts[status] = counts.get(status, 0) + 1
        return counts


# ------------------------------------------------------------------------------------------
# merging into the running pipeline
# ------------------------------------------------------------------------------------------


async def merged_rules(base: RuleStore, store: RuleReviewStore | None = None) -> RuleStore:
    """`base` with every stored review applied. The one place the two halves meet."""
    statuses = await (store or RuleReviewStore()).statuses()
    return base.with_reviews(statuses)


async def refresh_pipeline_rules(pipe: Any, store: RuleReviewStore | None = None) -> RuleStore:
    """Rebuild the pipeline's rule store from the CSVs plus the current reviews.

    Called at startup and after every review write. It re-reads the CSVs rather than re-merging the
    store in hand, because merging a merged store would compound: a rule rejected yesterday and
    verified today has to be decided from the CSV's own flag, not from what the last merge left
    behind.
    """
    statuses = await (store or RuleReviewStore()).statuses()
    pipe.apply_rule_reviews(statuses)
    log.info(
        "rules refreshed: %d review(s) applied, %d enforced, %d still unverified",
        len(statuses),
        len(pipe.rules.exclusions)
        + len(pipe.rules.zielleistung)
        + len(pipe.rules.specificity)
        + len(pipe.rules.factor_caps),
        pipe.rules.unverified_constraint_rule_count(),
    )
    return pipe.rules


__all__ = [
    "RuleNotFound",
    "RuleReviewStore",
    "describe",
    "effective_rules_hash",
    "kind_of",
    "merged_rules",
    "refresh_pipeline_rules",
]
