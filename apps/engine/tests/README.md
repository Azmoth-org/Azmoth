# `apps/engine/tests`

570 tests. Every one of them was either migrated from the POC unchanged in substance, or added for
behaviour the POC did not have. **None was weakened to make the migration pass** — where a
migrated test failed only because a path moved, the path was fixed; where it asserted on an
artefact this monorepo does not contain (the POC's static UI), the assertion moved to the contract
it was really about, and that is recorded in
[`docs/migration/MIGRATION_REPORT.md`](../../../docs/migration/MIGRATION_REPORT.md).

## Running them

```bash
cd apps/engine
.venv/bin/python -m pytest -q                    # all of it, ~20 s
.venv/bin/python -m pytest -q tests/test_clingo.py
.venv/bin/python -m pytest -q -k determinis      # by name
.venv/bin/python -m pytest -q --lf               # last failures only
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
570 passed in 20.43s        # no skips: the engines were present
```

## What each file is for

| File | Tests | What it defends |
| --- | --- | --- |
| `test_golden_snapshot.py` | 11 | **golden** — the frozen POC output, reproduced field-for-field |
| `test_golden_normalization.py` | 16 | **golden** — the normaliser the snapshot, the cache key and the receipt all depend on |
| `test_manual_cases.py` | 41 | **golden / determinism** — the three synthetic cases end to end, twice |
| `test_clingo.py` | 34 | **legal posture** — arbitration, the factor ladder, Analogansatz, brute-force differential |
| `test_property.py` | 84 | **property-based** — invariants over randomly generated candidate sets |
| `test_production_fixes.py` | 64 | the seven P0 fixes: config, timeout, cache, proposals, coverage, documentation gaps, receipts |
| `test_padnext.py` | 57 | reading a delivery and auditing it; one deliberate defect per position |
| `test_validation.py` | 28 | independent re-check, exact money, § 6a Minderung, blocked-reason reconciliation |
| `test_souffle.py` | 36 | the Datalog layers: specificity, Zielleistung, exclusions, mutual clusters |
| `test_bridge_and_data.py` | 54 | the deterministic bridge, the catalog loader, the rule store |
| `test_catalog_snapshot_identity.py` | 24 | **provenance** — that the committed catalog really is the official GOÄ |
| `test_schema.py` | 44 | the frozen input contract, and that no billing concept leaks into it |
| `test_api.py` | 31 | the HTTP contract, including that the dropped POC surfaces are gone |
| `test_api_envelope.py` | 10 | both accepted request shapes, and that tolerating the bare one did not weaken typo detection |
| `test_import_goae.py` | 29 | the importer's parsing decisions — whether the catalog is trustworthy |
| `test_request_limits.py` | 7 | oversized bodies refused at the perimeter, before they are buffered |

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
- `client` — a `TestClient` with the process-wide singletons rebuilt per test, which is what keeps
  the proposal-store tests independent of each other.
- `solve_payload(client, extraction)` / `solve_proposal(...)` — POST `/api/v1/solve` and return the
  invoice draft, or the whole proposal envelope.
- `make_bridge` / `one_act_per_ziffer` / `make_extraction` — drive one symbolic layer with synthetic
  candidates, without going through the bridge or the catalog. That separability is the
  architectural claim, and these helpers are how the tests exercise it directly.
- `manual_case` / `expected_case` / `golden_case` — read from `logic/tests/`, resolved through
  `app.config`, so the suite does not care which directory pytest was invoked from.

Case data lives in `logic/tests/cases/`, frozen snapshots in `logic/tests/golden/`, and the PADnext
fixture in `logic/tests/cases/padnext/`. All of it is synthetic, and
`test_manual_cases.py::test_case_uses_only_synthetic_data` is the guard against a real record ever
being committed as a fixture.
