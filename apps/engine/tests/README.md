# `apps/engine/tests`

1000 tests. Every one of them was either migrated from the POC unchanged in substance, or added for
behaviour the POC did not have. **None was weakened to make the migration pass** — where a
migrated test failed only because a path moved, the path was fixed; where it asserted on an
artefact this monorepo does not contain (the POC's static UI), the assertion moved to the contract
it was really about, and that is recorded in
[`docs/migration/MIGRATION_REPORT.md`](../../../docs/migration/MIGRATION_REPORT.md).

## Running them

```bash
cd apps/engine
.venv/bin/python -m pytest -q                    # all of it, ~87 s
.venv/bin/python -m pytest -q tests/test_clingo.py
.venv/bin/python -m pytest -q -k determinis      # by name
.venv/bin/python -m pytest -q --lf               # last failures only
.venv/bin/python -m pytest -q --ignore=tests/property   # skip the ~40 s Hypothesis suite
.venv/bin/python -m pytest tests/benchmarks --benchmark-only   # the perf gate, skipped by default
```

Inside the container image, where Soufflé is guaranteed present:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm engine python -m pytest -q
```

### Soufflé is required, and a missing one makes tests *skip*

Every test that drives the rules engine depends on the `souffle` binary being on `PATH`. When it is
absent those tests **skip** rather than fail, which is right for a laptop and dangerous for CI: a
green run that tested nothing looks exactly like a green run that tested everything. Check the skip
count, or run in the image where the binary is always there.

```
$ .venv/bin/python -m pytest -q
992 passed, 7 skipped, 1 xfailed in 87s   # 4 skips: the Postgres parametrisations, see below
                                          # 3 skips: the benchmarks, see below
                                          # 1 xfail: an open defect, see the property suite below
```

Seven is the whole expected skip count, and it is written down here so that an *eighth* stands out.
Run with `-rs` and pytest names the reason for each.

## What each file is for

| File | Tests | What it defends |
| --- | --- | --- |
| `test_golden_snapshot.py` | 11 | **golden** — the frozen POC output, reproduced field-for-field |
| `test_golden_normalization.py` | 16 | **golden** — the normaliser the snapshot, the cache key and the receipt all depend on |
| `test_manual_cases.py` | 41 | **golden / determinism** — the three synthetic cases end to end, twice |
| `test_clingo.py` | 34 | **legal posture** — arbitration, the factor ladder, Analogansatz, brute-force differential |
| `test_property.py` | 84 | **property-based** — ten invariants over randomly generated candidate sets |
| `property/test_financial_invariants.py` | 7 | **property-based, Hypothesis** — five invariants over randomly generated `/solve` requests, plus the open defect the first sweep found |
| `test_production_fixes.py` | 64 | the seven P0 fixes: config, timeout, cache, proposals, coverage, documentation gaps, receipts |
| `test_padnext.py` | 75 | reading a delivery and auditing it; one deliberate defect per position, and the three honest money buckets |
| `test_padnext_schema.py` | 63 | **framing validation** — the five ways a delivery is refused before it is read, with a line number, and the position-level problems that must never be a refusal |
| `test_validation.py` | 28 | independent re-check, exact money, § 6a Minderung, blocked-reason reconciliation |
| `test_souffle.py` | 36 | the Datalog layers: specificity, Zielleistung, exclusions, mutual clusters |
| `test_bridge_and_data.py` | 54 | the deterministic bridge, the catalog loader, the rule store |
| `test_catalog_snapshot_identity.py` | 24 | **provenance** — that the committed catalog really is the official GOÄ |
| `test_multi_catalog.py` | 38 | **temporal routing** — one catalog edition per era: the right directory is opened, an unknown one is refused, and two editions cannot share a receipt hash |
| `test_schema.py` | 44 | the frozen input contract, and that no billing concept leaks into it |
| `test_api.py` | 31 | the HTTP contract, including that the dropped POC surfaces are gone |
| `test_api_envelope.py` | 10 | both accepted request shapes, and that tolerating the bare one did not weaken typo detection |
| `test_import_goae.py` | 29 | the importer's parsing decisions — whether the catalog is trustworthy |
| `test_request_limits.py` | 7 | oversized bodies refused at the perimeter, before they are buffered |
| `test_db_persistence.py` | 27 | **durability** — an approval survives a real restart; the lifecycle under a row lock; the migration matches the models |
| `test_audit_log.py` | 15 | the audit log records what happened, in order, with an actor — and cannot be rewritten |
| `test_pagination.py` | 31 | **paging and filtering the two list endpoints** — that `total` follows the filter rather than the table, that two pages never overlap, and that a limit outside its range is a `422` and not a clamped success |
| `benchmarks/test_performance.py` | 3 | **performance regressions** — cold catalog + rule load, one solve, one proposal round trip, each gated on a soft and a hard threshold |

## The benchmarks, and why they are skipped by default

`tests/benchmarks/` measures wall-clock, so it is the one part of this suite whose result depends on
what else the machine is doing. `pytest.ini` carries `--benchmark-skip`; `--benchmark-only`
overrides it, and that is the only way these three run:

```bash
.venv/bin/python -m pytest tests/benchmarks --benchmark-only
```

Each reports the median of 10 timed rounds against two thresholds: **soft** at the baseline +20%,
which warns and prints a summary section but still passes, and **hard** at +100%, which fails and
names the number. The baselines, the machine they were measured on, the observed run-to-run spread
and the reasoning behind the two thresholds are in
[`docs/performance_baselines.md`](../../../docs/performance_baselines.md). CI runs them as its own
`engine-benchmarks` job and keeps the JSON as an artefact.

The three skips this produces in an ordinary run are intentional, and they are counted above.

## The database, and why the suite does not use yours

`DATABASE_URL` is forced to `sqlite+aiosqlite:///:memory:` in `conftest.py`, at import time, before
`app.main` is imported. Two reasons, and the first is the important one:

1. **Safety.** An inherited `DATABASE_URL` — exported for a `psql` session, or sitting in a `.env` —
   must not be able to make the suite write test proposals into a real database.
2. **Isolation.** For SQLite the connection *is* the database, so every new engine gets an empty one
   and a test cannot see the rows of the test before it. Nothing has to truncate anything.

`APP_ENV` is forced to `development` for the same kind of reason: the container image sets
`APP_ENV=production`, CI runs this suite inside it, and two production guards would fire on that
(`create_all` is refused in production, and so is a non-Postgres URL). Both are correct for a running
service and wrong for a test run, which is not a deployment.

**`test_db_persistence.py` is the exception.** Durability cannot be tested against an in-memory
database — closing the connection *is* the restart, and it takes the data with it — so those tests
build a file-backed database in `tmp_path`, dispose the engine completely, open a second one against
the same file and read the record back.

Every test in that module is parametrised over both supported dialects. The Postgres half runs only
when pointed at a scratch server, and skips with a message naming the variable when it is not — CI's
`engine-database` job is what sets it:

```bash
docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=test --name goae-test-db postgres:15-alpine
POSTGRES_TEST_URL=postgresql+asyncpg://postgres:test@localhost:5433/postgres \
  .venv/bin/python -m pytest tests/test_db_persistence.py -v
```

Also here: `test_the_migration_and_the_models_describe_the_same_schema` runs `alembic upgrade head`
and `Base.metadata.create_all` into two scratch databases and compares them. It catches the ordinary
drift — a column added to the models, a suite that passes because it uses `create_all`, and a deploy
that migrates into a schema without it.

## The golden tests

`logic/tests/golden/*.golden.normalized.json` were produced by the **POC** engine, before this
migration, and are committed byte-for-byte unchanged. That is what makes them worth having: they
are the record of what the previous implementation billed.

`test_golden_snapshot.py::test_the_engine_still_reproduces_the_frozen_snapshot` compares them
against the live engine as a **subset**: every field the snapshot contains must still be present and
identical, and `test_no_undeclared_field_was_added` requires any *new* field to be named in
`ADDED_BY_MIGRATION`. A failure in the first is a behaviour change and must be investigated — never
fixed by regenerating the snapshot, which would make the file assert nothing.

`test_golden_normalization.py` is the other half, and it matters more than it looks. `canonical()`
decides what "the same result" means, and three things now depend on it: the golden comparison, the
content-addressed cache key, and the receipt hash. It is asserted in both directions — that measured
timings are stripped (or determinism checks would fail on a deterministic system) and that nothing
load-bearing is (or two different results would hash to one cache key).

## The Hypothesis property suite

`tests/property/` is the newer half of the property-based testing, and it differs from
`test_property.py` in what it generates and how far it runs.

`test_property.py` builds a `BridgeResult` by hand from a curated pool of Ziffern and drives the
symbolic layers directly, over 60 seeded cases. `tests/property/` generates a real
`POST /api/v1/solve` body — the frozen input contract, clinical entities only, no Ziffer anywhere —
and runs `Pipeline.propose` end to end, which is what makes `receipt_hash` available to assert on.
The two are complementary: one reaches Ziffern the mapping table cannot produce, the other reaches
the bridge, the receipt and the request contract.

The generated vocabulary is `load_mapping()` filtered against the loaded catalog, so a generated
service always resolves to a real, active position and the strategies cannot drift from
`data/mappings/entity_to_ziffer.csv`. Adding a row widens them; removing one narrows them.

| Property | Claim |
| --- | --- |
| `test_financial_sum_invariant` | Punktzahl x Punktwert x Faktor, less § 6a Minderung, rounded half-up per line and summed, equals `total.amount_eur` — recomputed from the catalog |
| `test_uniqueness_invariant` | no Ziffer twice, lines in canonical order, nothing both charged and blocked |
| `test_proof_invariant` | every position, charged or blocked, carries its reason — and a named blocker really is on the invoice |
| `test_factor_bounds_invariant` | every factor inside `[1.0, Höchstsatz]`, capped by any Leistungslegende cap, justified above the Schwellenwert |
| `test_determinism_invariant` | same request → same `Coding` and same `receipt_hash`, with the cache off so each run genuinely re-solved |

```bash
.venv/bin/python -m pytest tests/property/ --hypothesis-seed=0            # ~40 s, reproducible
.venv/bin/python -m pytest tests/property/ --hypothesis-show-statistics   # what got generated
HYPOTHESIS_MAX_EXAMPLES=2000 .venv/bin/python -m pytest tests/property/ \
    --hypothesis-seed=random                                              # ~13 min sweep
```

### Why the seed is on the command line and not in the profile

The profile deliberately does not set `derandomize`, so a plain run explores new inputs — which is
the only reason to have these tests rather than more golden cases. `--hypothesis-seed=0` pins the
input set when reproducibility matters, and CI passes it so a red build is actionable. The two are
not interchangeable: Hypothesis checks `derandomize` *before* `--hypothesis-seed`, so setting it in
the profile would have silently made the documented flag a no-op.

### `max_examples`, and what it costs

100 per property (50 for determinism, which solves twice per example) — about 40 s for the file, at
roughly 80 ms per solve. That is the largest number that keeps the whole engine suite in the range
where people still run it before committing, and it covers the generated space several times over.
`HYPOTHESIS_MAX_EXAMPLES` raises it without editing anything; the bug in
[`docs/audit/PROPERTY_TEST_FINDINGS.md`](../../../docs/audit/PROPERTY_TEST_FINDINGS.md) was found at
1500 and would be a reasonable nightly figure.

### The one `xfail`, and why it is `strict`

The first wide sweep failed all five properties on one shared cause: an Analogansatz position
reaches the invoice through `analog/2`, and the two legality constraints in
`logic/asp/goae_optimize.lp` range over `bill/1`, so it faces neither. The validator catches it and
refuses, which turns an ordinary encounter into a `500`.

Fixing it changes what the solver is willing to bill, so it is **not** fixed here — it is recorded
as `test_the_analog_ladder_ignores_exclusions_against_the_final_invoice`, an `xfail(strict=True)`
that reproduces it in four lines. `strict` means the day the constraint is widened, that test
XPASSes and fails the build, telling whoever fixed it to delete the marker and the generator guard
that goes with it. The root cause, the proposed diff and the two decisions it needs first are in
[`docs/audit/PROPERTY_TEST_FINDINGS.md`](../../../docs/audit/PROPERTY_TEST_FINDINGS.md).

No assertion was weakened for it. The generator declines exactly one combination — an Analogansatz
service alongside a service whose Ziffer is mutually exclusive with one of that analog type's
candidate targets — derived from the rule tables rather than written out, and
`test_the_generated_space_is_worth_exploring` pins its size so a data change cannot widen it
silently.

## The determinism tests

| Test | Claim |
| --- | --- |
| `test_manual_cases.py::test_case_is_deterministic` | same input → the same canonical response |
| `test_manual_cases.py::test_case_receipt_hash_is_stable` | …and the same 64-hex receipt |
| `test_padnext.py::test_reading_the_same_delivery_twice_gives_the_same_report` | the audit path too |
| `test_padnext.py::test_the_receipt_hash_is_stable_across_identical_audits` | …with a stable receipt |
| `test_production_fixes.py::test_the_receipt_ignores_measured_values` | timings do not move the receipt |
| `test_production_fixes.py::test_the_second_identical_solve_is_served_from_the_cache` | the cache agrees |
| `test_production_fixes.py` cache-key matrix | every input that can change an answer changes the key |
| `property/test_financial_invariants.py::test_determinism_invariant` | …over randomly generated requests, with the cache off |

## The legal-posture tests

These are the ones to read before touching the solver, and the ones that must not be relaxed to
make a change pass. Changing what they assert changes what the system is willing to bill for, and
needs legal and domain review — see [`logic/README.md`](../../../logic/README.md).

| Test | Claim |
| --- | --- |
| `test_production_fixes.py::test_the_objective_ordering_is_untouched` | `@5/@4/@3/@2/@1` in that order, revenue last, hard rules as integrity constraints, no new priority level |
| `test_clingo.py` (arbitration) | a mutual conflict is decided on **evidence**, not on money |
| `test_clingo.py` (brute force) | the solver's choice equals an exhaustive enumeration's optimum |
| `test_clingo.py` / `test_manual_cases.py` (factor ladder) | no factor leaves its § 5 band or its Leistungslegende cap |
| `test_manual_cases.py::test_case_factors_stay_inside_their_legal_band` | any factor above the Schwellenwert has a written reason (§ 12 Abs. 3) |
| `property/test_financial_invariants.py` | …and the same for money, uniqueness and proof, over randomly generated requests |
| `test_manual_cases.py::test_case_never_violates_a_rule_it_enforces` | no invoice violates an enforced exclusion or Zielleistung rule |
| `test_souffle.py` (Zielleistung) | components are suppressed in **Datalog**, not traded off in the optimiser |
| `test_validation.py` | the layer that picks a number is not the layer that approves it; a disagreement raises |
| `test_production_fixes.py::test_missing_documentation_names_the_gap_without_charging_for_it` | what is billed is the current factor, never the possible one |
| `test_production_fixes.py` (rule coverage) | the API never implies unverified rules are enforced |
| `test_schema.py` | no fee-schedule concept may enter the input contract |
| `test_catalog_snapshot_identity.py` | the catalog is the official public-domain text, at a recorded SHA-256 |

## Fixtures

Shared fixtures are in `conftest.py`. The important ones:

- `settings` — explicit defaults, so a developer's `.env` can never change what the suite asserts.
- `client` — a `TestClient` with the process-wide singletons rebuilt per test. That used to be about
  a dictionary and is now about the connection pool: `__enter__` runs the lifespan (which builds a
  `Database` and creates the schema) and `__exit__` disposes it, and because `DATABASE_URL` is
  in-memory SQLite, disposing the engine destroys the database. Each test therefore starts from an
  empty `proposals` table without anything having to delete rows.
- `database` / `store` — an isolated in-memory database with both tables created, and a
  `ProposalStore` bound to it. For the tests that drive the store below HTTP. Not the singleton, so
  nothing global is touched.
- `solve_payload(client, extraction)` / `solve_proposal(...)` — POST `/api/v1/solve` and return the
  invoice draft, or the whole proposal envelope.
- `make_bridge` / `one_act_per_ziffer` / `make_extraction` — drive one symbolic layer with synthetic
  candidates, without going through the bridge or the catalog. That separability is the
  architectural claim, and these helpers are how the tests exercise it directly.
- `manual_case` / `expected_case` / `golden_case` — read from `logic/tests/`, resolved through
  `app.config`, so the suite does not care which directory pytest was invoked from.

In `tests/property/conftest.py`, for the Hypothesis suite only:

- `property_pipeline` — a **session-scoped** pipeline with `cache_enabled=False`. Both halves
  matter: `@given` with a function-scoped fixture trips `HealthCheck.function_scoped_fixture`, and
  with the content-addressed cache on, Hypothesis's repeated inputs would assert against a dict
  computed once instead of a solve.
- `solve_requests()` / `solve()` — the request strategy and the one-line runner that parses a fresh
  `SolveRequest` per call, so two runs of one payload cannot share an object.

Case data lives in `logic/tests/cases/`, frozen snapshots in `logic/tests/golden/`, and the PADnext
fixture in `logic/tests/cases/padnext/`. All of it is synthetic, and
`test_manual_cases.py::test_case_uses_only_synthetic_data` is the guard against a real record ever
being committed as a fixture.
