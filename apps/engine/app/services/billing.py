"""Which practice may audit, how much they have audited, and what a closed period came to.

Three responsibilities, and they are deliberately in one module because they are three views of one
number — how many invoices a practice audited in the period they are currently in:

    BillingStore.entitlement    what this practice is allowed, and which period is open
    BillingStore.check          may this request audit `n` more, and at what cost
    BillingStore.close_period   the period ended; price it and write one invoice row

## The counter is `api_usage_logs`, not a column that gets incremented

There is no `invoices_used_this_month` anywhere. The figure is a `SUM(invoices_processed)` over the
usage rows in the open period, which costs one indexed aggregate on
`(organization_id, timestamp)` — the composite index `0009` created for exactly this shape of query.

A running counter would be faster and would be wrong in a way that is very hard to find. It would be
a second source of truth for a billable quantity, and the day it disagreed with the usage rows —
a partial flush, a retried transaction, a period boundary crossed mid-request — there would be no way
to tell which of the two a customer should be charged from. Deriving it means the invoice and the
usage report cannot disagree, because they are the same query.

**What that inherits, and what `check` does about it.** `app.services.usage` buffers usage rows for
up to 25 requests or 15 seconds, so a naive `SUM` can be that far behind — which on a hard-stop plan
would let a quota of 50 through at 75, and would then have the practice's own usage screen disagree
with the refusal they eventually got.

So `check` flushes the meter **only when the buffered rows could change its answer**: within
`FLUSH_THRESHOLD` of the ceiling it flushes and re-reads, and anywhere else it does not. A practice at
12 of 2,500 pays nothing for exactness it does not need; a practice at 49 of 50 gets an exact answer.
That keeps the buffer's whole benefit on the hot path and removes the one place its lag was visible
to a customer.

## Periods are stored, not computed

`current_period_start` / `current_period_end` are columns, and `roll` moves them forward one month at
a time when the clock has passed the end. Two reasons, and the second is the one that settles it.

A practice that signed up on the 14th is billed on the 14th, so a period is not "the calendar month"
— and `GET /api/v1/settings/usage`'s calendar month is a *different* window, deliberately, because
"what have we used this month" and "what will this period cost" are different questions. Both state
the window they used, which is the rule that keeps them from being confused for one another.

And an invoice has to be able to say what window it covered years later, without depending on
whatever today's code thinks a month is.

## Rolling a period is what creates an invoice

There is no scheduler here. `roll` is called from the read and check paths, so the first request of
a new period is what closes the previous one — the same discipline `app.services.usage` uses for its
flush and for the same reason: this stack has no Redis, no Celery and a SQLite default whose single
writer makes a background task that transacts alongside requests actively unsafe.

A practice that makes no request for three months gets three invoices when they next appear, each
priced from the entitlement as it was — because the loop rolls one period at a time and prices each
from the row before advancing it. A practice that never comes back gets none, which is correct: it
also has no usage to bill.

**Closing is idempotent.** `billing_invoices (organization_id, period_start)` is unique, so a race
between two requests that both notice the period ended ends with one invoice and one caller
discovering the constraint. The loser does not retry and does not raise: it re-reads.

## Money is an integer count of cents, everywhere, with no exceptions

No floats, no `Decimal`, no strings that look like `"99.00"`. The overage line is
`max(0, processed - included) * overage_rate_cents`, which is exact in `int` and is not exact in
`float` for any rate that is not a power of two. `data/arnon.dk/data/markdown/
5-things-i-learned-developing-billing-system.md` makes the general argument (and the sharper one
about currencies with no subdivision, which is why nothing here divides by 100 to store a value).

Formatting cents into `1.234,50 €` is a presentation concern and belongs where the presenting
happens — the schema returns cents.
"""

from __future__ import annotations

import logging
import secrets
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    ApiUsageRecord,
    BillingInvoiceRecord,
    OrganizationBillingRecord,
    as_utc,
    utcnow,
)
from app.db.session import Database, get_database
from app.services.billing_plans import (
    ORDER,
    Plan,
    SubscriptionTier,
    default_plan,
    plan as plan_by_code,
)
from app.services.usage import FLUSH_THRESHOLD

log = logging.getLogger(__name__)

#: How many periods `roll` will close in one call before giving up and logging.
#:
#: A practice absent for two years would otherwise make its next request pay for twenty-four
#: invoice writes. The cap turns that into a bounded cost per request and a log line; the remaining
#: periods are closed by the requests that follow, one batch at a time, so nothing is lost.
MAX_PERIODS_PER_ROLL = 24


def _add_one_month(moment: datetime) -> datetime:
    """One calendar month later, clamping the day to what the target month actually has.

    31 January + 1 month is 28 February (29 in a leap year), not 3 March. Both answers are defensible
    in the abstract and only one of them is defensible on an invoice: a period that starts on the 31st
    must not silently skip February, because the period after it would then start on the 3rd and the
    practice's billing date would walk forward a few days every year.

    `dateutil.relativedelta` does this and is not a dependency this service is going to take for
    eleven lines — see the note on pinning in `app/services/pdf.py`.
    """
    year = moment.year + (moment.month // 12)
    month = moment.month % 12 + 1
    day = min(moment.day, monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _invoice_id() -> str:
    """`inv_<16 hex>`. Opaque, unguessable, and not derived from anything about the practice."""
    return f"inv_{secrets.token_hex(8)}"


@dataclass(frozen=True)
class Entitlement:
    """What one practice is allowed, and which period that allowance is for.

    A snapshot read out of `organization_billing`, detached from the session on purpose: this crosses
    a request boundary into a dependency and a route, and a live ORM row there is how a lazy load
    ends up outside the session that could satisfy it.

    Every number here comes from the **row**, not from the plan catalog. `plan_code` is what the
    numbers were taken from when the plan was assigned; it is not where they are read from now. See
    `app.services.billing_plans` on why that distinction is the whole design.
    """

    organization_id: str
    subscription_tier: SubscriptionTier
    plan_code: str
    monthly_invoice_quota: int
    overage_rate_cents: int
    allow_overage: bool
    period_start: datetime
    period_end: datetime

    @property
    def plan_label(self) -> str:
        """What a settings screen prints. Falls back to the tier when the plan is unknown here.

        Unknown is a real state and not a bug: a row may name a `plan_code` from a deployment newer
        than this one after a rollback. The tier is stored on the row, so there is always something
        honest to print.
        """
        found = plan_by_code(self.plan_code)
        return found.label if found is not None else self.subscription_tier.value


@dataclass(frozen=True)
class QuotaDecision:
    """Whether `requested` more audits may run, and what they cost beyond the quota.

    Returned rather than raised, for the same reason `ratelimit.Decision` is: the figures go on a
    **successful** response too. A partner who can see "412 of 500 used" in a header slows down or
    upgrades before being refused, which is the entire purpose of publishing it.

    `overage_cents` is what *this request* would add beyond the included quota — not the period's
    total overage. A caller deciding whether to send a 300-file archive wants the marginal cost.
    """

    allowed: bool
    #: What refusing (or charging) was decided against — the entitlement as it stood.
    entitlement: Entitlement
    #: Invoices already audited in the open period.
    used: int
    #: What this request asked to audit.
    requested: int
    #: `max(0, quota - used)`, before this request.
    remaining: int
    #: How many of `requested` fall above the quota.
    overage_invoices: int
    #: `overage_invoices * overage_rate_cents`.
    overage_cents: int
    #: Seconds until the open period ends. What a `Retry-After` says when the answer is `429`.
    #:
    #: Honest rather than encouraging: a monthly quota resets in days, and telling a client to retry
    #: in five seconds would be a lie that produces a retry loop. At least 1 — a `Retry-After: 0`
    #: invites an immediate retry that would be refused again.
    reset_after: int

    def headers(self) -> dict[str, str]:
        """The quota trio, spelled like the rate limiter's so a client parses them the same way."""
        return {
            "X-Quota-Limit": str(self.entitlement.monthly_invoice_quota),
            "X-Quota-Remaining": str(max(0, self.remaining)),
            "X-Quota-Reset": str(self.reset_after),
        }


@dataclass(frozen=True)
class PeriodUsage:
    """What one practice has audited in one window, and what it would cost at today's entitlement.

    The read model behind `GET /api/v1/billing/usage`. Every field is derived from the same
    `SUM(invoices_processed)` the quota check uses, so a screen showing "47 of 100" and a refusal at
    101 cannot disagree.
    """

    entitlement: Entitlement
    invoices_processed: int
    requests: int
    remaining: int
    overage_invoices: int
    overage_cents: int
    base_fee_cents: int
    projected_total_cents: int


class BillingStore:
    """Every read and write against `organization_billing` and `billing_invoices`.

    A store rather than free functions for the same reason `ApiKeyStore` is one: the database is
    injectable, so a test drives it against its own engine without touching the process-wide
    singleton. It holds no connection — `get_database()` is asked per call — so one instance is safe
    for the life of the process, which is what `app.api.deps` keeps.
    """

    def __init__(self, database: Database | None = None) -> None:
        self._database = database

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    # --------------------------------------------------------------------------------------
    # the entitlement
    # --------------------------------------------------------------------------------------

    async def entitlement(self, organization_id: str, *, now: datetime | None = None) -> Entitlement:
        """This practice's plan, creating the pilot assignment if they have none, and rolling
        the period forward if the stored one has ended.

        **Get-or-create, and the create is the interesting half.** A practice reaches this on its
        first audit, which means the first audit must not fail because nobody had set up billing. So
        the default is the pilot plan — free, generous, overage allowed — and the row is written
        rather than assumed, because a quota check against an imaginary entitlement would have
        nothing to snapshot and nothing for an invoice to name.

        The unique index on `organization_id` is what makes the race safe: two simultaneous first
        audits both try to insert, one loses on the constraint, and the loser re-reads the winner's
        row. Both then hold the same entitlement rather than two half-counting ones.
        """
        moment = now or utcnow()

        async with self.database.session() as session:
            record = await self._load(session, organization_id)
            if record is None:
                record = self._new_record(organization_id, moment)
                session.add(record)
                try:
                    await session.flush()
                except IntegrityError:
                    # Lost the race described above. Roll back to a usable session and read what the
                    # winner wrote — which is the same entitlement this call would have created.
                    await session.rollback()
                    record = await self._load(session, organization_id)
                    if record is None:  # pragma: no cover - the constraint said it exists
                        raise
                else:
                    log.info(
                        "organisation %s had no billing row; assigned %s",
                        organization_id,
                        record.plan_code,
                    )

            snapshot = self._snapshot(record)

        # Rolling writes invoices, so it runs in its own transaction rather than inside the read
        # above: a failure to price a closed period must not lose the entitlement row that was just
        # created, and the entitlement is what the caller actually asked for.
        return await self.roll(snapshot, now=moment)

    async def roll(self, current: Entitlement, *, now: datetime | None = None) -> Entitlement:
        """Close every period that has ended, pricing each, and return the open one.

        One period at a time, and each is priced from the entitlement *as it was during that
        period* before the row advances. A practice absent for three months therefore gets three
        invoices with the right plan on each, rather than one covering three months at today's price.

        Returns `current` unchanged when the period is still open, which is the overwhelmingly
        common case and costs no query at all.
        """
        moment = now or utcnow()
        if moment < current.period_end:
            return current

        entitlement = current
        for _ in range(MAX_PERIODS_PER_ROLL):
            if moment < entitlement.period_end:
                return entitlement
            await self.close_period(entitlement)
            entitlement = await self._advance(entitlement)

        log.warning(
            "organisation %s is more than %d periods behind; the rest will close on the next "
            "requests",
            entitlement.organization_id,
            MAX_PERIODS_PER_ROLL,
        )
        return entitlement

    async def assign_plan(
        self, organization_id: str, target: Plan, *, actor: str | None = None
    ) -> Entitlement:
        """Put this practice on `target`, snapshotting its numbers onto their row.

        **The period is not restarted.** An upgrade mid-period raises the quota and leaves the
        window alone, so a practice that has already audited 480 of 500 invoices and moves to Pro
        immediately has 2,020 left rather than a fresh 2,500 and a period boundary in the middle of a
        month. Proration of the base fee is the other half of that decision and is deliberately not
        implemented — see `docs/BILLING.md`, which says so rather than leaving it to be discovered.

        Also creates the row when there is none, for the same reason `entitlement` does: "upgrade
        me" must work for a practice whose first action this is.
        """
        moment = utcnow()
        async with self.database.session() as session:
            record = await self._load(session, organization_id)
            if record is None:
                record = self._new_record(organization_id, moment)
                session.add(record)
                await session.flush()

            previous = record.plan_code
            record.subscription_tier = target.tier.value
            record.plan_code = target.code
            record.monthly_invoice_quota = target.monthly_invoice_quota
            record.overage_rate_cents = target.overage_rate_cents
            record.allow_overage = target.allow_overage
            record.updated_at = moment

            snapshot = self._snapshot(record)

        direction = (
            "unchanged"
            if previous == target.code
            else "changed"
        )
        log.info(
            "organisation %s plan %s %s -> %s by %s",
            organization_id,
            direction,
            previous,
            target.code,
            actor or "unknown",
        )
        return snapshot

    # --------------------------------------------------------------------------------------
    # the counter
    # --------------------------------------------------------------------------------------

    async def invoices_in(
        self, organization_id: str, *, since: datetime, until: datetime
    ) -> tuple[int, int]:
        """`(invoices_processed, requests)` for one practice over one window.

        Half-open — `since <= timestamp < until` — which is what makes consecutive periods partition
        the timeline instead of double-counting the instant they touch. `UsageStore.summarise` uses
        an inclusive end because it answers a different question (what have we used *so far*, where
        `until` is now), and both state their window.

        One aggregate over the composite index `0009` built for it. Never a fetch-and-sum: a busy
        month is tens of thousands of rows, and adding them up in the process would make the quota
        check slower the more a customer uses us.
        """
        async with self.database.session() as session:
            row = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(ApiUsageRecord.invoices_processed), 0),
                        func.coalesce(func.sum(ApiUsageRecord.request_count), 0),
                    ).where(
                        ApiUsageRecord.organization_id == organization_id,
                        ApiUsageRecord.timestamp >= since,
                        ApiUsageRecord.timestamp < until,
                    )
                )
            ).one()
        return int(row[0] or 0), int(row[1] or 0)

    async def check(
        self, organization_id: str, *, requested: int = 1, now: datetime | None = None
    ) -> QuotaDecision:
        """May this practice audit `requested` more invoices in the open period?

        The whole decision, in three states:

        * within quota — allowed, nothing owed beyond the base fee
        * above quota and `allow_overage` — allowed, and `overage_cents` says what it adds
        * above quota and not — refused, and the caller raises `429 QUOTA_EXCEEDED`

        `requested` is the *whole* request: one for a single audit, `len(members)` for an archive. A
        bulk upload is therefore refused as a unit rather than accepted and then truncated halfway
        through, which is the behaviour a partner can act on — a job that audited 180 of 300 files
        and stopped is a job somebody has to reconcile by hand.

        Raises nothing. The refusal is the caller's to raise, because only the caller knows which
        error envelope and which language belong on its endpoint.
        """
        moment = now or utcnow()
        entitlement = await self.entitlement(organization_id, now=moment)
        used, _ = await self.invoices_in(
            organization_id, since=entitlement.period_start, until=entitlement.period_end
        )

        # ---------------------------------------------------------------------------------
        # Exactness at the boundary, and only at the boundary.
        # ---------------------------------------------------------------------------------
        # `app.services.usage` buffers rows for up to `FLUSH_THRESHOLD` requests, so the `SUM`
        # above can be that far behind. Well inside the quota that does not matter — a practice at
        # 12 of 2,500 is not about to be refused either way, and flushing would put a database
        # write in front of every audit, which is the exact cost the buffer exists to avoid.
        #
        # Within a buffer's reach of the ceiling it matters a great deal: without this, a hard-stop
        # plan with a quota of 50 would let through 75, and the practice's own usage screen would
        # then disagree with the refusal they eventually got. So the check flushes *only* when the
        # buffered rows could change the answer, and re-reads once.
        #
        # `>=` rather than `>` on the margin, and `FLUSH_THRESHOLD` rather than the current buffer
        # depth, because the depth is this process's and there may be others. The threshold is the
        # per-process bound and is the honest figure to be conservative by.
        if used + requested + FLUSH_THRESHOLD >= entitlement.monthly_invoice_quota:
            # Imported here rather than at module scope: the meter is a process-wide singleton held
            # by `app.api.deps`, and a service that imported it at the top would make
            # `app.services.billing` unimportable without the API layer — which the store's own
            # tests rely on not being the case.
            from app.api.deps import usage_meter

            if usage_meter().pending:
                await usage_meter().flush()
                used, _ = await self.invoices_in(
                    organization_id,
                    since=entitlement.period_start,
                    until=entitlement.period_end,
                )

        quota = entitlement.monthly_invoice_quota
        remaining = max(0, quota - used)
        asked = max(0, requested)
        overage_invoices = max(0, (used + asked) - quota)
        overage_cents = overage_invoices * entitlement.overage_rate_cents
        reset_after = max(1, int((entitlement.period_end - moment).total_seconds()))

        allowed = overage_invoices == 0 or entitlement.allow_overage

        if not allowed:
            log.info(
                "organisation %s is over quota: %d used of %d, asked for %d more on plan %s",
                organization_id,
                used,
                quota,
                asked,
                entitlement.plan_code,
            )

        return QuotaDecision(
            allowed=allowed,
            entitlement=entitlement,
            used=used,
            requested=asked,
            remaining=remaining,
            overage_invoices=overage_invoices,
            overage_cents=overage_cents,
            reset_after=reset_after,
        )

    async def period_usage(
        self, organization_id: str, *, now: datetime | None = None
    ) -> PeriodUsage:
        """What the current period has cost so far. The read model behind the usage endpoint.

        `projected_total_cents` is what this period would come to **if nothing more happened** — the
        base fee plus the overage accrued so far. It is not a forecast: extrapolating from three
        days of a month would produce a number that changes every time somebody looks at it, which
        is worse than no number on a screen a practice checks an invoice against.
        """
        moment = now or utcnow()
        entitlement = await self.entitlement(organization_id, now=moment)
        processed, requests = await self.invoices_in(
            organization_id, since=entitlement.period_start, until=entitlement.period_end
        )

        overage_invoices = max(0, processed - entitlement.monthly_invoice_quota)
        overage_cents = overage_invoices * entitlement.overage_rate_cents
        base = plan_by_code(entitlement.plan_code)
        base_fee = base.base_fee_cents if base is not None else 0

        return PeriodUsage(
            entitlement=entitlement,
            invoices_processed=processed,
            requests=requests,
            remaining=max(0, entitlement.monthly_invoice_quota - processed),
            overage_invoices=overage_invoices,
            overage_cents=overage_cents,
            base_fee_cents=base_fee,
            projected_total_cents=base_fee + overage_cents,
        )

    # --------------------------------------------------------------------------------------
    # the invoices
    # --------------------------------------------------------------------------------------

    async def close_period(self, entitlement: Entitlement) -> BillingInvoiceRecord | None:
        """Price one ended period and write its invoice. `None` if it was already written.

        Idempotent through the unique index on `(organization_id, period_start)` rather than through
        a check-then-insert, because a check-then-insert is exactly the pattern that double-charges
        under concurrency: two requests both notice the period ended, both see no invoice, both
        write one. Here the second loses on the constraint and gets `None`, which the caller treats
        as "already done" — the correct reading, since the row that exists says the same thing this
        one would have.

        **A zero period still gets an invoice.** A practice on a free plan that audited nothing
        produces a `0`-total row, and that is deliberate: "August: nothing owed" and "August: no
        record" are different statements, and only the first can be reconciled against.
        """
        processed, _ = await self.invoices_in(
            entitlement.organization_id,
            since=entitlement.period_start,
            until=entitlement.period_end,
        )

        included = entitlement.monthly_invoice_quota
        overage_invoices = max(0, processed - included)
        overage_cents = overage_invoices * entitlement.overage_rate_cents
        catalog = plan_by_code(entitlement.plan_code)
        base_fee = catalog.base_fee_cents if catalog is not None else 0

        record = BillingInvoiceRecord(
            public_id=_invoice_id(),
            organization_id=entitlement.organization_id,
            period_start=entitlement.period_start,
            period_end=entitlement.period_end,
            plan_code=entitlement.plan_code,
            subscription_tier=entitlement.subscription_tier.value,
            base_fee_cents=base_fee,
            invoices_included=included,
            invoices_processed=processed,
            overage_invoices=overage_invoices,
            overage_rate_cents=entitlement.overage_rate_cents,
            overage_fee_cents=overage_cents,
            total_cents=base_fee + overage_cents,
            currency="EUR",
            status="ISSUED",
        )

        try:
            async with self.database.session() as session:
                session.add(record)
                await session.flush()
                session.expunge(record)
        except IntegrityError:
            log.debug(
                "period %s for organisation %s was already invoiced",
                entitlement.period_start.isoformat(),
                entitlement.organization_id,
            )
            return None

        log.info(
            "invoiced organisation %s for %s–%s: %d invoices, %d cents",
            entitlement.organization_id,
            entitlement.period_start.date(),
            entitlement.period_end.date(),
            processed,
            record.total_cents,
        )
        return record

    async def list_invoices(
        self, *, organization_id: str, limit: int = 24
    ) -> list[BillingInvoiceRecord]:
        """This practice's invoices, newest period first.

        Returns detached rows: the session is closed before they are read. Safe here and only here
        because every column is loaded eagerly (there is no relationship on this table) and the
        caller only projects them onto a response model.

        `limit` defaults to two years of monthly periods, which is more than any screen shows and
        bounded, so a long-lived practice cannot turn this endpoint into an unbounded response.
        """
        async with self.database.session() as session:
            rows = (
                (
                    await session.execute(
                        select(BillingInvoiceRecord)
                        .where(BillingInvoiceRecord.organization_id == organization_id)
                        .order_by(BillingInvoiceRecord.period_start.desc())
                        .limit(max(1, limit))
                    )
                )
                .scalars()
                .all()
            )
            session.expunge_all()
            return list(rows)

    # --------------------------------------------------------------------------------------
    # internals
    # --------------------------------------------------------------------------------------

    @staticmethod
    async def _load(session, organization_id: str) -> OrganizationBillingRecord | None:
        return (
            await session.execute(
                select(OrganizationBillingRecord).where(
                    OrganizationBillingRecord.organization_id == organization_id
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _new_record(organization_id: str, moment: datetime) -> OrganizationBillingRecord:
        """A fresh assignment on the pilot plan, with the period starting now.

        The period is anchored on the moment the practice first appeared rather than on the 1st of
        the month, which is what makes "billed on the 14th" possible without a second concept. The
        first period is therefore usually shorter than a month in wall-clock terms — it is not: it
        runs to the same day-of-month next month, which is exactly one period.
        """
        found = default_plan()
        start = moment
        return OrganizationBillingRecord(
            organization_id=organization_id,
            subscription_tier=found.tier.value,
            plan_code=found.code,
            monthly_invoice_quota=found.monthly_invoice_quota,
            overage_rate_cents=found.overage_rate_cents,
            allow_overage=found.allow_overage,
            current_period_start=start,
            current_period_end=_add_one_month(start),
            created_at=moment,
            updated_at=moment,
        )

    @staticmethod
    def _snapshot(record: OrganizationBillingRecord) -> Entitlement:
        """The row as a frozen value, with UTC re-attached.

        `as_utc` is not decoration: SQLite hands back exactly the naive datetime that was written,
        and the period arithmetic below subtracts it from an aware `utcnow()`. Without this the
        first comparison raises `TypeError` on the default database and works on Postgres, which is
        the worst possible distribution of a bug.

        An unknown `subscription_tier` string falls back to `free` rather than raising. The column is
        written only from `SubscriptionTier`, so a value outside it means a rollback past a tier this
        deployment knows — and refusing to describe a practice's entitlement is a worse answer than
        describing it conservatively.
        """
        try:
            tier = SubscriptionTier(record.subscription_tier)
        except ValueError:  # pragma: no cover - only reachable across a downgrade
            log.warning(
                "organisation %s has tier %r, which this deployment does not know; reading it as "
                "free. The quota comes from the row and is unaffected.",
                record.organization_id,
                record.subscription_tier,
            )
            tier = SubscriptionTier.FREE

        start = as_utc(record.current_period_start)
        end = as_utc(record.current_period_end)
        assert start is not None and end is not None  # both columns are NOT NULL

        return Entitlement(
            organization_id=record.organization_id,
            subscription_tier=tier,
            plan_code=record.plan_code,
            monthly_invoice_quota=record.monthly_invoice_quota,
            overage_rate_cents=record.overage_rate_cents,
            allow_overage=record.allow_overage,
            period_start=start,
            period_end=end,
        )

    async def _advance(self, entitlement: Entitlement) -> Entitlement:
        """Move the stored period one month forward. Called only after its invoice was written.

        The new start is the old **end**, not "now": periods have to abut exactly, or a practice's
        usage falls into a gap between two of them and is billed by neither.
        """
        start = entitlement.period_end
        end = _add_one_month(start)
        async with self.database.session() as session:
            record = await self._load(session, entitlement.organization_id)
            if record is None:  # pragma: no cover - the caller just read it
                return entitlement
            record.current_period_start = start
            record.current_period_end = end
            record.updated_at = utcnow()
            return self._snapshot(record)


def is_upgrade(current: SubscriptionTier, target: SubscriptionTier) -> bool:
    """Whether moving from `current` to `target` raises the entitlement.

    The one comparison between tiers that is legitimate, and it is here rather than at a call site so
    that `ORDER` has exactly one reader. Everything else asks about a limit — see rule 3 in
    `app.services.billing_plans`.
    """
    return ORDER[target] > ORDER[current]


def calendar_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    """The current calendar month in UTC, half-open. For callers that want a month, not a period.

    Kept beside the period logic so the difference between the two windows is visible in one place:
    `Entitlement.period_start` is the practice's billing anchor and this is the calendar. They are
    the same only for a practice that happened to sign up on the 1st.
    """
    moment = now or datetime.now(timezone.utc)
    start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, _add_one_month(start)


__all__ = [
    "MAX_PERIODS_PER_ROLL",
    "BillingStore",
    "Entitlement",
    "PeriodUsage",
    "QuotaDecision",
    "calendar_period",
    "is_upgrade",
]
