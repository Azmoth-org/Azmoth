# The database

Two tables. One holds a proposal and the decision taken on it; the other is the append-only log of
what happened to it. That is the entire schema — everything else the engine reads (the catalog, the
rule tables, the logic programs) is versioned input, and the result cache is content-addressed and
disposable.

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

### Four columns the API does not return

`input_hash`, `rejected_at`, `rejected_by` and `exported_at` are written and queryable but absent
from the `Proposal` response model. Adding them would change the OpenAPI document, and the contract
for this migration was that the document does not move — the frontend must not be able to tell that
the backend changed. `rejected_by` in particular is not lost: it is the actor on the `REJECTED`
audit event, which is where "who rejected this" belongs anyway. (It used to be *genuinely* lost —
the old in-memory `transition()` accepted a `reason` but no `by` for a rejection, so the API
validated a required `rejected_by` and then dropped it.)

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

`anonymous` is deliberately conspicuous. An audit log full of it is a visible statement that access
control is still missing, which is exactly the gap
[`../compliance/PRIVATE_DATA_WARNING.md`](../compliance/PRIVATE_DATA_WARNING.md) lists. Writing a
plausible-looking name there instead would be the one genuinely dangerous option.

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
