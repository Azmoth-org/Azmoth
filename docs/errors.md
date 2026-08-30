# Error catalog

Every non-2xx response this engine produces, what triggers it, and what a client should do about
it. The codes are a contract: `error_code` is stable and safe to switch on, `message` is prose that
may be reworded, and `details` carries the machine-readable specifics for that code and nothing
else.

The catalog lives in code as [`app/errors.py`](../apps/engine/app/errors.py) — `ErrorCode` is the
enum, and `tests/test_error_handling.py` fails if a value in it has no row in the table below. A
new code cannot ship undocumented.

## The envelope

Every error body, from every endpoint, has the same shape:

```json
{
  "error_code": "PADNEXT_SCHEMA_VIOLATION",
  "message": "The payload does not conform to the PADnext ADL schema: 2 violations…",
  "details": { "violation_count": 2, "violations": [{ "line": 12, "column": 8, "path": "…" }] },
  "retry_after": null,
  "error": "padnext_schema_violation",
  "status": 422,
  "detail": { "…the same four fields…" }
}
```

- **`error_code`** — SCREAMING_SNAKE, stable, one of the rows below. Switch on this.
- **`message`** — human-readable, German where a practice will read it, English where an integrator
  will. Do not parse it.
- **`details`** — an object whose keys depend on the code. Documented per row.
- **`retry_after`** — seconds, and `null` on every deterministic failure. When it is set, the same
  value is also sent as the standard `Retry-After` header.
- **`error`** and **`detail`** — the older spellings, emitted so clients written before this
  existed keep working. `error` is `error_code` lower-cased; `detail` mirrors the body. New code
  should read the top level.

## The catalog

| Error Code | HTTP | Trigger condition | Resolution / action for the client |
|---|---:|---|---|
| `EMPTY_REQUEST_BODY` | 400 | A body-taking endpoint received no body — usually a client that built the request wrong, or a proxy that dropped it. | Send the file as the raw request body. Do not retry unchanged. |
| `INVALID_XML` | 400 | The payload is not well-formed XML: an unclosed tag, a stray byte, a truncated upload. `details.line` / `details.column` point at it. | Fix the document at the given position and resend. A DOCTYPE is refused outright (entity-expansion risk) and reports here too. |
| `MALFORMED_CONTENT_LENGTH` | 400 | The `Content-Length` header is not an integer. Refused at the perimeter, before any body is read. | Fix the client's header handling. |
| `VALIDATION_ERROR` | 422 | The JSON body does not match the endpoint's schema. `details.errors` is Pydantic's error list: field path, failing value, reason. | Correct the named fields. Deterministic — retrying identical input returns the same 422. |
| `PADNEXT_UNREADABLE` | 422 | The delivery parsed as XML but is not a readable PADnext delivery: no `<rechnung>`, a container that will not open, a member that escapes the archive root, a size above the reader's own limits. | Read `message` — it names which of those it was. Re-export the delivery from the PVS. |
| `PADNEXT_SCHEMA_VIOLATION` | 422 | The payload is XML and is not an ADL document this engine can audit. Framing is fatal under `PADNEXT_SCHEMA_POLICY=strict`. `details.violations[]` carries `message`, `line`, `column` and a readable element `path` for each. | Fix the export against `padx_adl_v2.12`. To audit a 99 %-conforming file anyway, the deployment can set `PADNEXT_SCHEMA_POLICY=warn`, which turns every violation into a finding instead and reports them on the `schema_warnings` field of the report — see `docs/api/PARTNER_API.md`. |
| `UNKNOWN_ZIFFER` | 422 | **Every** GOÄ position in the delivery is absent from the loaded catalog. `POST /padnext/audit` only — the batch path reports a mismatched file as one low-coverage report among many rather than failing the upload. `details.unknown_ziffern` lists them, `details.catalog_version` names what they were checked against. | Almost always the wrong catalog edition, not a typo — check which GOÄ the delivery was coded against. A delivery with only *some* unknown positions is **not** an error: those are audited, marked `unknown_ziffer` and counted in the `unconfirmed` bucket. |
| `UNSUPPORTED_INPUT_FORMAT` | 400 | The body sent to `/api/v1/audit/single` or `/api/v1/audit/bulk` is not the format that endpoint takes — most often a PDF or a JSON wrapper. Decided by the leading bytes, never by the filename, so a PDF named `.xml` is caught. `details.detected` is what it looked like (`pdf`, `json`, `zip`, `unknown`, `empty`) and `details.accepted` is what that endpoint takes. | Send the PADnext delivery itself — a `*_padx.xml` or a `.padx` container — on `/audit/single`, or a ZIP of them on `/audit/bulk`. `400` rather than `415`: the `Content-Type` header was not the problem, the body was. |
| `REAL_DATA_REFUSED` | 422 | The delivery declares `auftrag/@echtdaten="1"` — production patient data — and this deployment processes synthetic data only. | Use test data. Enabling `PADNEXT_ALLOW_REAL_DATA` requires a lawful basis and the controls in [`PRIVATE_DATA_WARNING.md`](compliance/PRIVATE_DATA_WARNING.md). Not a permission the client can acquire. |
| `ECHTDATEN_UNDECLARED` | 422 | The delivery does not say whether it holds production data: `@echtdaten` is absent, empty, or a value the specification does not define (`"ja"`, `"yes"`, `"nein"`). An undeclared delivery is refused, not assumed to be test data. | Run [`scripts/anonymize_padnext.py`](../scripts/anonymize_padnext.py), which stamps `echtdaten="false"` on both the order file and the payload, and upload its output. Fixing the export to emit `echtdaten="0"` works too. See [`ANONYMIZATION_SPEC.md`](pilot/ANONYMIZATION_SPEC.md). |
| `ORGANIZATION_REQUIRED` | 403 | The request carries no `X-Organization-ID` header, and every proposal and batch endpoint needs one — each row belongs to exactly one practice and there is no default to fall back on. `details.header` names the header. | Send the active Better Auth organisation id. The web tier sets it on every call it proxies (`apps/web/lib/engine.ts`); a direct caller has to set it itself. `GET /health`, `GET /catalog`, the rules endpoints and `POST /padnext/audit` do **not** require it — the first three are not tenant data and the last stores nothing. Deterministic: the identical request fails identically. |
| `API_KEY_REQUIRED` | 401 | A request to `/api/v1/audit/*` carried no `X-API-Key` header, or an empty one. `details.header` names it. | Send the key. Mint one with `POST /api/v1/settings/api-keys` from a signed-in session — see [`api/PARTNER_API.md`](api/PARTNER_API.md). `401` here and `403` for `ORGANIZATION_REQUIRED` is not an inconsistency: this endpoint verifies a credential, so a caller who presents none has failed to authenticate. No `WWW-Authenticate` is sent, because the scheme is a bare header rather than one that header names. |
| `API_KEY_INVALID` | 401 | The key is malformed, unknown, has the wrong secret, or has been revoked. **All four answer identically**, with an empty `details` — telling them apart would let a caller enumerate issued key ids, or confirm one without holding its token. | Check that the key is still active with `GET /api/v1/settings/api-keys`; mint a new one if it was revoked. Deterministic — the identical request fails identically. |
| `RATE_LIMIT_EXCEEDED` | 429 · `Retry-After` | The API key has spent its budget for the current window: `RATE_LIMIT_SINGLE_PER_MINUTE` (100) on `/audit/single`, `RATE_LIMIT_BULK_PER_HOUR` (10) on `/audit/bulk`. `details.limit`, `details.window_seconds`, `details.bucket`, `details.key_id`. | Wait the `Retry-After` and retry — it is computed from when the window actually rolls over, not defaulted. `X-RateLimit-Limit` / `-Remaining` / `-Reset` are on every **successful** response too, so a client can slow down before it is refused. The budget is per key: a second integration takes a second key. |
| `REQUEST_TOO_LARGE` | 413 | The declared body exceeds the limit **for that path**: 5 MiB on `/api/v1/audit/single`, 50 MB on `/api/v1/audit/bulk`, `MAX_REQUEST_BYTES` (32 MiB) everywhere else. Refused before the body is read. `details.declared_bytes` and `details.max_bytes`, where `max_bytes` is the limit that actually applied. | Split the upload, or use `POST /api/v1/audit/bulk` (partner) or `POST /api/v1/padnext/batch` (web tier) for many files. A request sent with chunked transfer encoding carries no `Content-Length` and is refused by the handler instead, with the same code. |
| `CATALOG_NOT_FOUND` | 404 | A catalog edition was requested that is not on disk, or whose name could not be a directory name. `details.requested_version`, `details.available_versions`. | Pick one of `available_versions`. An unknown edition is never silently answered from another one — answering a question about one era with another era's money is the mistake this refusal exists to prevent. |
| `SOLVER_TIMEOUT` | 504 | Clingo hit `SOLVER_TIMEOUT_SECONDS` (default 5 s) **with no answer set at all**. `details.timeout_seconds`, `details.models_found` (always 0 here), `details.partial_result_available`, `details.positions_in_play`. | Retryable only in the sense that a smaller case or a longer ceiling would work; the identical request will time out again. See the partial-result note below. |
| `SOLVER_FAILED` | 500 | The ASP program failed to ground, has no answer set (the enforced rules contradict each other for this input), or produced no unique Steigerungsfaktor. | An engine defect, not a bad request. Report it with the case. The program text goes to the server log, never to the client. |
| `ENGINE_VALIDATION_DISAGREEMENT` | 500 | The independent validation pass contradicted the solver. `details.violations` is what it found. | Also an engine defect. **No draft is returned** — a disagreement is never resolved in favour of one side and shipped as an invoice. |
| `RULES_ENGINE_UNAVAILABLE` | 503 · `Retry-After: 5` | Soufflé could not be run or failed: binary missing, process could not be started, non-zero exit, or a 60 s evaluation timeout. | Retry once after the header's delay. If it persists, the deployment is missing its `souffle` binary — check the container image and `SOUFFLE_BIN`. |
| `TRANSIENT_DB_FAILURE` | 503 · `Retry-After: 5` | A database call failed on its **connection**, and `DB_RETRY_ATTEMPTS` (default 3) attempts with backoff all failed. `details.attempts`, `details.last_error`. | The write did **not** happen. Retry the identical request after the delay. |
| `INTERNAL_ERROR` | 500 | An exception nobody in this codebase named. | A bug. The response deliberately carries only the exception type; the detail is in the server log. |

Errors that are about the HTTP resource rather than the engine keep the codes the routes already
used, upper-cased into the same envelope: `PROPOSAL_NOT_FOUND` (404), `ILLEGAL_TRANSITION` (409,
with `details.current_status` / `details.requested_status`), `BATCH_NOT_FOUND` (404),
`BATCH_NOT_COMPLETED` (409), `RULE_NOT_FOUND` (404), `EMPTY_BATCH` (400), `EMPTY_FILE` (400),
`TOO_MANY_FILES` (413), `FILE_TOO_LARGE` (413), `BATCH_TOO_LARGE` (413).

The partner API adds seven of the same kind, and they are resource-shaped for the same reason — they
are facts about a job or an archive rather than about the engine:

| Code | HTTP | Trigger | Action |
|---|---:|---|---|
| `AUDIT_JOB_NOT_FOUND` | 404 | No such job **for this API key**. A job belonging to another practice answers the same way as one that never existed — a `403` would confirm the id exists, which is enough to enumerate uploads across tenants. `details.job_id`. | Check the id, or list your jobs with `GET /api/v1/audit/bulk`. |
| `AUDIT_JOB_NOT_COMPLETED` | 409 | A PDF was asked for on a job that is still `PENDING` / `PROCESSING`, or that `FAILED`. `details.current_status`. | Poll `GET /api/v1/audit/bulk/{job_id}` until `COMPLETED`. A partial roll-up is not printed with a caveat attached, because a caveat does not survive being pulled out of a folder three weeks later. |
| `ARCHIVE_UNREADABLE` | 400 | The bulk upload is not a ZIP whose directory can be read, or a member escapes the archive root (`../`, an absolute path). | Re-create the archive. Refused before any job is written, so there is nothing to poll and nothing to clean up. |
| `ARCHIVE_HAS_NO_DELIVERIES` | 400 | A readable ZIP holding no `*.xml` or `*.padx` member. Almost always a folder of invoice PDFs. | Zip the PADnext exports, not the printed invoices. Other files in the archive (a `README.txt`, a PVS log, `__MACOSX/`, `*.auf` order files) are skipped rather than refused. |
| `ARCHIVE_TOO_LARGE` | 413 | More than `MAX_BULK_ARCHIVE_MEMBERS` (500) deliveries, or an archive that expands past `MAX_BULK_UNCOMPRESSED_BYTES` (256 MiB). `details.limit`, `details.observed`. | Split the upload. The expansion ceiling is checked twice — against the declared sizes before anything is read, and against the real bytes as each member is extracted, because a declared size is a number the archive's author wrote. |
| `UPLOAD_STORAGE_UNAVAILABLE` | 503 · `Retry-After: 30` | The archive could not be written to `UPLOAD_DIR`. **The job was not accepted** — no row exists and nothing will be processed. | Retry. If it persists the deployment's upload volume is missing or not writable; `/srv` is deliberately read-only to the runtime user in the container image, so `UPLOAD_DIR` has to point at a mounted volume. |
| `API_KEY_NOT_FOUND` | 404 | `DELETE /api/v1/settings/api-keys/{key_id}` named a key this organisation does not have. `details.key_id`. | Check the id against `GET /api/v1/settings/api-keys`. Revoking an already-revoked key is **not** an error — it succeeds and leaves the original `revoked_at` alone. |

## Two things the table cannot say in a cell

### A partial solve is a 200, not a 504

`SOLVER_TIMEOUT` fires only when the ceiling expired with **no model at all**. That case must never
be served as an invoice: an empty result is indistinguishable from "nothing is chargeable", which
is a different and much more dangerous statement.

A solve that *is* cut short but has already found a model returns **`200`** with:

- `solver_status: "TIMEOUT_PARTIAL"` on the proposal and in the audit trail,
- `solver_timed_out: true`,
- a `solver_timeout_partial` warning stating in German that optimality was not proved.

Every hard constraint still held — exclusions, Zielleistung, the § 5 factor bands are integrity
constraints that no timeout can trade away. What is unproven is only whether the *best* of the
legally equivalent alternatives was chosen. So the partial result is returned, labelled, and a
reviewer decides. That is the "partial result handling" a client should implement: check
`solver_timed_out` on a 200 before treating the draft as final.

### What is retried, and what is deliberately not

Retries live in [`app/core/retry.py`](../apps/engine/app/core/retry.py) — exponential backoff with
full jitter, attempts counted in total, nothing hidden from the caller.

| Operation | Retried | Attempts | Why |
|---|---|---:|---|
| Database call, connection invalidated | yes | `DB_RETRY_ATTEMPTS` (3) | A failover drops the socket; a second attempt gets a fresh connection. The transaction rolled back, so nothing was half-written. |
| Database call, integrity or missing table | **no** | 1 | A unique violation is a fact about the data. The third attempt reaches the same answer. |
| Soufflé process fails to *start* (`OSError`) | yes | 3 | `ENOMEM`, a full process table — host conditions that clear on their own. |
| Soufflé exits non-zero | **no** | 1 | The program ran and rejected its input. Deterministic. |
| Soufflé evaluation timeout | **no** | 1 | The ceiling is 60 s; two more attempts would hold the request open for three minutes to fail anyway. |
| Clingo solve | **no** | 1 | In-process and deterministic. A timeout retried is a timeout paid twice. |
| Anything answering 4xx | **no** | 1 | The request is wrong. Retrying it is load without a chance of a different answer. |

Full jitter rather than a fixed schedule is not decoration: the failure being protected against is
a database restart, and a restart releases every waiting worker at once. Identical backoff would
send them all back in the same millisecond and knock it over again.

**Clients should honour `Retry-After` and retry at most once or twice.** The engine has already
spent its own attempts before the 503 reached you.
