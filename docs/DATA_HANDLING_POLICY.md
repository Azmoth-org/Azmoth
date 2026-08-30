# Data handling

What Azmoth stores when you send it an invoice, where it goes, how long it stays, and what it
refuses to accept. One page, because the person who needs it — a practice manager, a billing
centre's data protection officer, a PVS vendor's architect — has to be able to read all of it
before deciding whether to send us a file.

Written against what the code actually does. Every claim below names the module or setting that
enforces it, so it can be checked rather than believed.

> **Status: this describes a system processing synthetic and anonymised data.** It is not a
> substitute for a Vertrag zur Auftragsverarbeitung (Art. 28 DSGVO), and Azmoth has not yet
> completed one. Processing production patient data requires that contract, a documented lawful
> basis, and the controls in
> [`compliance/PRIVATE_DATA_WARNING.md`](compliance/PRIVATE_DATA_WARNING.md). See
> [§ 5](#5-production-data-is-refused-by-default).

---

## 1. What we store

| What | Where | How long |
|---|---|---|
| The uploaded `.zip` of a bulk job | Local disk under `UPLOAD_DIR` | Until the job reaches `COMPLETED` or `FAILED` — then deleted |
| A single-file audit's XML | **Nowhere.** Held in memory for the request | Not stored at all |
| The audit result (JSON per delivery, plus the roll-up) | Postgres, `batch_jobs` / `batch_files` | Indefinitely, until you ask us to delete it |
| API keys | Postgres, `api_keys` — **SHA-256 hash only** | Until revoked; the row is kept, the secret never existed here |
| Unhandled errors | Postgres, `error_log` — type, message, route, request id, tenant | Diagnostic; safe to purge on a schedule |
| Request logs | The container's stdout | Whatever your log retention is |

**`POST /api/v1/audit/single` writes nothing.** The delivery is parsed in memory, audited, and the
report is returned. No row, no file, nothing to delete afterwards. If that is the property you need,
it is the endpoint to use.

## 2. What the audit itself reads out of a delivery

The reader does not parse patient identity. It extracts what the GOÄ rules turn on:

- the charged positions — Ziffer, factor, amount, date, `begründung` text, `punktzahl`;
- the case's `behandlungsart` / `vertragsart` and any `minderungssatz`;
- the delivery's message type, version and `echtdaten` flag.

Name, address, date of birth and insurance number are **not read into any structure the engine
holds**, and therefore do not appear in a report, in the database, or in a log
(`apps/engine/app/padnext/reader.py`). They may still be present in the XML file you upload, which
is why a bulk job's archive is treated as patient data for as long as it exists on disk.

## 3. Where it is stored, and who can reach it

- **On our infrastructure only.** No third-party processor receives your data. There is no
  analytics service, no external logging service, and no AI provider in any request path — the
  engine calls no external API while auditing (`EXTRACTION_MODE=manual` is the only supported mode
  and the engine holds no model).
- **Postgres**, on an encrypted volume, reachable only from the engine container on a private
  network. It is not published to the internet.
- **Uploads** go to a mounted volume (`/var/lib/azmoth/uploads` in the shipped compose files), owned
  by the engine's unprivileged runtime user. The rest of the application image is read-only to that
  user by design.
- **Tenant isolation is enforced on every query**, not by convention. Each API key carries its
  organisation in the database, and every read filters on it; a job belonging to another practice
  answers `404`, so a key cannot even be used to discover that one exists
  (`apps/engine/app/api/apikeys.py`, `apps/engine/app/api/tenancy.py`).

## 4. Retention, and how deletion actually happens

**Uploads are deleted when the job finishes.** `RETAIN_BULK_UPLOADS=false` is the default and the
deletion happens on the transition to `COMPLETED` or `FAILED` — the moment the bytes stop being
needed, not on a timer. Setting it to `true` keeps archives for debugging a failing integration; it
is an operator decision with a data-protection consequence and should be turned off again.

**An interrupted job keeps its archive**, deliberately: that is what lets it resume after a restart
instead of being lost. Such an archive is deleted when the resumed job finishes.

**Results are kept until you ask.** We do not currently expire them, because an audit is a record a
practice may need to produce months later. Deletion on request is a manual operation today
(`DELETE FROM batch_jobs WHERE organization_id = …` cascades to the per-file rows); a
self-service endpoint is planned and is not built.

**Logs and `error_log` hold no invoice content.** No request bodies, no uploaded filenames, no
header values beyond the request id, and no traceback locals. `error_log` stores the exception type,
its message, the route template, the request id and the tenant — enough to answer "what broke for
this customer" without anyone needing clearance for patient data to read it.

## 5. Production data is refused by default

A PADnext delivery declaring `auftrag/@echtdaten="1"` — production patient data — is **rejected**
with `422 REAL_DATA_REFUSED`. It is not audited, not stored, and not logged beyond the refusal.

`PADNEXT_ALLOW_REAL_DATA=false` is the default and the shipped compose files set it explicitly.
Changing it is not a configuration preference: it requires a signed Auftragsverarbeitungsvertrag, a
documented lawful basis, and the technical and organisational measures described in
[`compliance/PRIVATE_DATA_WARNING.md`](compliance/PRIVATE_DATA_WARNING.md). It is not a permission a
caller can obtain by asking.

**Anonymised exports still need checking.** A PVS export prepared as "test data" may carry
`echtdaten="1"` from the source system regardless of whether the patient fields were scrubbed — the
flag describes the export, not the content. If your anonymised file is refused, that is why, and the
fix is in the export rather than in our configuration.

## 6. Limits we enforce

| Limit | Value | Setting |
|---|---|---|
| Single delivery | 5 MiB | `MAX_SINGLE_XML_BYTES` |
| Bulk archive | 50 MB | `MAX_BULK_ZIP_BYTES` |
| Archive expanded | 256 MiB | `MAX_BULK_UNCOMPRESSED_BYTES` |
| Deliveries per job | 500 | `MAX_BULK_ARCHIVE_MEMBERS` |
| Requests | 100/min single, 10/hour bulk, per key | `RATE_LIMIT_*` |

Archives are checked against their declared sizes before anything is read, and against the bytes
that actually come out as each member is extracted — a declared size is a number the archive's
author chose.

## 7. Sub-processors

**None.** If that changes, this section names them before it happens.

An error-tracking hook exists (`app.core.observability.set_error_hook`) so a deployment *can* wire
up Sentry or an equivalent. Nothing is registered by default, and no such dependency is installed.
If one is enabled it receives the exception, the request id, the route and the tenant — the same
fields `error_log` holds, and no invoice content — and it becomes a sub-processor that belongs in
the table above and in your Verzeichnis von Verarbeitungstätigkeiten.

## 8. What we are missing, stated plainly

An honest policy names its gaps rather than leaving a reader to find them.

- **No Auftragsverarbeitungsvertrag yet.** Required before any production data, from anyone.
- **No self-service deletion endpoint.** Deletion on request is manual.
- **No automatic retention expiry** on audit results.
- **No encryption of individual columns.** Protection is at the volume and network level; a
  database administrator can read stored reports.
- **No formal penetration test**, and no SOC 2 or ISO 27001 certification.
- **Backups are the deployment's responsibility.** The shipped compose files use a named Docker
  volume for Postgres; a restore has to be tested by whoever operates it.

---

*Questions about this document, or a request to delete data: contact the operator of your Azmoth
deployment. Last reviewed when the partner API shipped; it is updated in the same pull request as
any change to what is stored.*
