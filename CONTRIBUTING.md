# Contributing

This repository holds a **GOÄ billing compliance engine**. Its output is a billing draft a physician
is legally responsible for, so a few conventions here are stricter than in a normal web project.
Read [Hard rules](#hard-rules) before your first change.

## Branch naming

```
<type>/<short-kebab-scope>
```

| Type | Use for | Example |
| --- | --- | --- |
| `feat/` | new behaviour a user or caller can observe | `feat/padnext-batch-audit` |
| `fix/` | a defect in existing behaviour | `fix/minderung-exempt-abschnitt-j` |
| `refactor/` | internal change, no behaviour change | `refactor/split-pipeline-stages` |
| `test/` | tests only | `test/golden-case-factor-bands` |
| `docs/` | documentation only | `docs/engine-architecture` |
| `chore/` | tooling, CI, dependencies, repo hygiene | `chore/ci-engine-image` |
| `data/` | catalog or rule-table changes — **always its own branch** | `data/verify-zielleistung-rules` |

Keep the scope to 2–4 words, lower case, hyphenated. Name the *subject*, not the file:
`feat/proposal-export` beats `feat/update-proposals-py`.

One branch = one reviewable idea. If you cannot describe it in one sentence without "and", split it.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), matching the branch type:

```
feat(engine): bound the Clingo solve with a hard timeout

The solver could previously run unbounded. A cancelled solve now returns the
best model found so far, labelled TIMEOUT_PARTIAL, and a solve that found
nothing at all fails with 504 rather than an empty invoice — "no answer" and
"nothing is chargeable" are different statements.
```

Scopes in use: `engine`, `web`, `logic`, `data`, `contracts`, `ui`, `infra`, `docs`, `repo`.

Explain **why**, not what — the diff already says what. If a change touches money, a rule or the
solver, say what you verified.

## Quality gates

Everything below must pass before you open a pull request. CI runs the same commands.

```bash
# Engine (Python 3.11 + the souffle binary — see apps/engine/README.md)
cd apps/engine
.venv/bin/python scripts/engine_cli.py check     # engines, data, logic, end-to-end probe
.venv/bin/python -m pytest                       # 731 tests, against in-memory SQLite

# Whole workspace
pnpm turbo typecheck lint build
```

If you changed a Python schema or an endpoint, regenerate the shared contract **in this order** and
commit both outputs:

```bash
cd apps/engine && .venv/bin/python scripts/export_openapi.py   # → packages/contracts/openapi/
pnpm generate:contracts                                        # → packages/contracts/typescript/
```

`python scripts/export_openapi.py --check` fails if the committed document is stale. Never hand-edit
`packages/contracts/typescript/schema.ts`.

### `souffle` missing makes tests *skip*, not fail

Rules-engine tests skip when the `souffle` binary is absent, so a green run on a laptop without it
tested almost nothing. Check the skip count, or run inside the engine image:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm engine python -m pytest -q
```

### The four remaining skips are the Postgres dialect

The suite runs against in-memory SQLite, so the parametrisations in `tests/test_db_persistence.py`
that exercise Postgres (JSONB, `SELECT … FOR UPDATE`, timezone-aware timestamps) skip and say so.
CI's `engine-database` job runs them. Locally:

```bash
docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=test --name goae-test-db postgres:15-alpine
POSTGRES_TEST_URL=postgresql+asyncpg://postgres:test@localhost:5433/postgres \
  .venv/bin/python -m pytest tests/test_db_persistence.py -v
```

### If you changed `app/db/models.py`

Generate a migration and read it — autogenerate cannot see a rename, and it emits
`postgresql.JSONB(astext_type=Text())` with `Text` not imported:

```bash
cd apps/engine
alembic revision --autogenerate -m "what changed"
```

`tests/test_db_persistence.py::test_the_migration_and_the_models_describe_the_same_schema` fails if
you forget. Full detail in
[`docs/architecture/DATABASE.md`](docs/architecture/DATABASE.md#adding-a-migration).

## Hard rules

**1. `logic/` and `data/` are not ordinary source.**
`logic/asp/goae_optimize.lp` and `logic/datalog/goae_rules.dl` are the legal reasoning;
`data/catalogs/` and `data/rules/` are versioned official data with recorded provenance. Read
[`logic/README.md`](logic/README.md) first. In particular:

- The ASP objective ordering (`@5/@4/@3/@2/@1`, revenue **last**) must not change without legal and
  medical-billing review. Hard rules stay integrity constraints; they never become weighted terms.
- Never edit the catalog JSON or a rule CSV by hand. Corrections go through
  `data/catalogs/goae_current/overrides.json`, which requires `reason`, `source` and `verified_at`.
- Never delete an unverified rule and never flip `verified` to `true` without a named reviewer and a
  date.

**2. Golden snapshots are evidence, not fixtures.**
`logic/tests/golden/*.json` record what the engine billed. If a change moves one, **stop and
investigate** — do not regenerate it to make the suite pass. If the new value is genuinely correct,
say so in the PR and have a second person confirm the money.

**3. Money is never computed in the frontend.**
The engine returns exact decimal strings (`"130.39"`) precisely so a JavaScript client cannot round
them. Display them verbatim; never parse, add or re-format an amount.

**4. Synthetic data only.**
No patient data, no real invoices, anywhere — including in a "quick local test". There is no access
control, no audit logging and no § 203 StGB workflow. See
[`docs/compliance/PRIVATE_DATA_WARNING.md`](docs/compliance/PRIVATE_DATA_WARNING.md).

**5. No credentials in this repo.**
The engine needs none, and a test fails if a settings field named `*key*`, `*secret*`, `*token*`,
`*password*` or `*credential*` appears. `.env.example` files are committed and must stay empty of
values.

**6. Do not invent API fields in the web app.**
If the UI needs data the engine does not expose, add it to the engine and regenerate the contract.
Never type a field into TypeScript that the OpenAPI document does not have.

## Pull requests

- Target `main`. Keep PRs small; stack them when work genuinely depends on earlier work.
- Say what you verified, not just what you wrote. Paste the test line (`731 passed, 4 skipped`).
- Call out anything touching money, a rule, the solver objective, or the compliance posture in the
  PR title so it gets the right reviewer.
- A PR that changes `logic/` or `data/` needs a second approver.

## Repository layout

```
apps/engine/      Python 3.11 FastAPI — the coding engine and the PADnext auditor
apps/web/         Next.js 16 — /review, /padnext, /padnext/batch, /rules, behind one app shell
packages/contracts/  generated OpenAPI → TypeScript contract (do not hand-edit)
packages/ui/      shadcn/ui components shared by the apps
logic/            Clingo ASP + Soufflé Datalog programs, golden cases  ← see logic/README.md
data/             GOÄ catalog, rule tables, mappings, raw snapshot + provenance
docs/             architecture, compliance, migration record
infra/docker/     compose file: Postgres + engine + web (`up --build` starts everything)
```

Add a shadcn component with the CLI from the repo root, so it lands in `packages/ui`:

```bash
pnpm dlx shadcn@latest add <component> -c apps/web
```
