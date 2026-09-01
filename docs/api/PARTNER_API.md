# The partner API

The commercial surface: PADnext in, JSON out, authenticated by an API key. Written for an
integrator at a PVS vendor or a billing centre who has to make this work against their own export.

Everything below lives under `/api/v1/audit/*` and `/api/v1/settings/api-keys`. The rest of the
engine's endpoints (`/solve`, `/proposals`, `/padnext/*`) are the Azmoth web application's own and
are not part of this contract — they authenticate differently, they are not rate limited, and they
may change with the frontend that consumes them.

The machine-readable version of this document is the OpenAPI schema at `GET /openapi.json`, with an
interactive copy at `/docs`. It is committed at
[`packages/contracts/openapi/openapi.json`](../../packages/contracts/openapi/openapi.json), so a
client can be generated without a running engine.

**This file is being published as prose at `docs.azmoth.com/api/partner-api`** — the Fumadocs site
in [`apps/docs`](../../apps/docs), which replaced the orientation page the marketing site used to
carry. The page there is currently a stub that says so and links out; the migration is a matter of
moving the sections below into `apps/docs/content/docs/api/`. Until that is done this file is the
prose contract, and the OpenAPI schema is the binding one either way.

---

## 1. Authentication

Every request carries the key in a header:

```
X-API-Key: azm_live_ab12cd34ef56_9f4c…
```

**The key determines whose data the request sees.** There is no header, query parameter or body
field with which a caller can name an organisation — the tenant comes out of the stored key row.
A job created with one key is invisible to every other key, and asking for it answers `404` rather
than `403`, so a key cannot be used to discover that another practice's job exists.

### Getting a key

Keys are minted from the Azmoth web application by a signed-in member of the practice, through
`POST /api/v1/settings/api-keys`. That endpoint is behind the session rather than behind a key —
necessarily, since a first key cannot be issued to a caller who already has one.

```http
POST /api/v1/settings/api-keys
Content-Type: application/json

{ "name": "PVS-Export nächtlich" }
```

```json
{
  "token": "azm_live_ab12cd34ef56_9f4c…",
  "key_id": "ab12cd34ef56",
  "name": "PVS-Export nächtlich",
  "organization_id": "org7Kd2…",
  "created_at": "2026-08-30T09:14:22Z",
  "created_by": "usr_9f1…",
  "last_used_at": null,
  "revoked_at": null
}
```

> **`token` is shown exactly once and cannot be recovered.** Only its SHA-256 hash is stored, so
> nobody — including us — can show it to you again. Put it in your secret store now. If it is lost,
> mint another and revoke the old one.

`key_id` is the public half. It is what a log line names, what the rate limit counts against, and
what you pass to revoke the key. It cannot be used to authenticate.

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/v1/settings/api-keys` | Mint a key. Calling it twice gives **two live keys** — that is how a rotation is done: mint, deploy, revoke. |
| `GET` | `/api/v1/settings/api-keys` | This practice's keys, newest first, without their secrets. Revoked keys stay in the list and carry `revoked_at`. |
| `DELETE` | `/api/v1/settings/api-keys/{key_id}` | Revoke. Idempotent. Every request carrying the key is refused with `401` from then on; the row is kept, because "this key was live from March to July" is a question a billing dispute asks. |

`last_used_at` is accurate to about a minute — the column is deliberately not written on every
request. It answers "is anything still using this key", which is a question about days.

### Why this is not Better Auth's

Better Auth issues the *session* the web application runs on, so the obvious question is why the
partner API's credential is not its too. Two answers, and the second is the one that settles it.

**There is no such plugin at the version this repository pins.** `better-auth@1.7.1` — and `1.7.2`,
the current release — exports `admin`, `anonymous`, `bearer`, `jwt`, `organization`, `two-factor`,
`username` and fourteen others from `better-auth/plugins`. There is no `apiKey` among them, and no
`api-key` module in the distributed package. Nothing was passed over here; there was nothing to pass
over.

**And it could not do this job even if it existed.** Better Auth runs in the Next.js tier and
validates in JavaScript against its own tables. `X-API-Key` is verified by the **engine**, which is
Python, is the only thing a partner's integration talks to, and deliberately cannot query Better
Auth's tables — [`app/api/tenancy.py`](../../apps/engine/app/api/tenancy.py) explains at length why
it does not even check that an organisation exists. A credential the engine has to resolve on every
request has to live in a table the engine owns. That is the same argument
[`BILLING.md`](../BILLING.md) §3.2 makes about the subscription, reached from the credential side.

So the implementation is custom, and it is held to the properties a review would ask for:

| Property | Where |
|---|---|
| 192 bits from `secrets.token_bytes`, never `random` | [`services/api_keys.py`](../../apps/engine/app/services/api_keys.py) `generate_token` |
| Only a SHA-256 hash is stored; the token exists in exactly one response body | `ApiKeyRecord.key_hash`, and there is no code path that can re-read a token |
| Constant-time comparison, so the hash check is not a timing oracle | `hmac.compare_digest` in `verify` |
| One indexed lookup per request, not a scan hashing every row | the public `key_id` half, `unique=True` |
| Revocation is a column, and a revoked key's history survives | `revoked_at`; rows are never deleted |
| Malformed, unknown, wrong-secret and revoked are one indistinguishable `401` | `ApiKeyInvalid` — telling them apart is an enumeration oracle |
| Minting is behind a verified session, not behind a key | `app/api/settings_keys.py`, and see above on why it must be |
| The token is shown once, in a modal, with a copy button and a warning | `components/settings/new-key-dialog.tsx` |
| Revocation asks first | an `AlertDialog` in `components/settings/api-key-manager.tsx` |

**On SHA-256 rather than bcrypt or Argon2**, since that is the line a checklist usually flags: a
password KDF exists to make each guess expensive because human-chosen passwords come from a small
space. This secret is 192 random bits. There is no space to search, so the work factor would buy
nothing and would cost every authenticated request the same tens of milliseconds. What is required —
and is there — is the constant-time comparison.

The day Better Auth does ship an API-key plugin, the thing to reconsider is not the storage but the
**boundary**: a Better Auth JWT the engine verifies itself would replace both this credential and the
asserted `X-Organization-ID` header, and `tenancy.py` names the exact function that change lands in.

---

## 2. `POST /api/v1/audit/single` — one delivery, synchronously

**Input.** The PADnext delivery itself: a `*_padx.xml` payload or a `.padx` container. Either as
`multipart/form-data` in the field `file`, or as a raw request body.

```bash
# raw body
curl -X POST https://engine.example/api/v1/audit/single \
     -H "X-API-Key: $AZMOTH_KEY" \
     -H "Content-Type: application/xml" \
     --data-binary @00004711_20260726_ADL_000001_padx.xml

# multipart
curl -X POST https://engine.example/api/v1/audit/single \
     -H "X-API-Key: $AZMOTH_KEY" \
     -F "file=@00004711_20260726_ADL_000001_padx.xml"
```

**Output.** `200` with the complete audit report.

Below is the real response for the synthetic nine-error delivery bundled at
`logic/tests/cases/padnext/00004711_20260726_ADL_000001_padx.xml`, elided only where a list would
run for pages:

```jsonc
{
  "source_name": "00004711_20260726_ADL_000001_padx.xml",
  "positions": [ /* 9 entries: verdict, reason, proof, claimed and recomputed amounts */ ],
  "findings":  [ /* 11 entries: each with its legal basis and the rule id that produced it */ ],

  "claimed_total_eur":   "251.54",   // what the invoice charges
  "confirmed_fine_eur":   "24.25",   // green  — provably correct
  "confirmed_wrong_eur":  "88.49",   // red    — provably not chargeable as claimed
  "unconfirmed_eur":     "138.80",   // amber  — NOT a finding; see below
  "coverage_ratio": 0.4482,          // share of the money this audit could judge

  "receipt_hash": "bd8abb06ef7f0a4b…",  // SHA-256 over catalog, rules, logic, solvers, policy, input
  "catalog_version": "goae_official_snapshot_2026-07-25",
  "enforced_rule_count": 858,      // live figures — see the note below
  "advisory_rule_count": 9
}
```

Note what those numbers say about this engine and not about that invoice: **55 % of the money could
not be judged at all**. That is the honest state of coverage today, and it is why the amber bucket
is reported rather than folded away.

> **The two rule counts above move, and they are the only figures in this document that do.** They
> are reproduced from a real response so the example is checkable, and they are *not* a contract:
> read them from `rule_coverage_detail` on your own responses, or from `GET /api/v1/rules/coverage`.
> A regression test in this repository fails the build if the values printed here drift from what
> the engine computes, so they cannot go quietly stale — but your integration should not depend on
> them being any particular number.

Every euro amount is a **decimal string**, never a JSON number. Parse it with a decimal type. A
client that reads these into an IEEE double will lose cents, and cents are what a Rechnungsprüfer
checks.

### `200` is the answer even when the invoice is wrong

The HTTP status describes the API call, not the invoice. A report listing nine findings is a
successful audit. Non-2xx means **no report could be produced at all** — the body was not PADnext,
the delivery was coded against a different fee schedule, the rules engine was unavailable. A client
that treats findings as an error retries a request that worked.

### The three amounts are never one number

```
confirmed_fine_eur + confirmed_wrong_eur + unconfirmed_eur == claimed_total_eur
```

- **`confirmed_wrong_eur`** is the only figure that may be presented as exposure. Even then it is
  not a settled refund: a mutually exclusive pair puts *both* lines here, because the engine will
  not guess which one the practice meant to keep. Read it as "euros that cannot be billed as
  submitted".
- **`unconfirmed_eur` is not a finding against the practice.** It is the boundary of this engine's
  rule coverage — most of the exclusion rules were extracted from the GOÄ's prose automatically and
  are not enforced until a billing expert has verified them. At scale it will usually be the
  largest of the three.

Adding them together produces a "€X at risk" headline that is a false statement about somebody's
billing. Do not build one. `coverage_ratio` is the honest headline: it says how much of the invoice
was audited, not how much of it is wrong.

**Limits.** 5 MiB per delivery, 100 requests per minute per key.

### `schema_warnings` — when the deployment audits a non-conforming delivery anyway

Before a single position is read, the delivery's *framing* is checked against our subset of the
PADneXt v2.12 schema: root element, namespace, message type, the `anzahl` / `posanzahl` counters,
`behandlungsart`, and whether an `abrechnungsfall` has positions at all. What a failure costs is a
deployment setting, `PADNEXT_SCHEMA_POLICY`, and two fields on every report tell you which way it
was set:

| `schema_policy` | A delivery with bad framing | `schema_warnings` |
|---|---|---|
| `strict` *(default)* | `422 PADNEXT_SCHEMA_VIOLATION`; no report exists | always `[]` |
| `warn` | audited; every violation is also a finding | one string per violation |
| `off` | audited; the schema is never consulted | always `[]` |

```jsonc
{
  "schema_policy": "warn",
  "schema_warnings": [
    "Die Lieferung verstößt gegen das PADnext-Schema (line 10 at rechnungen/rechnung/abrechnungsfall/positionen): Element '{http://padinfo.de/ns/pad}positionen', attribute 'posanzahl': 'drei' is not a valid value of the atomic type 'xs:nonNegativeInteger'."
  ]
}
```

**Read both fields, not just one.** `schema_warnings: []` under `strict` means the delivery
conformed; under `off` it means nobody asked. Only `schema_policy` separates those.

The array is a top-level view of the findings already carrying
`type: "padnext_schema_violation"`, and the duplication is deliberate: a client has to be able to
answer "was this file conforming?" without walking a findings list that also holds every
position-level defect the audit exists to find — and the answer changes what the report means,
because under `strict` there would have been no report at all.

**`warn` changes nothing about how positions are judged.** A `goziffer` with no `@ziffer`, an
unreadable `faktor`, a position type this engine does not model: always a finding, never a refusal,
under every policy. And it does not relax `PADNEXT_ALLOW_REAL_DATA` — a delivery declaring
production patient data is still `REAL_DATA_REFUSED`.

Each affected delivery also emits one structured log line on our side
(`event: padnext_schema_violation`) naming every violation's rule, line, column and element path,
under the request id of the upload. If you are in the pilot and something was accepted that should
not have been, quote the `X-Request-ID` from your response and we can find it.

---

## 3. `POST /api/v1/audit/bulk` — many deliveries, in the background

**Input.** One `multipart/form-data` field `file`, holding a ZIP. Any `*.xml` or `*.padx` member at
any depth is audited; everything else — a `README.txt`, your export log, `__MACOSX/`, `*.auf` order
files — is skipped rather than refused.

```bash
curl -X POST https://engine.example/api/v1/audit/bulk \
     -H "X-API-Key: $AZMOTH_KEY" \
     -F "file=@august_2026.zip"
```

**Output.** `202`, immediately, before any auditing has happened:

```json
{
  "batch_id": "batch_4d980fa1c7b32e05",
  "status": "PENDING",
  "file_count": 128,
  "created_at": "2026-08-30T09:14:22Z"
}
```

`batch_id` is the `job_id` you poll with. `file_count` is already exact: the archive is opened and
checked **before** the response, so an unusable one is a `400` on the upload rather than a job that
fails thirty seconds later.

### `GET /api/v1/audit/bulk/{job_id}` — progress, then the result

Poll it. There is no webhook.

| `status` | Meaning |
|---|---|
| `PENDING` | Queued; no delivery has been audited yet. |
| `PROCESSING` | A worker has it. `processed_file_count` / `file_count` is the progress. |
| `COMPLETED` | Every delivery reached a verdict. `aggregate_summary` and each `files[].report` are populated. |
| `FAILED` | The **job** broke — see `error_message`. A delivery that could not be read is *not* this; that is a `FAILED` entry in `files`, and the rest of the archive is still audited. |

While the job runs, `files[].report` is `null`: a two-second poll over a hundred deliveries must not
ship a hundred full reports per tick. Once the status is `COMPLETED`, each entry carries exactly the
`PadnextAuditReport` that `/audit/single` would have returned for those bytes, and
`aggregate_summary` carries the roll-up with the same three-way split and the same identity.

`files` is sorted by `confirmed_wrong_eur` descending — riskiest first. The engine sorts it because
the amounts are exact decimal strings a client must not parse back into numbers to order them.

### `GET /api/v1/audit/bulk` — your jobs

Newest first, with the roll-up but without the per-delivery reports. It exists so that losing a
`job_id` does not lose the job. Supports `status`, `created_after`, `limit` (max 100) and `offset`;
`total` is recounted under the filters.

**Limits.** 50 MB per archive, 256 MiB expanded, 500 deliveries, 10 uploads per hour per key.

### Durability

The archive is written to disk before the `202` is sent, so a `202` is a promise that the work will
happen — an engine restarted mid-job resumes it rather than losing it, and the deliveries that
already had a verdict are not audited again. The archive is deleted once the job reaches a terminal
status: it stops being needed then, and a PADnext delivery is billing data about identifiable
treatment.

---

## 4. `POST /api/v1/audit/{job_id}/pdf` — the printable report

`200` with `application/pdf`, named `{job_id}_pruefbericht.pdf`. Only for a `COMPLETED` job; a
running one is `409`, because a partial roll-up printed onto paper is a number somebody reconciles
against three weeks later with no way to tell which moment it was a snapshot of.

The document carries the three amounts, the coverage ratio, every delivery sorted by risk, and the
engine identity the figures were produced under — catalog version and hash, rule state, logic state.
The sentence about `unconfirmed` being a coverage gap rather than a finding is printed beside the
number, because a PDF outlives the screen it came from.

It closes with the terms it has to: the report is a draft requiring a physician's release, not an
invoice; the data-protection basis; a contact address; and a ruled Freigabe line for the release to
be recorded on. Every page carries `Seite X von Y` and the report id, so a page separated from the
rest still says what it belongs to.

A4, 20 mm margins, Helvetica, no embedded fonts and no images — so it is a few kilobytes, the text
is selectable and searchable, and it prints correctly in monochrome. Nothing in it is distinguished
by colour alone.

Read-only and idempotent: the same job renders byte-identical output every time, because the
document dates itself by the job's completion rather than by the clock.

---

## 5. Errors

Every non-2xx response, from every endpoint, has the same body:

```json
{
  "error_code": "RATE_LIMIT_EXCEEDED",
  "message": "Ratenlimit erreicht: 100 Anfragen pro Minute … — Rate limit exceeded …",
  "details": { "limit": 100, "window_seconds": 60, "bucket": "single", "key_id": "ab12cd34ef56" },
  "retry_after": 37,
  "error": "rate_limit_exceeded",
  "status": 429,
  "detail": { "…the same fields…" }
}
```

**Switch on `error_code`.** It is stable. `message` is prose — German first for the practice,
English after for the integrator — and may be reworded. `details` carries the machine-readable
specifics for that code. `retry_after` is present only where retrying the identical request could
succeed, and is also sent as the standard `Retry-After` header.

The codes this API produces, with the complete catalog in
[`docs/errors.md`](../errors.md):

| Code | HTTP | What went wrong |
|---|---:|---|
| `UNSUPPORTED_INPUT_FORMAT` | 400 | Not PADnext — a PDF, a JSON wrapper, a bare archive on `/single`. `details.detected` says what it looked like. Decided by the leading bytes, so renaming a file does not change the answer. |
| `EMPTY_REQUEST_BODY` | 400 | Nothing arrived. |
| `INVALID_XML` | 400 | Not well-formed. `details.line`, `details.column`. |
| `ARCHIVE_UNREADABLE` | 400 | The ZIP could not be opened, or a member escapes the archive root. |
| `ARCHIVE_HAS_NO_DELIVERIES` | 400 | A valid ZIP holding no `*.xml` / `*.padx`. Usually a folder of invoice PDFs. |
| `API_KEY_REQUIRED` | 401 | No `X-API-Key`. |
| `API_KEY_INVALID` | 401 | Unknown, wrong or revoked. The three are deliberately indistinguishable. |
| `AUDIT_JOB_NOT_FOUND` | 404 | No such job **for this key**. |
| `AUDIT_JOB_NOT_COMPLETED` | 409 | A PDF was asked for before the job finished. `details.current_status`. |
| `REQUEST_TOO_LARGE` | 413 | Above the limit for that path. `details.max_bytes` is the one that applied. |
| `ARCHIVE_TOO_LARGE` | 413 | Too many deliveries, or expands past the ceiling. |
| `PADNEXT_SCHEMA_VIOLATION` | 422 | Not an ADL document this engine can audit. `details.violations[]` with line and column. |
| `UNKNOWN_ZIFFER` | 422 | **Every** GOÄ position is absent from the loaded catalog — almost always the wrong edition, not a typo. A delivery with only *some* unknown positions is audited normally. |
| `REAL_DATA_REFUSED` | 422 | The delivery declares production patient data and this deployment processes synthetic data only. |
| `RATE_LIMIT_EXCEEDED` | 429 | Budget spent. Honour `Retry-After`. |
| `RULES_ENGINE_UNAVAILABLE` | 503 | Ours. Retry once after the header's delay. |
| `UPLOAD_STORAGE_UNAVAILABLE` | 503 | The archive could not be stored; **the job was not accepted**. Retry. |

---

## 6. Rate limits

| Endpoint | Budget | Window |
|---|---|---|
| `POST /api/v1/audit/single` | `RATE_LIMIT_SINGLE_PER_MINUTE` (100) | one minute |
| `POST /api/v1/audit/bulk` | `RATE_LIMIT_BULK_PER_HOUR` (10) | one hour |

Per **key**, not per organisation. A second integration takes a second key, so a runaway loop in one
cannot spend the other's budget — and the answer to "why are we being throttled" is a `key_id` both
sides can look at.

Every successful response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
`X-RateLimit-Reset` (seconds until the window rolls). Read them and slow down before you are
refused; that is what they are for.

The bulk budget is two orders of magnitude tighter because one call can be 500 deliveries and 500
solver runs. The limit is on the work accepted, not on the requests made.

### A quota is not a rate limit, and they do not return the same error

The rate limit above protects the service. The **quota** — how many invoices your plan includes per
billing period — protects the invoice, and it is a different refusal:

| | `RATE_LIMIT_EXCEEDED` | `QUOTA_EXCEEDED` |
|---|---|---|
| HTTP | `429` | `429` |
| Counted per | key | organisation |
| Unit | requests | **invoices audited** |
| Clears by | waiting a minute | the billing period rolling, or a plan change |
| `Retry-After` | seconds | days |

**Do not back off on `QUOTA_EXCEEDED` the way you back off on a rate limit.** It carries an honest
`Retry-After` — the seconds until the period rolls — and a retry loop on it runs for weeks. Branch on
`error_code`.

`X-Quota-Limit`, `X-Quota-Remaining` and `X-Quota-Reset` are on every successful audit response, like
the rate-limit trio and for the same reason.

A bulk upload is checked **as a unit**: an archive of 300 deliveries with 40 invoices left in the
period is refused whole rather than audited part-way, because a job that stopped at file 180 is a job
somebody has to reconcile by hand.

`GET /api/v1/billing/usage` answers what is left, and reads with either a key or a session.
`POST /api/v1/billing/upgrade` needs a **session** — a key must not be able to escalate its own
entitlements — so a refused integration is resolved by somebody at the practice, not from the API.
[`BILLING.md`](../BILLING.md) has the whole model.

---

## 7. What this API is not

**It is not an invoicing system.** The report is an audit of an invoice somebody else produced. No
position is changed, nothing is submitted anywhere, and the practice remains responsible for what it
bills.

**Rule coverage is partial and the response says so.** `enforced_rule_count` is what can suppress a
position; `advisory_rule_count` is what only warns; `suppressed_unverified_rule_count` is what a
billing expert has not yet confirmed and which therefore does nothing.

Read those three as a statement about the *rule set*, and `coverage_ratio` as a statement about
*your invoice*. They are not the same measurement and the gap between them matters: almost every
rule is enforced today, and this engine could still only reach a verdict on 44.8 % of the bundled
example's money. The limit is **catalog reach** — a Ziffer no rule mentions cannot be judged however
thoroughly the rule set has been verified — not rule confidence. So `unconfirmed_eur` and
`coverage_ratio` are the boundary of the answer, and quoting an enforcement percentage as if it were
an audit percentage would overstate what you are buying.

**Synthetic data only, unless the deployment says otherwise.** A delivery flagged
`auftrag/@echtdaten="1"` is refused with `REAL_DATA_REFUSED`. Enabling production data requires a
lawful basis and the controls in
[`PRIVATE_DATA_WARNING.md`](../compliance/PRIVATE_DATA_WARNING.md); it is not a permission a client
can acquire by asking.
