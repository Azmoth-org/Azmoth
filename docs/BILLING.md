# Billing — quotas, plans and priced periods

**Status: implemented.** This document describes what the code does. Its companion,
[`MONETIZATION.md`](MONETIZATION.md), is the *proposal* that argued for it — which model, which
segment, what a price should be anchored to. Read that one for the commercial reasoning and this one
for the mechanism.

> ### ⚠ Before you quote a price from anything in this repository
>
> **The euro amounts in [`app/services/billing_plans.py`](../apps/engine/app/services/billing_plans.py)
> are placeholders.** They are round, obviously-provisional numbers whose only job is to let the
> machinery be built, tested and demonstrated. The invoice **quotas** are real in the sense that they
> come from `MONETIZATION.md` §3 Model A (1,000 / 10,000 / 100,000 invoices); the fees and overage
> rates are not.
>
> Setting them is a business decision. `billing_plans.py` is the single file it is made in, and
> §7 below says how to make it without breaking anything.

---

## 1. The one idea the whole system rests on

**The billable unit is one audited invoice.** Not one API call, not one megabyte, not one seat.

That is `MONETIZATION.md` §1's conclusion and it is worth restating because everything else follows
from it. Compute is not the cost driver — roughly 80 ms per invoice means one modest container audits
on the order of a million a month — so what a customer pays for is a GOÄ verdict they can defend to
an Erstattungsstelle. The unit of value is the invoice.

Before this work, the engine could not count them. `api_usage_logs` recorded one row per HTTP
request with `request_count` hard-coded to `1`, so a `POST /audit/single` carrying one invoice and a
`POST /audit/bulk` carrying three thousand were indistinguishable in the meter.
`bytes_processed` could not stand in: it is `Content-Length`, which measures ZIP compression.

`api_usage_logs.invoices_processed` closes that. It is the column every other part of this document
reads.

> **A naming note.** `MONETIZATION.md` §5.1 proposed calling this column `billable_units`. It shipped
> as `invoices_processed`, which is what the requirement asked for and is arguably the better name:
> it says *what* is counted rather than *that* it is countable, and there is exactly one billable unit
> in this product. Anywhere the proposal says `billable_units`, the code says `invoices_processed`.

---

## 2. The four moving parts

```
                       ┌─────────────────────────────────────────────┐
   an audit arrives    │ app/api/quota.py                            │
   ───────────────────▶│   check_and_refuse(org, requested=N)        │
                       └───────────────┬─────────────────────────────┘
                                       │
                       ┌───────────────▼─────────────────────────────┐
                       │ app/services/billing.py  BillingStore.check │
                       │   1. entitlement(org)  ← organization_billing│
                       │   2. SUM(invoices_processed) over the period │
                       │   3. allowed / charged / refused             │
                       └───────────────┬─────────────────────────────┘
                                       │ allowed
                       ┌───────────────▼─────────────────────────────┐
   the audit runs      │ observability.record_invoices(N)            │
                       │   → request context → _meter() → usage row  │
                       └───────────────┬─────────────────────────────┘
                                       │ period ends
                       ┌───────────────▼─────────────────────────────┐
                       │ BillingStore.close_period → billing_invoices│
                       └─────────────────────────────────────────────┘
```

| File | What it owns |
|---|---|
| [`app/services/billing_plans.py`](../apps/engine/app/services/billing_plans.py) | The price list. Append-only, in code, no table. |
| [`app/services/billing.py`](../apps/engine/app/services/billing.py) | Entitlements, the quota decision, period rolling, priced invoices. |
| [`app/api/quota.py`](../apps/engine/app/api/quota.py) | The gate every audit path calls, and the `429`. |
| [`app/api/billing.py`](../apps/engine/app/api/billing.py) | The four HTTP endpoints. |

---

## 3. Schema

Migration: [`20260831_0010_subscriptions_and_invoices.py`](../apps/engine/alembic/versions/20260831_0010_subscriptions_and_invoices.py).

### 3.1 `api_usage_logs.invoices_processed`

`INTEGER NOT NULL DEFAULT 0`. Invoices actually audited by the request that wrote the row: `1` for a
single audit, `N` for a bulk upload, `0` for a status poll, a listing, a usage read or an audit that
failed before any delivery was read.

Rows written before the migration read as `0`. That is the honest value — those requests were metered
before there was a unit to attribute to them, and backfilling a guess into a column an invoice is
built from would be inventing history.

### 3.2 `organization_billing` — one row per practice

The entitlement the quota check reads. `organization_id` is **unique**: one practice, one plan.

| Column | Why |
|---|---|
| `subscription_tier` | `free` \| `starter` \| `pro` \| `enterprise`. A label, denormalised from `plan_code` so "show me every Pro practice" is a query. |
| `plan_code` | The SKU with its revision — `pilot-2026.08`. What the numbers below were taken from. |
| `monthly_invoice_quota` | **Snapshotted** from the plan at assignment. See §4. |
| `overage_rate_cents` | Snapshotted. Euro cents, integer. |
| `allow_overage` | Snapshotted. Whether going over is charged or refused. |
| `current_period_start` / `current_period_end` | The open period, half-open. Stored, not computed — see §5. |

#### Why this is not `subscription_tier` on the `organization` table

Because `organization` is not ours. Better Auth computes its schema from the library's own field
definitions and creates it from the web tier (`pnpm --filter web auth:migrate`);
[`alembic/env.py`](../apps/engine/alembic/env.py) names it in the denylist precisely so autogenerate
cannot offer to drop every practice in the database. A billing column added there would be owned by
neither migrator and dropped by the next Better Auth upgrade.

It is also unreadable from where it is needed. **The quota is enforced in the engine**, on both audit
paths, and the engine deliberately cannot query Better Auth's tables —
[`app/api/tenancy.py`](../apps/engine/app/api/tenancy.py) explains at length why it does not even
check that an organisation *exists*. An entitlement consulted before every audit has to live in a
table Alembic owns, keyed by the organisation id. `doctor_profiles` and `practices` are here for the
same reason, reached from the identity side instead of the commercial one.

> `MONETIZATION.md` §5.3 proposed this table as `billing_accounts`, with `billing_email`,
> `hard_cap_units` and `contract_start`/`contract_end`. What shipped is a narrower table under a
> different name, because it is a different design: the snapshot semantics of §4 are not in the
> proposal, and the three contract columns describe an agreement rather than an entitlement and
> belong wherever contracts eventually live. The proposal's `hard_cap_units` is served by
> `allow_overage`: a plan that refuses above its quota *is* a hard cap at the quota.

### 3.3 `billing_invoices` — one row per closed period

`(organization_id, period_start)` is **unique**, and that constraint *is* the idempotency of closing
a period. A retry after a timeout is normal; double-charging a customer is not, so a second close
loses on the index rather than inserting a duplicate.

Every amount is stored rather than derived: `base_fee_cents`, `invoices_included`,
`invoices_processed`, `overage_invoices`, `overage_rate_cents`, `overage_fee_cents`, `total_cents`,
`currency`. Deriving `total_cents` on read would mean an issued figure could change when the rounding
in a helper changed, which is the one thing an amount somebody has been told must not do.

**This is not a Rechnung in the legal sense.** No VAT, no invoice-number series under § 14 UStG, no
payment terms, and nothing here is sent to anybody. It is the figure a real invoicing system — or a
person with a spreadsheet — is built from.

---

## 4. The rule that matters most: entitlements are snapshots

`organization_billing` stores `monthly_invoice_quota`, `overage_rate_cents` and `allow_overage`
alongside `plan_code`, duplicating what `billing_plans.py` already says.

**The duplication is the feature.** A practice's quota is what was agreed when they were put on the
plan. No later edit to the catalog, no rollback to an older deployment, and no plan removed from
`PLANS` can change it retroactively. The catalog is where a *new* assignment gets its numbers; the
row is where an existing one keeps them.

Three rules, in `billing_plans.py`'s own words:

1. **A plan is never modified once assigned; a new revision is added.** `starter-2026.08` becomes
   `starter-2026.11`, and practices on the old code stay on it until somebody deliberately moves
   them.
2. **What was agreed is snapshotted onto the assignment.** So even a violation of rule 1 cannot reach
   an existing practice.
3. **Entitlement is asked as a question about a limit, never about a plan name.** Nothing outside
   `billing_plans.py` branches on `tier == PRO`. Adding a tier is a data change, not a search through
   the codebase for comparisons.

Rules 1 and 3 come from the `data/arnon.dk/` corpus —
[`design-your-pricing-and-tools-so-you-can-adapt-it-later`](../data/arnon.dk/data/markdown/design-your-pricing-and-tools-so-you-can-adapt-it-later.md)
and
[`why-you-should-separate-your-billing-from-entitlement`](../data/arnon.dk/data/markdown/why-you-should-separate-your-billing-from-entitlement.md).
Rule 2 is what turns rule 1 from a convention into a guarantee.

---

## 5. Periods

A period is **stored**, not computed, and it is anchored on the day the practice was created. A
practice that first appeared on the 14th is billed on the 14th.

`GET /api/v1/settings/usage` reports the **calendar month** instead, and that is deliberate: "what
have we used this month" and "what will this period cost" are different questions. Both endpoints
state the window they used, and the settings UI prints both — two numbers that legitimately differ
are only confusing when neither says why.

`_add_one_month` clamps the day: 31 January + 1 month is 28 February (29 in a leap year), not 3
March. The wrong answer is not merely surprising — a period that overflowed into March would make the
*following* period start on the 3rd, and the practice's billing day would walk forward a few days
every year.

### Closing a period creates the invoice, and there is no scheduler

`BillingStore.roll` is called from the read and check paths, so **the first request of a new period is
what closes the previous one.** This stack has no Redis, no Celery, and a SQLite default whose single
writer makes a background task that transacts alongside requests actively unsafe — the same
constraint [`app/services/usage.py`](../apps/engine/app/services/usage.py) documents for its flush,
and it cost three test files failing at a distance to establish.

Consequences, stated plainly:

- A practice absent for three months gets three invoices when they next appear, each priced from the
  entitlement **as it was during that period** — the loop rolls one period at a time and prices each
  before advancing.
- A practice that never comes back gets no invoice. Correct: they also have no usage to bill.
- At most `MAX_PERIODS_PER_ROLL` (24) periods close per request. The rest close on the requests that
  follow, so a two-year absence is bounded per request rather than paying for 24 invoice writes at
  once.
- **A period with no usage still gets an invoice**, with a zero total. "August: nothing owed" and
  "August: no record" are different statements, and only the first can be reconciled against.

---

## 6. Enforcement

### Where the check runs

| Endpoint | How | Count |
|---|---|---|
| `POST /api/v1/audit/single` | FastAPI dependency | 1, before the body is read |
| `POST /api/v1/audit/bulk` | in the handler, after `inspect_archive` | `len(members)` |
| `POST /api/v1/padnext/audit` | in the handler, **only if a practice is named** | 1 |
| `POST /api/v1/padnext/batch` | in the handler, after the parts are read | `len(uploads)` |

The first is a dependency because the count is a constant and the tenant comes out of the verified
key, so a practice over its quota is refused without a 5 MB upload crossing the wire. The other three
cannot be: **the number of invoices is part of the request body.**

**A bulk upload is refused as a unit.** A job that audited 180 of 300 files and stopped because a
ceiling was reached mid-run is a job somebody reconciles by hand — worse for the practice than being
told up front that the archive does not fit in what is left of their period.

### `/padnext/audit` and the optional tenant

That endpoint is classified `UNSCOPED_BY_DESIGN` in `tests/test_tenancy.py`: it stores nothing, so
there is no row for a tenant to own, and its contract is frozen. Adding the tenant dependency would
turn every call without the header into a `403` — including `/demo`, which serves a visitor who has
not signed in.

So the tenant is read **optionally**. Every call the web tier proxies carries one (it comes from the
session — [`apps/web/lib/engine.ts`](../apps/web/lib/engine.ts)), so a signed-in reader's audit is
checked and counted; `/demo`'s visitor is not.

**The gap this leaves, stated rather than glossed:** a caller who can reach the engine directly and
omits the header gets a free audit. That is the *same* gap `tenancy.py` documents at length — the
engine authenticates nobody and must not be published to the browser — and it closes the same way,
with a token the engine verifies itself. It is not a new hole.

`POST /padnext/audit.pdf` is deliberately **not** counted, even though it runs a real audit: it
renders a report for a delivery already charged for once, and charging again for the printable copy —
or refusing the download because the quota ran out between reading the verdicts and printing them —
would be indefensible.

### The three outcomes

| State | Result |
|---|---|
| within quota | `200`, nothing owed beyond the base fee |
| over quota, `allow_overage` | `200`, and the overage is charged. An invoice line, not an outage. |
| over quota, not `allow_overage` | `429 QUOTA_EXCEEDED` |

`X-Quota-Limit`, `X-Quota-Remaining` and `X-Quota-Reset` are on every **successful** audit response
too, so a partner slows down or upgrades before being refused.

### `QUOTA_EXCEEDED` is not `RATE_LIMIT_EXCEEDED`

Both are `429` and they say opposite things about what the caller should do. A rate limit is a safety
valve on a Soufflé pool: wait a minute and the same request succeeds. A quota is a commercial
boundary: waiting works too, but the wait is up to a month, and what actually resolves it is a plan
change. **An integration that could not tell them apart would sit in a retry loop for three weeks and
call it a backoff.**

> **A deliberate divergence from the proposal.** `MONETIZATION.md` §5.4 specifies `QUOTA_EXCEEDED`
> as *"non-retryable, with no `Retry-After`"*. It shipped **with** one: the seconds until the billing
> period rolls.
>
> The reasoning. In this codebase `retry_after` means precisely "the same request may plausibly
> succeed later" ([`docs/errors.md`](errors.md), *The envelope*), and here it demonstrably will —
> the engine knows exactly when, because the period end is a stored column. Omitting the field would
> be withholding a fact the engine holds. What the proposal is guarding against is a client that
> retries in a tight loop, and a large honest number is a better defence against that than no number
> at all: a client honouring `Retry-After: 2419200` waits for the period, and a client ignoring it
> retries immediately and gets the same `429` either way.
>
> The distinction the proposal cares about is preserved where it matters — a **separate error code**,
> so a client can branch, plus a message naming the upgrade endpoint. If a partner integration is
> ever observed sleeping on this value in a way that breaks it, dropping the field is a one-line
> change in `app/api/quota.py`.

### The buffer, and exactness at the boundary

`app/services/usage.py` buffers usage rows for up to 25 requests or 15 seconds, so a naive
`SUM(invoices_processed)` can be that far behind. On a hard-stop plan that would let a quota of 50
through at 75 — and then have the practice's own usage screen disagree with the refusal they got.

So `BillingStore.check` flushes the meter **only when the buffered rows could change its answer**:
within `FLUSH_THRESHOLD` of the ceiling it flushes and re-reads, and anywhere else it does not. A
practice at 12 of 10,000 pays nothing for exactness it does not need; a practice at 49 of 50 gets an
exact answer. The buffer keeps its whole benefit on the hot path, and the one place its lag was
visible to a customer is gone.

### The counter is a query, not a column

There is no `invoices_used_this_month` anywhere. The figure is a `SUM` over the usage rows in the open
period, using the composite index `(organization_id, timestamp)` that migration `0009` created for
exactly this shape.

A running counter would be faster and wrong in a way that is very hard to find: a second source of
truth for a billable quantity, and the day it disagreed with the usage rows — a partial flush, a
retried transaction, a period boundary crossed mid-request — nobody could say which of the two a
customer should be charged from. Deriving it means **the usage screen and the refusal cannot
disagree, because they are the same query.**

---

## 7. Setting the real prices

One file: [`app/services/billing_plans.py`](../apps/engine/app/services/billing_plans.py).

**Do not edit an existing plan.** Add a revision:

```python
"starter-2026.11": Plan(
    code="starter-2026.11",
    tier=SubscriptionTier.STARTER,
    label="Starter",
    base_fee_cents=14_900,          # the new price
    monthly_invoice_quota=1_000,
    overage_rate_cents=22,
    allow_overage=True,
),
```

…and mark the one it replaces `selectable=False`. It stays in `PLANS`: the practices on it read their
own snapshot, an issued invoice still names it, and `plan_for_tier` will now resolve "Starter" to the
new revision for anybody signing up. Existing customers move when somebody deliberately moves them,
which is what avoids grandfathering a plan nobody can select.

`tests/test_billing.py` asserts the *arithmetic* and never a euro figure, precisely so that setting
real prices does not break the suite.

### What the pilot should produce as input to that decision

From `MONETIZATION.md` §4: invoices audited per customer per month, and the euro value of the
`confirmed_wrong_eur` bucket found. The second is the anchor — a price is defensible when it is a
visible fraction of the money the audit recovered.

**And never denominate a price in `unconfirmed_eur`.** That bucket is the limit of our own rule
coverage; charging against it would give us a commercial reason to keep coverage low.

---

## 8. During the pilot

Every practice starts on `pilot-2026.08`: **no fee, 10,000 invoices, overage allowed.** A pilot
practice is therefore never refused an audit for a billing reason, which is the correct behaviour for
a product being evaluated — and the usage is metered in full from the first request.

That combination is the point, and it is the thing a free pilot usually gets wrong. The conversation
that converts a pilot is *"you audited 3,140 invoices last quarter and we found €18,400 of confirmed
errors"*, and it cannot be had retroactively if nothing was counted. The corpus article on this is
[`pricing-ai-proofs-of-concept-free-pilots-will-kill-you`](../data/arnon.dk/data/markdown/pricing-ai-proofs-of-concept-free-pilots-will-kill-you.md).

The settings UI says so where a reader will see it: when the projected total is zero, the
subscription card prints that no costs arise during the pilot and that usage is recorded so a later
basis exists. A screen showing euro amounts nobody is being charged would be worse than one that
explains itself.

---

## 9. The API

All four are behind [`/api/engine/billing/*`](../apps/web/app/api/engine/billing) in the web tier.

| Endpoint | Credential | What |
|---|---|---|
| `GET /api/v1/billing/plans` | key **or** session | Selectable plans, cheapest first |
| `GET /api/v1/billing/usage` | key **or** session | The open period: tier, used, remaining, overage |
| `GET /api/v1/billing/invoices` | key **or** session | Closed periods, newest first |
| `POST /api/v1/billing/upgrade` | **session only** | Change plan |

The reads accept either credential through the same `resolve_reader` branch
`GET /api/v1/settings/usage` already uses: a partner has to be able to see what they are spending
without opening a browser, and a practice manager has to see it in the web application. Whichever
credential is presented decides the organisation, and **there is no parameter or path segment that
names one.**

`upgrade` is session-only, and the asymmetry is deliberate. It is a commercial commitment, and the
right authority for it is a signed-in member of the practice — not a bearer token sitting in a PVS
vendor's configuration file. It is the same boundary `POST /api/v1/settings/api-keys` sits behind, for
a related reason: **an API key must not be able to escalate its own entitlements.**

The practical consequence: a partner refused with `429 QUOTA_EXCEEDED` cannot resolve it from the
API. The refusal names the plan and the endpoint, and somebody at the practice does the upgrade. That
is the correct division — the person who pays should be the person who agrees to pay more.

### Changing plan mid-period

The period is **not** restarted. A practice that has audited 480 of 1,000 and moves to Professional
immediately has 9,520 left — not a fresh 10,000 and a period boundary in the middle of a month.

**Proration of the base fee is not implemented.** A mid-period upgrade is charged the new plan's full
base fee for that period. That is a simplification, not an oversight: proration needs a decision about
whether the old plan's quota is pro-rated too, and answering it wrongly is worse than answering it
later. It is the first thing a real payment integration has to settle.

**Downgrades are permitted.** The endpoint is called `upgrade` because that is the normal case; the
engine refuses no plan change. If consumption already exceeds the new quota, the new quota applies
immediately — on a plan without overage that means `429` until the period rolls.

---

## 10. What is deliberately not here

- **No payment.** No card, no SEPA mandate, no Stripe, no dunning, no VAT. `POST /billing/upgrade`
  records that a practice is on a plan; it does not collect money for it.
- **No `environment` column on `api_keys`** (`MONETIZATION.md` §5.2). A `test` key that meters but
  never bills is the right next step — the first thing a PVS integrator does is point their CI at us,
  and today that arrives as usage. It is not here because a second code path through an
  authentication check is a real cost and the pilot bills nothing anyway.
- **No `operation` or `billing_period` column on `api_usage_logs`** (§5.1). `endpoint` is doing the
  first job today and periods are attributed by timestamp against the practice's stored window, which
  is stable because periods abut exactly and are only advanced by `roll`. `billing_period` becomes
  worth its migration when a closed period has to be provably immutable against a *code* change, not
  just against a query.
- **No `batch_job_id` on the usage row** (§5.1). A disputed bulk count is currently reconciled through
  the job's own `batch_files` rows and the request id in the logs.
- **Rate limits are still `Settings`-wide, not per tier** (§5.4). The safety valve has to survive
  underneath any commercial limit, and adding a second source for it before a plan has actually been
  sold would be machinery with no customer.

### The honest ceiling on all of it

`app/services/usage.py` says it and it applies to everything above: **this is metering good enough to
price a pilot, not a financial ledger.** The write path buffers, so a process killed with a partial
buffer loses at most 25 rows or 15 seconds of traffic. The day an invoice built from it is disputed,
the buffer has to go and the write has to become synchronous and transactional with the request. That
is a deliberate future change and it is one line: flush on every record.

---

## 11. Tests

[`apps/engine/tests/test_billing.py`](../apps/engine/tests/test_billing.py) — 51 tests over the
catalog rules, period arithmetic, entitlement snapshots, the quota decision, the billable unit over
HTTP, the refusal on both audit paths, the four endpoints, and period close.

The properties worth knowing it protects:

- **the billable unit is invoices, not requests** — a bulk upload of three counts three invoices and
  one request;
- **a quota that says no actually says no**, on both audit paths, with a code distinguishable from a
  rate limit;
- **a catalog edit cannot reach a practice already on the plan**;
- **a period is closed exactly once**, enforced by the unique index rather than by a check somebody
  could remove;
- **the screen and the refusal are the same number** — a practice cannot be told "1 of 2 used" and
  then refused at 2.
