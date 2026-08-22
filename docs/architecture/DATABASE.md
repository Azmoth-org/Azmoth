# The database

Four tables, in two unrelated pairs.

`proposals` / `audit_events` is the approval record: one holds a proposal and the decision taken on
it, the other is the append-only log of what happened to it. `batch_jobs` / `batch_files` is the
batch PADnext audit: one upload of many deliveries, and one row per delivery in it.

Everything else the engine reads (the catalog, the rule tables, the logic programs) is versioned
input, and the result cache is content-addressed and disposable.

The two pairs are deliberately unalike, and the difference is worth stating before the column
listings. A proposal records that a **human took responsibility** for a billing draft, so what it
holds is written once and every decision on it is logged. A batch job records a **computation the
engine ran on its own**: its status moves as work proceeds, each file's verdict is written when it
lands, and re-uploading the same files simply produces another batch. There is nothing there for an
audit log to protect and no approval boundary to enforce — which is exactly why `batch_jobs` and
`batch_files` are plain mutable rows and `proposals` is not.

Before this, the proposal store was a Python dictionary. The module that held it argued the case
against a database: inventing a schema would mean inventing the retention policy, the access-control
model and the audit log alongside it, and all three are legal questions before they are engineering
ones. Half of that was right. The half that was backwards is the audit log — it is not a reason to
postpone a database, it is what a database is *for*, and an approval that dies with the process
cannot answer the one question a billing system must always be able to answer: **who accepted this,
and when.** Retention and access control are still open, and are still tracked as open in
[`../compliance/PRIVATE_DATA_WARNING.md`](../compliance/PRIVATE_DATA_WARNING.md) — but they are now
open *above* a durable record rather than instead of one.

---

## `proposals`

One row per solve. Written once by `create_proposal`; only the lifecycle columns are ever updated.

| column | type | notes |
| --- | --- | --- |
| `id` | `uuid` PK | surrogate key. The audit log's foreign key points here, not at the public id. |
| `proposal_id` | `varchar(64)` **unique**, indexed | the public `prop_<hex>` id the API returns and the frontend holds. |
| `case_id` | `varchar(128)`, indexed | the caller's own identifier for the encounter. Nullable. |
| `status` | `varchar(16)`, indexed | `DRAFT` \| `APPROVED` \| `REJECTED` \| `EXPORTED`. |
| `receipt_hash` | `varchar(64)`, indexed | SHA-256 over catalog, rule tables, logic, solver versions, policy, input **and** output. |
| `input_hash` | `varchar(64)` | SHA-256 over the canonical clinical input alone. |
| `catalog_version`, `catalog_sha256` | `varchar` | which fee schedule was loaded, and its content hash. |
| `rules_version`, `rules_hash` | `varchar` | the rule tables, hashed rather than merely versioned. |
| `logic_version` | `varchar(64)` | SHA-256 of `goae_rules.dl` + `goae_optimize.lp`. |
| `solver_version`, `rules_engine_version` | `varchar` | Clingo and Soufflé. |
| `solver_result_json` | `jsonb` | the full `CodingResponse` — extraction, coding, audit trail, proof trees. |
| `warnings_json` | `jsonb` | |
| `missing_documentation_json` | `jsonb` | |
| `rule_coverage_json` | `jsonb` | the coverage snapshot. The five counts the API flattens are read back out of this. |
| `cached` | `boolean` | whether the response this row was built from came from the result cache. |
| `created_at` | `timestamptz` | |
| `approved_at`, `approved_by` | `timestamptz`, `varchar(256)` | |
| `rejected_at`, `rejected_by`, `rejected_reason` | `timestamptz`, `varchar(256)`, `varchar(2048)` | |
| `exported_at` | `timestamptz` | |

Indexes: `case_id`, `status`, `receipt_hash`, `proposal_id` (unique), and a composite
`(status, created_at)` — the list endpoint is *"the most recent proposals, optionally in this
status"*, and both halves of that in one index means the common query does not sort a table scan.

### Why `id` and `proposal_id` are both there

The primary key is a UUID because that is what a foreign key should be. The public id is
`prop_<16 hex>` because that format is already in a shipped API contract, and 16 hex characters
cannot be recovered from a 32-character UUID — so it cannot be derived from the key. Changing the
wire format to suit the schema would be a breaking change to a client that is not asking for one, so
both exist. The store looks rows up by `proposal_id`; nothing above the store sees the UUID.

### What is written once and never rewritten

Everything above `created_at`. A decision touches only the status and the lifecycle stamps — never
the receipt, never the versions, never the solver output. That is what makes *"this receipt hash is
what was approved"* a checkable statement instead of a hopeful one, and there is a test that
snapshots every identity column across an approve-then-export and asserts it did not move.

### Four columns the `Proposal` response does not return

`input_hash`, `rejected_at`, `rejected_by` and `exported_at` are written and queryable but absent
from the `Proposal` response model. Adding them would have changed the OpenAPI document, and the
contract for the persistence migration was that the document does not move — the frontend must not
be able to tell that the backend changed. `rejected_by` in particular is not lost: it is the actor
on the `REJECTED` audit event, which is where "who rejected this" belongs anyway. (It used to be
*genuinely* lost — the old in-memory `transition()` accepted a `reason` but no `by` for a
rejection, so the API validated a required `rejected_by` and then dropped it.)

All four do appear in the **export** document, and that is the right place for them: an export is
read on its own, detached from this database, so a field that a live client can look up by other
means is a field an archived file has no way to recover. `input_hash` especially — comparing two
exports for "same case, different engine state" is impossible from the API responses alone.

### `receipt_hash` vs `input_hash`

They answer different questions and both are needed.

- **`receipt_hash`** — *"was this produced by exactly this engine state from exactly this input?"*
  It covers the data, the logic, the solver versions, the policy, the input and the output. It is
  comparable within an engine version and not across one, by design; see
  `app/services/receipt.py`, whose behaviour this migration does not touch.
- **`input_hash`** — *"is this the same case?"* Just the canonical clinical input. A catalog bump
  moves every receipt hash while leaving this one alone, which is what makes "find every proposal
  for this case" answerable after an upgrade.

`input_hash` is computed in the store rather than in the pipeline, precisely so that it did not have
to become a field on the response.

---

## `audit_events`

Append-only. One row per thing that happened to one proposal.

| column | type | notes |
| --- | --- | --- |
| `id` | `uuid` PK | |
| `proposal_id` | `uuid`, indexed, FK → `proposals.id` `ON DELETE CASCADE` | |
| `event_type` | `varchar(16)`, indexed | `CREATED` \| `VIEWED` \| `APPROVED` \| `REJECTED` \| `EXPORTED` |
| `actor` | `varchar(256)` | who did it. Never empty. |
| `timestamp` | `timestamptz`, indexed | |
| `metadata_json` | `jsonb` | context: the rejection reason, the approval note, the status it came from. |

Plus a composite `(proposal_id, timestamp)` — the audit view for one proposal, in order, is the only
read this table has to be fast at.

### Append-only is enforced, not documented

The ORM refuses an `UPDATE` or a `DELETE` on the mapper (`app/db/models.py::_reject_mutation`), so a
service method that tried to "fix up" an event raises `AuditLogIsAppendOnly` in the developer's own
test run rather than quietly rewriting the record a reviewer will be shown. A correction has to be a
new event, which is the point.

The database should enforce it too, and that half is **not** in the migration:

```sql
REVOKE UPDATE, DELETE ON audit_events FROM <application_role>;
```

It is left out deliberately. Alembic runs as the schema owner, and a grant against a role this
repository cannot know the name of would either fail or, worse, apply to the wrong role. It belongs
with the deployment's role definitions.

### `actor`, and what it does not mean

There is no authentication in this service. `approved_by` is a string the caller supplies, and a
read cannot be attributed at all — so a `VIEWED` event carries `anonymous`, and a `CREATED` event
carries `system` because a solve is not a person.

`EXPORTED` carries whatever `exported_by` the export request supplied, and that field is required
for the same reason `approved_by` is: an export is a thing a person or a named integration did, and
the log has to be able to say which. It used to default to `system`, which was right while the only
caller was `ProposalStore.export_proposal` and wrong the moment a human could press a button.

`anonymous` is deliberately conspicuous. An audit log full of it is a visible statement that access
control is still missing, which is exactly the gap
[`../compliance/PRIVATE_DATA_WARNING.md`](../compliance/PRIVATE_DATA_WARNING.md) lists. Writing a
plausible-looking name there instead would be the one genuinely dangerous option.

### The export is built inside the transaction that records it

`POST /api/v1/proposals/{id}/export` does three things in one unit of work: it moves the row to
`EXPORTED`, writes the `EXPORTED` audit event, and assembles the downloadable JSON document from
that same row — all before the commit. The obvious alternative, transition and then read the row
back, is wrong in two ways. The file could disagree with the record it claims to describe, and a
read that failed *after* a successful transition would leave a proposal permanently `EXPORTED` with
no file ever delivered — unrecoverable, because `EXPORTED` is terminal and there is no second
attempt.

That is what `_transition`'s `project` parameter exists for, and it has exactly one caller. The
lifecycle check and the row lock are the part that must not be duplicated: a second write path that
forgot either would let two people export one proposal.

The document carries `input_hash`, which no API response returns, and the full audit log *including
the `EXPORTED` row the export itself just wrote*. Self-describing on purpose — a document whose log
stops at `APPROVED` cannot show that it is the export it claims to be.

### A batch export is not a decision, and is not logged

`POST /api/v1/padnext/batch/{id}/export` changes no status and writes no audit row. It renders a
computation that already finished, so the same ZIP can be downloaded repeatedly and is byte-identical
each time; there is nothing for a second export to contradict. `audit_events` is keyed to a proposal
anyway — if batch access ever needs logging it needs its own table, not a foreign key bent to fit.

Only a `COMPLETED` batch can be exported. A running one would produce totals that are a snapshot of
an unidentifiable moment and a `FAILED` one has no roll-up at all; both are `409`.

### `VIEWED` is opt-in

Every transition reads the row before it writes it. If that read logged, every `APPROVED` event
would have a `VIEWED` event in front of it and the log a reviewer actually reads would be half
noise — so only `GET /api/v1/proposals/{id}` passes `record_view=True`. The approval already proves
somebody looked.

---

## The lifecycle, and where it is enforced

```
DRAFT ──approve──▶ APPROVED ──export──▶ EXPORTED
  │
  └───reject────▶ REJECTED
```

`REJECTED` and `EXPORTED` are terminal. The check lives in the store, not the router:

- the row is locked (`SELECT … FOR UPDATE`, a no-op on SQLite, which has no row locks and does not
  need them), then read, then checked, then written — all in one transaction. Without the lock, two
  simultaneous approvals both read `DRAFT`, both pass and both write, leaving one proposal with two
  approvers and a log recording both as having taken responsibility;
- the audit event is written in the **same** transaction as the status change. A status that moved
  without a matching event, or an event without the change, would each be a record nobody can
  defend;
- an illegal transition raises `IllegalTransitionError`, which the router turns into **HTTP 409**
  with `current_status` and `requested_status` in the body. Nothing is written — the log records
  what happened, not what was attempted and refused.

There is no `delete_proposal` and no eviction. The old dictionary dropped its oldest entry past 512
to bound memory; a durable store that silently discarded approvals would be worse than one that ran
out of disk, because only one of those is noticed.

---

## `batch_jobs`

One batch upload: many PADnext deliveries audited in the background, and the roll-up across them.
Written by `app/services/batch_audit.py`, behind `POST /api/v1/padnext/batch`.

| column | type | notes |
| --- | --- | --- |
| `id` | `uuid` PK | surrogate key; `batch_files` references this |
| `batch_id` | `varchar(64)`, **unique**, indexed | the public handle, `batch_<16 hex>` |
| `status` | `varchar(16)`, indexed | `PENDING` \| `PROCESSING` \| `COMPLETED` \| `FAILED` |
| `created_at` | `timestamptz` | |
| `completed_at` | `timestamptz`, nullable | set when the job reaches a terminal status |
| `aggregate_summary_json` | `jsonb`, nullable | the serialised `BatchAggregateSummary` |
| `error_message` | `text`, nullable | why the *batch* failed — not why a file did |

Plus a composite `(status, created_at)`, the same shape as the one on `proposals` and for the same
query: "the most recent batches, optionally in this status".

`id` and `batch_id` are both present for the same reason `proposals` carries both — see
[Why `id` and `proposal_id` are both there](#why-id-and-proposal_id-are-both-there).

### `FAILED` is narrower than it looks

A run in which every single file was unreadable is `COMPLETED`, not `FAILED`. The useful output of
such a run is a hundred per-file error messages a user needs to read, and a status that says
"nothing to see" would hide them. `FAILED` means the batch *machinery* broke — the background task
raised before it could finish, or a write would not land — and it is the one case where
`aggregate_summary_json` stays null on a finished job, because a total computed over rows that may
never have been written is worse than no total at all.

### The roll-up is stored, not recomputed

`aggregate_summary_json` holds the answer the batch reached, so a later change to how aggregation
works cannot silently restate a finished job. It carries `failed_file_count` inside itself, not only
on the row around it: the summary covers the files that were audited, and read on its own six months
later it still has to say what it is missing.

It also keeps the three honest buckets separate rather than reducing them to one figure, and at
batch scale that matters more than it does for a single invoice — `unconfirmed_eur` summed over a
year of billing is a six-figure number that describes *this engine's rule coverage*, not the
practice. See [`app/schemas/batch.py`](../../apps/engine/app/schemas/batch.py).

---

## `batch_files`

One uploaded delivery inside a batch, and the report it produced.

| column | type | notes |
| --- | --- | --- |
| `id` | `uuid` PK | |
| `batch_job_id` | `uuid`, indexed, FK → `batch_jobs.id` `ON DELETE CASCADE` | |
| `filename` | `varchar(512)` | as uploaded. **Not** unique within a batch |
| `status` | `varchar(16)`, indexed | `PENDING` \| `COMPLETED` \| `FAILED` |
| `report_json` | `jsonb`, nullable | the full `PadnextAuditReport`, as `/padnext/audit` would return it |
| `error_message` | `text`, nullable | why this delivery could not be audited |

Plus a composite `(batch_job_id, filename)` — the background task walks one job's files, and the API
reads them all back.

The uploaded **bytes are not stored**. They live in the accepting process's memory for the length of
the job and nowhere else; nothing here writes a billing document to disk. `filename` is display and
audit-trail only and never touches the filesystem, so a `../` in it is a curiosity rather than a
traversal.

`report_json` is stored whole for the same reason `proposals.solver_result_json` is: a normalised
copy re-serialised by later code is a different document, and the report carries its own
`receipt_hash` over the catalog, rules, policy and verdicts that produced it.

### There is no `PROCESSING` for a file

Files are audited one after another, and the move out of `PENDING` is a single write at the end of
each file's audit. A per-file in-progress state would be a second write per file bought for nothing:
the job's own `PROCESSING` already says work is happening, and the count still `PENDING` already
says how much is left.

### `BackgroundTasks` is not durable, and the schema shows it

A batch is processed in the same process that accepted it, so a restart mid-run leaves a row on
`PROCESSING` with some files still `PENDING` and nothing to resume it. That is the price of the
MVP's no-Celery, no-Redis constraint, and it is stated rather than hidden: `GET` reports the real
state, the web app stops polling after fifteen minutes and says why, and re-uploading the files
produces a fresh batch. A durable queue is the fix when one is wanted.

---

## Postgres in production, SQLite locally

`DATABASE_URL` is a SQLAlchemy **async** URL, so the driver is part of the value:

| environment | URL |
| --- | --- |
| production | `postgresql+asyncpg://user:pw@host:5432/db` |
| local dev | `sqlite+aiosqlite:///./test.db` (the default) |
| the test suite | `sqlite+aiosqlite:///:memory:` (forced in `tests/conftest.py`) |

SQLite is a real database and it does survive a restart, so this is not about persistence. It is
about the deployment claim: one writer, one file inside a container that is replaced on every
deploy, no replication, no encryption at rest. **Under `APP_ENV=production` the engine refuses to
start on anything but Postgres** (`app/db/session.py::assert_production_database`) — a warning would
be read once and forgotten; a refusal cannot be. `staging` and `development` are unrestricted.

Both dialects are supported for real, not nominally: `JSONVariant` is `JSONB` on Postgres and
portable `JSON` elsewhere, `Uuid` is native on Postgres and `CHAR(32)` elsewhere. The one difference
that is *not* papered over is time. `TIMESTAMP WITH TIME ZONE` round-trips an aware datetime on
Postgres; SQLite has no timestamp type and hands back exactly the naive value it was given. So
everything is written in UTC and `app.db.models.as_utc` re-attaches the timezone on read — treating
that naive value as local time is the classic way to make an audit log an hour wrong, twice a year.

---

## Running migrations

Everything below is run from `apps/engine`, where `alembic.ini` lives.

### Locally, with nothing set up

Nothing to do. `DATABASE_URL` defaults to a SQLite file and `DATABASE_AUTO_CREATE` defaults to true,
so `uvicorn app.main:app` and `pytest` create their own tables:

```bash
cd apps/engine
.venv/bin/uvicorn app.main:app --port 8000     # creates ./test.db on first start
.venv/bin/python -m pytest                     # in-memory, per test, nothing left behind
```

`create_all` is refused under `APP_ENV=production`: a schema that appeared without a migration has
no rollback, and its migration history claims a revision it is not at.

### Locally, against Postgres

```bash
docker compose -f infra/docker/docker-compose.yml up -d postgres

cd apps/engine
export DATABASE_URL=postgresql+asyncpg://govatax:govatax@localhost:5432/govatax
python scripts/migrate.py            # waits for the server, then upgrades to head
python scripts/migrate.py --check    # report the revision, change nothing; exit 1 if behind
```

or with Alembic directly — same `DATABASE_URL`, same result:

```bash
alembic upgrade head        # apply everything
alembic current             # what revision this database is at
alembic history --verbose   # the full history
alembic downgrade -1        # undo the last migration
```

`alembic.ini` deliberately has **no** `sqlalchemy.url`. `alembic/env.py` reads `DATABASE_URL`
through the same `app.config.Settings` the service uses, so a migration cannot be applied to a
different database than the one the engine will then talk to — and no connection string, with its
password, is ever committed.

> A database created by `create_all` has no revision stamp, so `alembic upgrade head` against it
> will try to create tables that already exist. Delete the SQLite file, or `alembic stamp head`,
> before switching a dev database over.

### In a container

The image's entrypoint runs the migration before the server, whatever `command:` it is given:

```
scripts/docker-entrypoint.sh → python scripts/migrate.py --wait 60 → exec uvicorn …
```

An `ENTRYPOINT` rather than a chained `CMD`, because `docker-compose.yml` overrides `command:` to add
`--reload`, and a `CMD ["sh","-c","migrate && uvicorn …"]` would be replaced wholesale by that
override — silently skipping migrations in the environment where the schema changes most often.
`RUN_MIGRATIONS=false` skips the step, for a pipeline that migrates in its own job.

So `docker compose up` is the whole story:

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

Postgres comes up, its healthcheck passes, the engine migrates and starts. `docker compose down`
stops the stack and keeps the data; `down -v` deletes the `govatax-postgres-data` volume, which
holds approval records — a decision, not a side effect of stopping.

### Adding a migration

```bash
cd apps/engine
# edit app/db/models.py, then:
alembic revision --autogenerate -m "what changed"
```

Then **read the generated file**. Three things autogenerate gets wrong or cannot know:

1. It emits `postgresql.JSONB(astext_type=Text())` with `Text` unqualified and not imported — a
   `NameError` on import, on every dialect. It has to be `sa.Text()`.
2. It cannot see a rename. It emits a drop plus an add, which loses the data.
3. It does not know `audit_events` is append-only. A migration that rewrites audit rows is a
   compliance event, not a schema change.

`tests/test_db_persistence.py::test_the_migration_and_the_models_describe_the_same_schema` runs
`alembic upgrade head` and `Base.metadata.create_all` into two scratch databases and compares
tables, columns, nullability, primary keys, foreign keys and index names. It exists for the ordinary
drift: somebody adds a column, the suite passes because it uses `create_all`, and the deploy runs
`alembic upgrade head` against a schema that does not have it.

---

## Testing

The suite forces `sqlite+aiosqlite:///:memory:` in `tests/conftest.py`, at import time, before
`app.main` is imported. That is both a safety measure — an inherited `DATABASE_URL` cannot make the
suite write test proposals into a real database — and the isolation mechanism: for SQLite the
connection *is* the database, so every new engine gets an empty one and a test cannot see the rows of
the test before it.

`tests/test_db_persistence.py` is the exception. Durability cannot be tested against an in-memory
database, because closing the connection *is* the restart and it takes the data with it — so those
tests build a file-backed database in `tmp_path`, dispose the engine completely, open a second one
against the same file and read the record back.

The same module runs its assertions against real Postgres when pointed at one:

```bash
docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=test --name goae-test-db postgres:15-alpine
POSTGRES_TEST_URL=postgresql+asyncpg://postgres:test@localhost:5433/postgres \
    python -m pytest tests/test_db_persistence.py -v
```

Without the variable those parametrisations skip and say why. It has no default because the tables
are dropped and recreated around each one, so it must be a scratch database.
