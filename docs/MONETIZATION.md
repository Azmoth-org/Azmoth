# B2B monetisation — pricing models and what the schema still needs

**Status: proposal, partly implemented.** §§1–4 — which model, which segment, what a price is
anchored to — are still a proposal and still the right place to argue about it. §5's schema and §6's
order of work have largely shipped; **[`BILLING.md`](BILLING.md) describes what the code actually
does**, including where it deliberately diverges from what is recommended below.

| §6 step | Status |
|---|---|
| 1. a billable unit on `api_usage_logs`, and write it | **shipped** as `invoices_processed` (§5.1 proposed `billable_units`); `operation`, `billing_period` and `batch_job_id` deferred — see `BILLING.md` §10 |
| 2. `environment` on `api_keys` | not done |
| 3. surface invoices-audited in `/settings/api-keys` | **shipped** — the subscription card's usage meter |
| 4. quotas and `QUOTA_EXCEEDED` | **shipped**, ahead of the order given here, as `organization_billing` rather than `billing_accounts`. `QUOTA_EXCEEDED` carries a `Retry-After`, against §5.4's recommendation; `BILLING.md` §6 gives the reasoning |

The original note stands for what remains: the schema change is the kind that is very cheap now and
very expensive after the first invoice has been sent.

---

## 1. What is actually billable

The engine does three things a customer would pay for, and they have very different cost and value
profiles:

| Operation | Endpoint | Shape | Marginal cost |
|---|---|---|---|
| Single audit | `POST /api/v1/audit/single` | Synchronous, one PADnext delivery | ~80 ms of CPU (`docs/performance_baseline.md`) |
| Bulk audit | `POST /api/v1/audit/bulk` | Asynchronous, one ZIP containing *N* deliveries | ~80 ms × *N*, plus storage for the job |
| Printable report | `POST /api/v1/audit/{job_id}/pdf` | Render of a result already computed | Rounding error |

The first thing to take from that table is that **compute is not the cost driver.** Eighty
milliseconds per invoice means a single modest container audits on the order of a million invoices a
month. Whatever we charge, we are not charging for CPU — we are charging for a GOÄ verdict that
somebody can defend to an Erstattungsstelle. Pricing therefore has to be value-anchored, and the
value unit is **one audited invoice**. Not one API call, not one megabyte, not one seat.

The second thing is that the PDF must never be a separate line item. It is the artefact the customer
actually shows a colleague, and metering it teaches them to avoid producing it.

---

## 2. The blocking problem: we can meter requests, but not invoices

This is the finding that matters most, and it should be fixed before any commercial conversation
gets specific.

Usage is recorded in one place — `_meter()` in `apps/engine/app/core/observability.py`, called from
HTTP middleware — and it writes **one row per HTTP request**, with `request_count` hard-coded to 1.
The middleware sits above the handler and has no idea what was in the body.

So today:

- A `POST /audit/single` for one invoice writes `request_count = 1`. Correct, by luck.
- A `POST /audit/bulk` carrying a ZIP of **3,000 invoices** also writes `request_count = 1`.

`bytes_processed` cannot stand in for the count either: it is `Content-Length`, so it measures ZIP
compression, not invoices. A customer whose deliveries compress well would be billed less than one
whose deliveries do not, for identical work.

The count *does* exist — `batch_files` holds one row per delivery in a job — but there is no column
anywhere joining a usage row to a batch job, so reconstructing "how many invoices did this billing
centre audit in August" means a query that cannot be written. **An Abrechnungsstelle will not accept
an invoice denominated in HTTP requests**, and neither will their auditor.

Everything in §4 follows from closing this gap.

---

## 3. Three models

### Model A — Tiered subscription with an invoice quota

A monthly platform fee including a fixed number of audited invoices, with a per-invoice overage rate
above it.

```
Starter      €      /mo    1,000 invoices included   overage € /invoice
Professional €      /mo   10,000 invoices included   overage € /invoice   + API access
Enterprise   negotiated  100,000+                    + SLA, dedicated catalog pinning
```

- **For:** predictable revenue; the customer's finance department can budget it; overage converts
  growth into revenue without a renegotiation.
- **Against:** a quota needs enforcement, a reset job, and a story for what happens at 100 % — three
  pieces of machinery that do not exist yet.

### Model B — Pay-per-invoice, no commitment

A single per-invoice rate, billed monthly in arrears, with volume breakpoints.

- **For:** the shortest possible path from a free pilot to a first euro. No quota machinery: the
  meter *is* the bill. It is also the only model that is honest about a partial rule catalog — a
  customer pays for exactly what they ran.
- **Against:** revenue is invisible until the month closes, and it prices identically for a customer
  who audits 200 invoices and one who audits 200,000 — which undersells the second badly.

### Model C — Wholesale platform licence (per connected practice)

An annual platform fee plus a per-practice rate, with invoice volume uncapped or very generously
capped.

- **For:** this is the only shape a PVS vendor can actually buy. A PVS resells to hundreds of
  practices under a fixed licence of its own and **cannot pass a variable per-invoice cost
  through** — a model that makes their COGS move with their customers' billing activity will be
  rejected in procurement, not negotiated down.
- **Against:** it decouples our revenue from load, so one PVS with heavy practices can cost real
  money. Needs a fair-use ceiling, not a hard cap.

---

## 4. Recommendation

**Two price lists, because these are two different businesses.**

| Segment | Model | Why |
|---|---|---|
| **Abrechnungsstellen** (billing bureaux) | **A — tiered subscription, invoice-metered, with overage** | Their volume is knowable and seasonal, they already buy software this way, and the quota is what turns "we tried it on a few files" into a committed monthly number. Overage means a busy quarter is upside instead of a renegotiation. |
| **PVS vendors** | **C — platform licence + per-practice** | They are a channel, not an end user. Their procurement needs a fixed, forecastable cost per practice; a per-invoice rate makes our price a variable in *their* margin, which is the objection that ends the deal. |

**Model B is the pilot's exit ramp, not a segment.** Offer it to every pilot participant at
graduation: it needs no quota machinery, so it can ship the day metering is fixed, and it converts a
free user into a paying one without asking them to forecast a volume they have never measured. Move
them onto Model A at renewal, once the meter has told both sides what their real volume is.

**On the numbers.** The rates above are deliberately blank. I have no German market benchmarks for
GOÄ audit tooling, and inventing figures in a document that will be quoted back is exactly the
failure `apps/marketing/src/lib/engine-facts.ts` exists to prevent. What the pilot should produce is
the input to that decision: invoices audited per customer per month, and the euro value of the
`confirmed_wrong_eur` bucket found. The second number is the anchor — a price is defensible when it
is a visible fraction of the money the audit recovered or the write-off it prevented.

**Pricing must never be denominated in the amber bucket.** `unconfirmed_eur` is the limit of our own
rule coverage, and charging against it would give us a commercial reason to keep coverage low. Bill
on invoices audited; that is a number whose incentives point the right way.

---

## 5. Schema changes

### 5.1 `api_usage_logs` — make a row billable

| Column | Type | Why |
|---|---|---|
| `billable_units` | `INTEGER NOT NULL DEFAULT 0` | **The one that unblocks everything.** Invoices actually audited by this request: `1` for `/audit/single`, `N` for a bulk job, `0` for a PDF render or a failed call. Separate from `request_count`, which stays what it is — a count of HTTP calls, which is an operational number, not a billing one. |
| `operation` | `VARCHAR(32) NOT NULL DEFAULT ''` | Normalised billing category — `audit.single`, `audit.bulk`, `report.pdf`. `endpoint` is a URL path and URL paths get versioned and renamed; a price list must not break when `/api/v1/` becomes `/api/v2/`. |
| `batch_job_id` | `VARCHAR(64) NULL` | The audit trail for `billable_units` on a bulk row. When a customer disputes a count, this is what joins to the `batch_files` rows that justify it. No foreign key, for the same reason `api_key_id` has none. |
| `billing_period` | `CHAR(7) NOT NULL` (`YYYY-MM`) | The period this row was *assigned to*, stamped at write time. Deriving the period from `timestamp` at query time means a later change to the month boundary or the timezone silently re-bills a closed month. A period that has been invoiced must be immutable. |

Index: `(organization_id, billing_period)` — that is the invoice query, and it does not want to scan
a timestamp range.

**One correctness note on where `billable_units` gets written.** The middleware cannot know it — for
bulk it is not even known yet when the `202` is returned. Either the handler puts the count into the
request context for `_meter()` to read, or the bulk completion path writes a second usage row when
the job finishes. The second is more honest: it bills work that actually completed, and a job that
fails halfway then bills for the files it audited rather than the files it was handed.

### 5.2 `api_keys` — two columns, and deliberately not the quota

| Column | Type | Why |
|---|---|---|
| `environment` | `VARCHAR(16) NOT NULL DEFAULT 'live'` | `test` keys meter but never bill. Without this, the first thing a PVS integrator does — point their CI suite at us — arrives as an invoice, and the first commercial conversation is a refund. |
| `label_purpose` *(optional)* | `VARCHAR(64) NULL` | Which system a key belongs to, for a per-integration usage breakdown a customer can act on. `name` is free text a human typed. |

**`monthly_quota` and `overage_rate` do not belong on `api_keys`,** and it is worth being explicit
about why, since they are the obvious place to put them. A customer has several keys — one per PVS
instance, one per environment, one rotated last week — and the quota is the **organisation's**, not
the key's. Putting it on `api_keys` means either duplicating it across every key of one customer and
keeping the copies in step, or having the quota silently reset when a key is rotated. Both are the
kind of bug that is discovered by a customer reading their bill.

### 5.3 New table: `billing_accounts` — one row per organisation

```sql
CREATE TABLE billing_accounts (
    id                      UUID        PRIMARY KEY,
    organization_id         VARCHAR(256) NOT NULL UNIQUE,
    plan                    VARCHAR(32)  NOT NULL DEFAULT 'pilot',
    -- Model A / C. NULL included-units means uncapped (Model B, pure per-invoice).
    monthly_included_units  INTEGER      NULL,
    overage_rate_cents      INTEGER      NULL,
    currency                CHAR(3)      NOT NULL DEFAULT 'EUR',
    -- Refuse rather than bill above this. NULL = no cap. A runaway integration
    -- should hit a 429 with a quota reason, not produce a five-figure surprise.
    hard_cap_units          INTEGER      NULL,
    contract_start          DATE         NOT NULL,
    contract_end            DATE         NULL,
    billing_email           VARCHAR(320) NOT NULL,
    created_at              TIMESTAMPTZ  NOT NULL,
    updated_at              TIMESTAMPTZ  NOT NULL
);
```

`plan` on `api_keys` would be a denormalised copy of `billing_accounts.plan`; resolve it through
`organization_id` instead.

### 5.4 Rate limits become tiers

`apps/engine/app/api/ratelimit.py` currently enforces 100/min for single audits and 10/hour for bulk,
per key, from `Settings`. Its own module docstring already anticipates this: *"A sliding window is
the right change the day the limit becomes a billing tier rather than a safety valve."* That day is
the day Model A ships. Two consequences:

1. The limits must be read from `billing_accounts` with the `Settings` values as the floor, not
   instead of it — the safety valve has to survive underneath the commercial limit.
2. A quota refusal and a rate-limit refusal are **different errors**. `RATE_LIMIT_EXCEEDED` means
   "retry shortly"; a quota refusal means "retry next month, or call sales", and returning the first
   for the second sends integrators into a retry loop that will never succeed. This needs a new
   `error_code` in `docs/errors.md` — `QUOTA_EXCEEDED`, non-retryable, with no `Retry-After`.

---

## 6. Order of work

1. **`billable_units` + `operation` + `billing_period` on `api_usage_logs`, and write them.**
   Nothing commercial can be decided before the meter is right, and every month it stays wrong is a
   month of pilot usage data that cannot be used to set a price.
2. `environment` on `api_keys`, so pilot and CI traffic are separable from day one.
3. Surface invoices-audited-per-month in `/settings/api-keys` — the customer seeing the number
   before it appears on a bill is what prevents the first dispute.
4. `billing_accounts`, quotas and `QUOTA_EXCEEDED` — only once a plan has actually been sold.

Steps 1–3 are worth doing regardless of which model wins. Step 4 is not, which is why it is last.
