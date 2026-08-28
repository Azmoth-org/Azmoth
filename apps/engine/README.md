# `apps/engine` — the GOÄ coding engine

A Python 3.11 FastAPI service that turns structured clinical entities into an **auditable billing
draft**, and audits already-coded PADnext deliveries against the same rules. No model runs anywhere
in this service.

```
clinical entities (JSON)
  → bridge      candidate GOÄ Ziffern         deterministic CSV lookup
  → Soufflé     what is certainly chargeable   stratified Datalog, explainable
  → Clingo      what requires a choice         ASP, legality hard-constrained, hard timeout
  → Soufflé     independent re-check of the chosen factors
  → validator   independent re-check, exact money, audit trail
  → proposal    DRAFT + receipt hash, awaiting a human
```

The logic lives outside this app on purpose: `logic/asp/goae_optimize.lp` and
`logic/datalog/goae_rules.dl` are declarative legal reasoning that should be reviewable without
reading Python. The catalog and rule tables live in `data/`. Both are resolved through `LOGIC_DIR`
and `DATA_DIR`.

> **Synthetic data only.** This service implements no access control, no audit logging and no PHI
> handling. Read [`docs/compliance/PRIVATE_DATA_WARNING.md`](../../docs/compliance/PRIVATE_DATA_WARNING.md)
> before pointing anything real at it.

## Install

Two dependencies are not pip-installable and have to be present:

| Dependency | Why | Install |
| --- | --- | --- |
| **Soufflé 2.5** (`souffle` binary) | evaluates `goae_rules.dl` | see below — not in the Debian/Ubuntu archives |
| **mcpp** | Soufflé shells out to a C preprocessor even in interpreter mode, and aborts without one | `apt-get install mcpp` |

```bash
cd apps/engine
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt      # pinned; clingo comes as a wheel

# Soufflé: upstream release .deb, unpacked directly (it targets Ubuntu 22.04)
curl -fsSL -o /tmp/souffle.deb \
  https://github.com/souffle-lang/souffle/releases/download/2.5/x86_64-ubuntu-2204-souffle-2.5-Linux.deb
sudo apt-get install -y mcpp libffi8 libgomp1 libncurses6 libsqlite3-0 zlib1g
sudo dpkg-deb -x /tmp/souffle.deb /

souffle --version                               # expect 2.5
.venv/bin/python scripts/engine_cli.py check    # engines, data, logic, end-to-end probe
```

`check` is the one command worth running after any change to the catalog, the rule tables or the
logic programs. It fails loudly rather than degrading.

If you would rather not install Soufflé locally, use Docker (below) — the image builds it in.

## Run the API

```bash
cd apps/engine
.venv/bin/uvicorn app.main:app --reload --port 8000

curl -s localhost:8000/api/v1/health | python3 -m json.tool
curl -s -X POST localhost:8000/api/v1/solve \
     -H 'Content-Type: application/json' \
     -d @../../logic/tests/cases/case_001_knee/input.json | python3 -m json.tool
```

Interactive docs at <http://localhost:8000/docs>.

### Endpoints

**Every proposal and batch endpoint below is organisation-scoped.** They require an
`X-Organization-ID` header naming the Better Auth organisation the caller acts for, and answer
`403 ORGANIZATION_REQUIRED` without one — there is no default tenant. Rows are stamped with it on
write and filtered by it on read, so one practice cannot see or decide another's records. The web
tier sets it from the session's active practice on every call it proxies
(`apps/web/lib/engine.ts`); a direct caller sets it itself:

```bash
curl -s localhost:8000/api/v1/proposals -H 'X-Organization-ID: <organization.id>'
```

`/health`, `/catalog`, `/vocabulary`, the rules endpoints and `POST /padnext/audit` do **not**
require it — the first four are not tenant data, and the last stores nothing. See
`apps/engine/app/api/tenancy.py` for why the header is enforced but not verified.


| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/api/v1/health` | versions, cache state, solver timeout — and a live **probe** of each solver (`solvers.clingo` / `solvers.souffle`: `ok` \| `failed` \| `unavailable`, with `probe_time_ms`) |
| `POST` | `/api/v1/solve` | clinical entities → a **DRAFT** proposal with a receipt hash |
| `GET` | `/api/v1/proposals` | a page of proposals: `?status=&case_id=&limit=&offset=` → `{items, total, limit, offset}` |
| `GET` | `/api/v1/proposals/{id}` | one proposal |
| `POST` | `/api/v1/proposals/{id}/approve` | the human approval boundary; `approved_by` required |
| `POST` | `/api/v1/proposals/{id}/reject` | terminal, with a reason |
| `POST` | `/api/v1/proposals/{id}/export` | reachable only from `APPROVED` |
| `POST` | `/api/v1/padnext/audit` | audit a `.padx` container or `*_padx.xml` payload |
| `POST` | `/api/v1/padnext/batch` | audit many deliveries; `202` with a handle to poll |
| `GET` | `/api/v1/padnext/batch` | a page of batches, newest first: `?status=&created_after=&limit=&offset=` → `{jobs, total, limit, offset}` — headers and roll-ups, no files |
| `GET` | `/api/v1/padnext/batch/{id}` | one batch: progress, then the roll-up and every file's report |
| `POST` | `/api/v1/padnext/batch/{id}/export` | a completed batch as a ZIP of CSVs |
| `GET` | `/api/v1/rules/coverage` | how much of the rule set is actually enforced |
| `GET` | `/api/v1/rules/review-queue` | unverified rules, with the GOÄ sentence each came from |
| `POST` | `/api/v1/rules/{id}/review` | a billing expert's verdict; merged into the running engine |
| `GET` | `/api/v1/catalog` | catalog provenance, coverage and its warnings |
| `GET` | `/api/v1/catalog/ziffer/{ziffer}` | one position, with the rules that touch it |
| `GET` | `/api/v1/vocabulary` | exactly the clinical vocabulary the bridge can map |

`POST /api/v1/solve` accepts either a bare extraction or `{"extraction": {...}, "setting": ...}`.

`POST /api/v1/padnext/audit` splits the claimed total into three buckets rather than one "at risk"
figure — `confirmed_wrong_eur` (provable against a verified rule, the versioned catalog or the § 5
arithmetic), `confirmed_fine_eur` (all applicable checks passed and a verified rule actually bore on
the position) and `unconfirmed_eur` (no verified rule maps to the Ziffer, or only advisory ones do).
They sum to `claimed_total_eur` exactly, and `coverage_ratio` says what share was audited at all.
**`unconfirmed` is our missing rule coverage, not a finding against the practice** — see
[`docs/architecture/ENGINE.md`](../../docs/architecture/ENGINE.md) for why the single figure was
removed.

## Database

Proposals and the approval record are persisted; an approval survives a restart and every decision
writes a row in an append-only audit log. Schema, the reasoning behind it, and the full set of
migration commands: [`../../docs/architecture/DATABASE.md`](../../docs/architecture/DATABASE.md).

**Locally there is nothing to set up.** `DATABASE_URL` defaults to a SQLite file and the tables are
created on first start:

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000   # creates ./test.db
.venv/bin/python -m pytest                            # in-memory, per test, nothing left behind
```

**Against Postgres**, which is what production runs and what `docker compose` brings up:

```bash
docker compose -f ../../infra/docker/docker-compose.yml up -d postgres

export DATABASE_URL=postgresql+asyncpg://azmoth:azmoth@localhost:5432/azmoth
.venv/bin/python scripts/migrate.py           # waits for the server, then upgrades to head
.venv/bin/python scripts/migrate.py --check   # report the revision; exit 1 if behind
.venv/bin/alembic upgrade head                # the same thing, via alembic directly
```

`alembic.ini` has no `sqlalchemy.url`: `alembic/env.py` reads `DATABASE_URL` through the same
`Settings` object the service uses, so a migration cannot land in a database the engine will not then
talk to, and no connection string is ever committed.

In a container the image migrates itself — `scripts/docker-entrypoint.sh` runs
`alembic upgrade head` before uvicorn, whatever `command:` it is given. `docker compose up` is the
whole story.

SQLite persists, but it is not a deployment target: one writer, one file inside a container that is
replaced on every deploy, no replication, no encryption at rest. Under `APP_ENV=production` the
engine **refuses to start** on anything but Postgres.

## CLI

```bash
.venv/bin/python scripts/engine_cli.py check                       # full stack check
.venv/bin/python scripts/engine_cli.py check-souffle                # container healthcheck
.venv/bin/python scripts/engine_cli.py solve ../../logic/tests/cases/case_001_knee/input.json
.venv/bin/python scripts/engine_cli.py solve <case.json> --stats   # timing + grounding breakdown
.venv/bin/python scripts/engine_cli.py padnext ../../logic/tests/cases/padnext/00004711_20260726_ADL_000001.padx
.venv/bin/python scripts/engine_cli.py catalog --ziffer 301
```

`--stats` splits catalog loading, parsing, each pipeline stage, Clingo grounding and Clingo search,
and prints the size of the ground program from `clingo.Control.statistics`. What it measures on the
three golden cases, and what would make a solve slow, is in
[`docs/performance_baseline.md`](../../docs/performance_baseline.md).

Provenance tooling — how the committed catalog was built, and how to rebuild it:

```bash
.venv/bin/python scripts/fetch_goae.py     # download the official XML, write data/raw/manifest.json
.venv/bin/python scripts/import_goae.py    # XML → data/catalogs/goae_current/ + data/rules/*.csv
.venv/bin/python scripts/generate_facts.py --manual <case.json> -o facts/   # inspect Datalog input
.venv/bin/python scripts/make_padnext_example.py                           # rebuild the .padx fixture
```

## Errors

Every non-2xx response carries `error_code` (stable, machine-readable), `message`, `details` and —
only where retrying could work — `retry_after` in seconds plus a `Retry-After` header. The complete
catalog, including which failures are retried internally and which are deliberately not, is
[`docs/errors.md`](../../docs/errors.md). The codes live in code as `app/errors.py`, and a code
without a row in that table fails the suite.

## Tests

```bash
cd apps/engine
.venv/bin/python -m pytest -q          # everything, against in-memory SQLite
.venv/bin/python -m pytest -q tests/test_golden_snapshot.py   # the migration check
```

The suite forces `DATABASE_URL=sqlite+aiosqlite:///:memory:` at conftest import time. That is both a
safety measure — an inherited `DATABASE_URL` cannot make the suite write test proposals into a real
database — and the isolation mechanism: for SQLite the connection *is* the database, so every test
gets an empty one.

To also exercise the Postgres dialect (JSONB, `SELECT … FOR UPDATE`, timezone-aware timestamps),
which CI does in the `engine-database` job:

```bash
docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=test --name goae-test-db postgres:15-alpine
POSTGRES_TEST_URL=postgresql+asyncpg://postgres:test@localhost:5433/postgres \
  .venv/bin/python -m pytest tests/test_db_persistence.py -v
```

Without that variable those parametrisations skip and say so. It has no default because the tables
are dropped and recreated around each test, so it must be a scratch database.

See [`tests/README.md`](tests/README.md) for which tests are golden, which pin determinism and
which pin the legal posture.

## Contracts for the front end

Schemas are never duplicated between Python and TypeScript:

```bash
.venv/bin/python scripts/export_openapi.py            # → packages/contracts/openapi/openapi.json
pnpm --filter @workspace/contracts generate           # → packages/contracts/typescript/schema.ts
.venv/bin/python scripts/export_openapi.py --check    # CI: fails if the committed file is stale
```

## Docker

```bash
# from the MONOREPO ROOT — the image needs logic/ and data/, which live outside apps/engine
docker build -f apps/engine/Dockerfile -t azmoth-engine:0.3.0 .

# the whole stack: Postgres, then the engine, which migrates it and serves the API.
# The rules and the catalog are mounted read-only, so editing a .dl / .lp / CSV needs no rebuild.
docker compose -f infra/docker/docker-compose.yml up --build
```

The image runs as a non-root user (uid 10001), installs Soufflé 2.5 and `clingo==5.8.0`, copies
`logic/`, `data/` and the Alembic history to `/srv`, exposes 8000, and has a healthcheck that fails
when the rules engine is unavailable — not merely when the process is down.
`scripts/engine_cli.py check` runs at build time, so a broken catalog fails the build rather than the
first request.

`ENTRYPOINT` is `scripts/docker-entrypoint.sh`, which runs `alembic upgrade head` and then `exec`s
whatever command it was given — so migrations happen even though `docker-compose.yml` overrides
`command:` to add `--reload`. `RUN_MIGRATIONS=false` skips that step for a pipeline that migrates in
its own job.

The image sets **no** `DATABASE_URL`, deliberately, so a bare
`docker run -p 8000:8000 azmoth-engine:0.3.0` refuses to start rather than quietly running on a
store it cannot keep records in — the image sets `APP_ENV=production`, and production requires
Postgres. To run the container against a database directly:

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://azmoth:azmoth@host.docker.internal:5432/azmoth \
  azmoth-engine:0.3.0
```

One-off commands need no database and skip the migration on their own:

```bash
docker run --rm azmoth-engine:0.3.0 python scripts/engine_cli.py check
docker run --rm -e REQUIRE_ENGINES=1 azmoth-engine:0.3.0 python -m pytest -rs
```

## Environment variables

Everything is optional; the defaults are the safe ones. Full annotated list in
[`.env.example`](.env.example).

`DATABASE_URL` is the only setting that names an external service or can carry a credential, and it
defaults to a local SQLite file — so a checkout runs with nothing configured. There are **no
secrets in this repository** and the engine needs no API key or token of any kind.

| Variable | Default | Effect |
| --- | --- | --- |
| `APP_ENV` | `development` | mostly a label — but `production` refuses a non-Postgres `DATABASE_URL` and refuses `DATABASE_AUTO_CREATE` |
| `DEBUG` | `false` | debug-level logging |
| `EXTRACTION_MODE` | `manual` | the only supported value — see the input boundary below |
| `UNVERIFIED_RULE_POLICY` | `warn` | what machine-extracted rules may do: `warn` / `block` / `ignore` |
| `BASE_FACTOR_POLICY` | `schwellenwert` | base Steigerungsfaktor absent a documented reason |
| `SOLVER_TIMEOUT_SECONDS` | `5` | hard ceiling on one Clingo solve |
| `SOUFFLE_BIN` / `SOUFFLE_TIMEOUT_S` | `souffle` / `60` | the Datalog engine |
| `CACHE_ENABLED` / `CACHE_MAX_ENTRIES` | `true` / `256` | content-addressed result cache |
| `DATABASE_URL` | `sqlite+aiosqlite:///./test.db` | where proposals and the audit log live. Postgres in production — refused otherwise under `APP_ENV=production` |
| `DATABASE_AUTO_CREATE` | `true` | create the tables at startup instead of requiring `alembic upgrade head`. Refused in production |
| `DATABASE_ECHO` | `false` | log every SQL statement. Separate from `DEBUG`: statement logs on clinical data are a leak risk |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | `5` / `10` | connection pool per worker; ignored by SQLite |
| `LOGIC_DIR` / `DATA_DIR` | repo `logic/` and `data/` | where the programs and the catalog are |
| `CATALOG_VERSION` | *(empty)* | set it to assert an expected snapshot; a mismatch fails at startup |
| `MAX_REQUEST_BYTES` | `33554432` | refused at the perimeter, before the body is buffered |
| `PADNEXT_ALLOW_REAL_DATA` | `false` | a delivery flagged as production data is refused |

### The input boundary

`EXTRACTION_MODE=manual` is the only supported mode, and it is not a limitation: the engine takes
**structured clinical entities**, and where they come from — a form, a PVS export, a model running
somewhere else — is outside this service. The POC had an experimental free-text path; it was not
migrated, and no LLM SDK is a dependency here (`tests/test_production_fixes.py` asserts that).

The invariant that path was held to *was* migrated: whatever produces clinical entities upstream
must never be told about the fee schedule. `app/core/extraction_prompts.py` holds that contract and
`tests/test_schema.py` enforces it — the extraction schema may not contain a Ziffer, a factor, a
Punktzahl or any other billing concept, in a field name, a description or a docstring.

### Solver timeout

`SOLVER_TIMEOUT_SECONDS` is enforced with Clingo's asynchronous solve handle: start, wait, cancel.
There is no configuration in which the solver runs unbounded (`0` and negatives are rejected).

- **Timeout with a model already found** → that model is returned, `solver_status` becomes
  `TIMEOUT_PARTIAL`, and a `solver_timeout_partial` warning says optimality is not proven. Every
  hard rule still holds; only the choice among equally lawful alternatives may not be the best one.
- **Timeout with no model at all** → `504` and no draft. An empty result would be
  indistinguishable from "nothing is chargeable", which is a very different statement.

Observed per-case solve time is ~30 ms, so the 5 s default is three orders of magnitude of headroom.
Solving is CPU-bound, so the routes that reach it are sync `def` functions and FastAPI runs them in
its threadpool — the event loop is never blocked.

### Cache behaviour

The cache is content-addressed. The key is a SHA-256 over the catalog version **and file hash**, the
rules version **and a hash of every rule CSV**, a hash of both logic programs, the Clingo and
Soufflé versions, the policy fingerprint, and the canonical input facts. Consequences:

- Two identical requests hit; the second response has `"cached": true`.
- Editing one cell of one rule CSV, or one line of `goae_optimize.lp`, misses. A cache that could
  serve a result computed under a different rule set would be a compliance defect, not a
  performance one.
- A cached hit is still returned as a **new `DRAFT` proposal with a new id**. The result is
  reusable; the responsibility for it is not.
- Nothing measured (timings, timestamps, ids) is in the key.

The backend is an in-memory LRU behind a `CacheBackend` protocol, so Redis can replace it without
touching a caller. `CACHE_ENABLED=false` makes every operation a no-op.

### Rule policy behaviour

Most exclusion rules (837 of them) were extracted from the fee schedule's prose automatically and
are **not human-verified**. `UNVERIFIED_RULE_POLICY` decides what they may do:

| Policy | Effect |
| --- | --- |
| `warn` **(default)** | they suppress nothing; the response warns and counts them advisory |
| `block` | enforced exactly like verified rules |
| `ignore` | dropped entirely, and counted |

Every solve and audit response reports `enforced_rule_count`, `advisory_rule_count` and
`suppressed_unverified_rule_count`, and carries a warning whenever advisory rules exist. The API
must never imply that unverified rules are enforced. See [`logic/README.md`](../../logic/README.md)
for what may and may not be changed about the rules and the objective ordering.

### Receipts

Every solve and audit returns a `receipt_hash`: SHA-256 over catalog version + file hash, rules
version + rule-table hash, logic hash, solver versions, policy fingerprint, canonical input and
canonical output. Two responses with the same receipt were produced by the same data, the same
logic and the same policy — which is what makes "deterministic" a checkable claim rather than an
assurance.

## Layout

```
app/
  main.py              FastAPI app: five routers, one prefix, no UI
  config.py            pydantic-settings; repo-root/env path resolution
  api/                 health, solve, proposals, padnext, catalog, deps
  core/                canonicalisation, request-size limit, frozen prompt contract
  schemas/             every contract, split by concern, re-exported as one namespace
  db/                  SQLAlchemy models (proposals, audit_events), engine and session factory
  services/            pipeline, cache, receipt, rule_coverage, proposal_store
  solvers/             clingo_solver, souffle_engine, souffle_facts
  rules/               rule_store — provenance and the unverified-rule policy
  catalog/             catalog_loader — versioned data with a recorded SHA-256
  bridge/              clinical entities → candidate Ziffern (CSV lookup, never a model)
  validation/          independent re-check, exact money, audit trail
  padnext/             reader + audit
alembic/               migration history; alembic.ini reads DATABASE_URL, never a committed URL
scripts/               engine_cli, migrate, export_openapi, import_goae, fetch_goae, …
tests/                 832 tests — see tests/README.md
```
