# Migration plan — POC backend → `Azmoth` monorepo

Written before any file was moved. Status of every item is recorded in
[`MIGRATION_REPORT.md`](./MIGRATION_REPORT.md) after execution.

```
SOURCE_POC      = /home/oussama/Desktop/MVP/SOURCE_POC        (READ-ONLY)
TARGET_MONOREPO = /home/oussama/Desktop/MVP/TARGET_MONOREPO   (writable)
```

The placeholders in the brief (`/absolute/path/to/...`) resolved to the two directories that
actually exist under `/home/oussama/Desktop/MVP`. Nothing outside `TARGET_MONOREPO` is written.

## 0. What the source actually is

The POC is a two-app repo:

- `backend/` — Python 3.11 FastAPI service, ~5 400 lines of app code + ~4 000 lines of tests.
  A deterministic GOÄ coding engine: CSV bridge → Soufflé Datalog → Clingo ASP → independent
  validator, plus a PADnext (private-billing XML) auditor.
- `frontend/` — Next.js 15 + shadcn workbench, marketing pages, two legacy static HTML pages
  (`/manual`, `/deck`) served by the backend, and an offline `demo_fallback/`.

The target monorepo is a **Turborepo + pnpm workspace** (`pnpm@10.33.4`, `turbo ^2.9.18`) with
`apps/web` (Next 16.2.6, React 19) and `packages/{ui,eslint-config,typescript-config}`. It has no
Python app yet. The existing setup is respected: no Nx, no workspace-tool change, `apps/web`
untouched except for one added script and the generated contract types.

### Compatibility adjustments made for this monorepo (deviations from the brief's literal layout)

| Brief says | What is done here | Why |
| --- | --- | --- |
| `packages/ui` "existing shadcn package if present" | left exactly as-is | already present and configured |
| `apps/engine/app/rules/rule_store.py` | kept, **plus** `app/bridge/` | the entity→Ziffer bridge is load-bearing pipeline logic with no home in the listed layout; it is the only place clinical vocabulary meets fee-schedule identifiers |
| `app/schemas/{case,facts,solver,proposal,padnext}.py` | those five **plus** `common.py` (shared `Dec`/`Setting`/`Warning_`) and `result.py` (invoice/audit envelopes) | splitting the POC's 529-line `models.py` into exactly five files would put the invoice envelope in an arbitrary one; `app/schemas/__init__.py` re-exports everything so callers see one namespace |
| `data/catalogs/`, `data/rules/` | those, **plus** `data/mappings/` and `data/raw/` | the entity→Ziffer mapping CSV and the raw official XML snapshot + manifest are provenance data the catalog identity tests assert against |
| Clingo `.lp` from `backend/app/optimization/*.lp` | → `logic/asp/` | as specified |
| Soufflé `.dl` from `backend/app/rules/*.dl` | → `logic/datalog/` | as specified |
| golden/manual cases → `logic/tests/cases/` | `input.json`/`expected.json` → `logic/tests/cases/<case>/`, frozen snapshots → `logic/tests/golden/<case>.golden.normalized.json` | the brief mandates both directories; this is the only split that gives each one a distinct meaning |
| pnpm workspace globs `apps/*` | `apps/engine` has **no** `package.json` | a Python app must not become a pnpm workspace member; `pnpm-workspace.yaml` is left unchanged and simply finds nothing there |

## 1. Files to migrate — exact source → exact target

### 1.1 Logic (byte-identical, only path references inside them may change)

| Source | Target |
| --- | --- |
| `backend/app/optimization/goae_optimize.lp` | `logic/asp/goae_optimize.lp` |
| `backend/app/rules/goae_rules.dl` | `logic/datalog/goae_rules.dl` |

Both are copied **verbatim**. The ASP objective block (`@5` analog collision, `@4` coverage,
`@3` evidence, `@2` specificity, `@1` points) and every integrity constraint are unchanged.

### 1.2 Data (byte-identical, never edited)

| Source | Target |
| --- | --- |
| `backend/data/catalog/goae.official.json` | `data/catalogs/goae_current/goae.official.json` |
| `backend/data/catalog/overrides.json` | `data/catalogs/goae_current/overrides.json` |
| `backend/data/catalog/unparsed_rows.json` | `data/catalogs/goae_current/unparsed_rows.json` |
| `backend/data/rules/*.csv` (7 files) | `data/rules/*.csv` |
| `backend/data/rules/import_report.json` | `data/rules/import_report.json` |
| `backend/data/mappings/entity_to_ziffer.csv` | `data/mappings/entity_to_ziffer.csv` |
| `backend/data/raw/goae_source.xml`, `manifest.json`, `README.md` | `data/raw/` |
| `backend/data/licensed/README.md` | `data/licensed/README.md` |

Provenance preserved exactly: `catalog_version = goae_official_snapshot_2026-07-25`,
`source.sha256_raw = d920ed67…78aa`, `retrieved_at = 2026-07-25T14:08:38+00:00`,
`legal_status = "Amtliches Werk, gemeinfrei nach § 5 UrhG"`, `coverage.rule_coverage = partial`,
`rules_version = auto_extracted_2026-07-25`, and every rule row's `verified` / `verified_at` /
`source` / `legal_basis` / `quote` column. **No unverified rule is deleted and none is promoted.**
`data/raw/goae_source.zip` is **not** copied — the extracted `.xml` beside it is what the manifest
hashes and what the importer reads.

### 1.3 Cases and fixtures

| Source | Target |
| --- | --- |
| `backend/manual_cases/case_00{1,2,3}_*/input.json` | `logic/tests/cases/case_00{1,2,3}_*/input.json` |
| `backend/manual_cases/case_00{1,2,3}_*/expected.json` | `logic/tests/cases/…/expected.json` |
| `backend/manual_cases/case_00{1,2,3}_*/golden.normalized.json` | `logic/tests/golden/case_00{1,2,3}_*.golden.normalized.json` |
| `backend/padnext_examples/*_padx.xml` + `.padx` | `logic/tests/cases/padnext/` (+ the `.auf` order file extracted from the container, so the example is rebuildable) |

### 1.4 Engine code — refactored, not copied

| Source | Target | Change |
| --- | --- | --- |
| `backend/app/models.py` | `apps/engine/app/schemas/{common,case,facts,solver,result,padnext…}.py` | split by concern; **no field semantics changed**; new `proposal.py`, and `RuleCoverage`/`MissingDocumentation`/`SolveResponse` added (Phase 3) |
| `backend/app/config.py` | `apps/engine/app/config.py` | rewritten: repo-root/env-resolved `LOGIC_DIR`/`DATA_DIR`, new `SOLVER_TIMEOUT_SECONDS`, `CACHE_ENABLED`, `APP_ENV`, `DEBUG`, `CATALOG_VERSION`; **no absolute path literals** |
| `backend/app/catalog.py` | `apps/engine/app/catalog/catalog_loader.py` | import paths only |
| `backend/app/bridge/{entity_to_ziffer,vocabulary}.py` | `apps/engine/app/bridge/` | import paths only |
| `backend/app/rules/rule_store.py` | `apps/engine/app/rules/rule_store.py` | import paths only |
| `backend/app/rules/goae_facts.py` | `apps/engine/app/solvers/souffle_facts.py` | moved next to the engine that writes them |
| `backend/app/rules/souffle_engine.py` | `apps/engine/app/solvers/souffle_engine.py` | reads `.dl` from `LOGIC_DIR` |
| `backend/app/optimization/clingo_solver.py` | `apps/engine/app/solvers/clingo_solver.py` | **hard timeout added** (Phase 3.2); reads `.lp` from `LOGIC_DIR`; `missing_documentation` derived |
| `backend/app/validation/validator.py` | `apps/engine/app/validation/validator.py` | import paths only |
| `backend/app/pipeline.py` | `apps/engine/app/services/pipeline.py` | LLM branch removed; rule-coverage + missing-documentation surfaced |
| `backend/app/padnext/{audit,reader,models}.py` | `apps/engine/app/padnext/` | import paths; rule-coverage block added to the report |
| `backend/app/limits.py` | `apps/engine/app/core/limits.py` | unchanged behaviour |
| `backend/app/extraction/prompts.py` | `apps/engine/app/core/extraction_prompts.py` | constants only — the frozen "no fee-schedule vocabulary" contract the schema-leak test asserts |
| `backend/app/main.py` | `apps/engine/app/main.py` + `app/api/{health,solve,padnext,proposals,catalog}.py` | split into routers; POC UI/LLM endpoints dropped (§2) |
| `backend/app/cli.py` | `apps/engine/scripts/engine_cli.py` | `check` / `check-souffle` / `code` / `catalog` retained as an ops tool |
| `backend/scripts/{fetch,import}_goae.py` | `apps/engine/scripts/` | catalog provenance tooling — without it the catalog cannot be rebuilt from source |
| `backend/scripts/generate_facts.py`, `make_padnext_example.py` | `apps/engine/scripts/` | debugging + fixture regeneration |

### 1.5 Tests

| Source | Target | Priority |
| --- | --- | --- |
| `tests/conftest.py` | `apps/engine/tests/conftest.py` | fixtures |
| `tests/test_manual_cases.py` | `tests/test_manual_cases.py` | **golden acceptance + determinism** |
| `tests/test_golden_normalization.py` | `tests/test_golden_normalization.py` | **golden** — *executed differently: the normaliser went to `app/core/canonical.py`, not `tests/golden.py`, because the cache key and the receipt hash are computed over it and it is therefore engine code, not test scaffolding. See the report §1.4.* |
| `tests/test_golden_snapshot_present.py` | `tests/test_golden_snapshot.py` | **golden**, plus a new in-process snapshot comparison |
| `tests/test_clingo.py` | `tests/test_clingo.py` | **brute-force differential + legal posture** |
| `tests/test_property.py` | `tests/test_property.py` | **property-based** |
| `tests/test_souffle.py` | `tests/test_souffle.py` | rules engine |
| `tests/test_validation.py` | `tests/test_validation.py` | validation + exact money |
| `tests/test_padnext.py` | `tests/test_padnext.py` | PADnext |
| `tests/test_catalog_snapshot_identity.py` | `tests/test_catalog_snapshot_identity.py` | **provenance** |
| `tests/test_bridge_and_data.py` | `tests/test_bridge_and_data.py` | bridge + rule store |
| `tests/test_schema.py` | `tests/test_schema.py` | frozen input contract |
| `tests/test_api.py`, `test_api_envelope.py` | merged into `tests/test_api.py` + `tests/test_api_envelope.py` | HTTP contract |
| `tests/test_request_limits.py` | `tests/test_request_limits.py` | perimeter |
| `tests/test_import_goae.py` | `tests/test_import_goae.py` | importer/provenance |
| — | `tests/test_production_fixes.py` (new) | cache key, receipt hash, proposal lifecycle, timeout, rule coverage |

## 2. Intentionally NOT migrated

| Not migrated | Reason |
| --- | --- |
| `frontend/**` (all of it) | brief: no POC frontend UI, no marketing pages, no legacy pages. `apps/web` stays as it is |
| `backend/app/static/manual.html`, `deck.html` + `GET /manual`, `/deck`, `/`(redirect) | POC-only UI served by the API |
| `demo_fallback/**`, `scripts/demo_snapshot.sh`, `tests/test_demo_snapshot.py` | offline demo fallback UI |
| `tests/test_deck.py`, `test_legacy_ui.py`, `test_ui_i18n.py` | assert on `deck.html` / `manual.html` / the static UI's i18n dictionary — the artefacts being dropped |
| `backend/app/extraction/llm_extractor.py`, `openai` dependency, `POST /api/v1/code`, `POST /api/v1/code/extract` | experimental LLM path. `EXTRACTION_MODE=manual` is the mandated default; a production engine should not carry an LLM SDK for a disabled path. The **boundary** is kept: `extraction_prompts.py`, its forbidden-vocabulary list, the schema-leak test, and `docs/architecture/ENGINE.md` |
| `GET /api/v1/padnext/example`, `GET /api/v1/manual_cases` | endpoints that serve test fixtures to the POC demo UI |
| `backend/data/raw/goae_source.zip` | 1.1 MB duplicate of the extracted XML that the manifest hashes |
| `backend/verify_case_001.py` (as a script) | 779-line HTTP-driving script with case-001 expectations baked into env-var defaults. Its `canonical()`/`VOLATILE_KEYS` normaliser — the part the tests depend on — is migrated to `tests/golden.py`; the assertions it made are already covered by `test_manual_cases.py` + the new in-process golden test |
| `backend/scripts/release_gate.sh`, `verify_ui_logic.mjs`, `scripts/verify.sh` | POC release gate wired to the POC's two apps and the static UI |
| `backend/docs/{ARCHITECTURE,GOAE_DATA,TESTING,PRESENTING}.md`, `docs/interview/**`, `docs/LEGACY_UI.md`, `REMEDIATION.md` | interview/presentation material. Provenance content is re-stated in `docs/architecture/ENGINE.md` and `data/raw/README.md` |
| `backend/docker-compose.yml`, `frontend/Dockerfile`, `.claude/` | replaced by `infra/docker/docker-compose.yml`; POC-local editor config |
| `backend/.venv/` | a virtualenv |

## 3. Mandatory production fixes (P0)

1. **Config** — `app/config.py` on `pydantic-settings`. `APP_ENV`, `DEBUG=false`,
   `EXTRACTION_MODE=manual`, `SOLVER_TIMEOUT_SECONDS=5`, `CACHE_ENABLED=true`,
   `UNVERIFIED_RULE_POLICY=warn`, `LOGIC_DIR`, `DATA_DIR`, `CATALOG_VERSION` (read from the
   catalog file when unset), `SOUFFLE_BIN`, clingo version read from the library. No absolute
   path literals; `apps/engine/.env.example` with safe defaults and no secrets.
2. **Clingo timeout** — `ctl.solve(on_model=…, async_=True)` + `handle.wait(timeout)` +
   `handle.cancel()`. On expiry: return the best model found so far with
   `solver_status="TIMEOUT_PARTIAL"`, or raise `ClingoTimeout` when nothing was found. Never
   unbounded. The route stays a **`def`** (not `async def`) so FastAPI runs the CPU-bound solve
   in its threadpool and the event loop is not blocked.
3. **Content-addressed cache** — SHA-256 over `{catalog_version, catalog_sha256, rules_version,
   rules_hash, canonical facts, solver_version, souffle_version, policy settings, logic_version}`.
   In-memory LRU behind a `CacheBackend` protocol so Redis can replace it. Stores solver result,
   proof atoms, warnings, rule-coverage counts, receipt hash, `created_at`.
4. **Proposal / approval** — `ProposalStatus{DRAFT,APPROVED,REJECTED,EXPORTED}`, `Proposal`
   schema with every field the brief lists. Solver output is wrapped as `DRAFT`.
   `POST /api/v1/proposals/{id}/approve` (+ `/reject`, `GET`) against an in-memory store.
   No database.
5. **Rule coverage** — `enforced_rule_count`, `advisory_rule_count`,
   `suppressed_unverified_rule_count`, `policy_for_unverified_rules`, and a warning whenever
   advisory rules exist, on **every** solve and audit response.
6. **Missing documentation** — structured `missing_documentation[{ziffer, current_factor,
   possible_factor, missing}]`, derived only from what the existing logic already emits
   (`justification_required` ∧ no justification present, and the ladder's own
   headroom). The ASP objective is not touched.
7. **Receipt hash** — `app/services/receipt.py`, SHA-256 over catalog version + sha256, rules
   version + hash, canonical input facts, canonical solver output, policy settings, solver
   versions. Returned on every solve and audit response and stored on the proposal.

## 4. Risks

| Risk | Mitigation |
| --- | --- |
| Splitting `models.py` silently changes a field name or serialiser and breaks the golden snapshot | the golden snapshot **is** the test: `logic/tests/golden/case_001_knee.golden.normalized.json` is compared field-for-field after migration. Any drift fails the suite |
| Moving `.lp`/`.dl` out of the Python package changes what the engines read | `LOGIC_DIR` is asserted at startup and by `test_config_paths`; the `.lp`/`.dl` bytes are diffed against source in the report |
| Adding a solver timeout changes results under load | timeout applies only after a complete optimal model is unavailable; `solver_status` is surfaced. Default 5 s versus ~30 ms observed per case |
| Caching returns a stale result after a rule CSV edit | the rules hash is part of the key; `data/rules/*` and the catalog file are hashed, not merely versioned |
| Dropping the LLM path loses the `EXTRACTION_MODE` contract | setting retained, `llm` rejected with a clear 501 at startup-config level, prompt contract + leak test retained |
| A Soufflé/clingo version bump changes an answer set | both versions are in the receipt hash and the audit trail; `clingo==5.8.0` and Soufflé 2.5 are pinned in `requirements.txt` / the Dockerfile |
| Tests silently skip (no `souffle` on PATH) and the suite looks green | `tests/README.md` documents it and `test_engines_are_available` fails loudly when `REQUIRE_ENGINES=1` |

## 5. Validation plan

1. `pip install -r apps/engine/requirements.txt` into a fresh 3.11 venv (pinned versions).
2. `python -c "import app.main"` — import check.
3. `pytest -q` in `apps/engine` — full suite; failures reported, never suppressed.
4. `python scripts/export_openapi.py` → `packages/contracts/openapi/openapi.json`.
5. `pnpm --filter contracts generate` (openapi-typescript) → `packages/contracts/typescript/`.
6. Golden case: run `case_001_knee` through the new engine in-process and compare against the
   migrated `golden.normalized.json` (expected `130.39 €`, 1030 Punkte, accepted `3,7,301,410,5030`,
   blocked `5,200,300`).
7. Determinism: same case twice, canonicalised, byte-equal.
8. Byte-diff the migrated `.lp`, `.dl`, catalog JSON and rule CSVs against `SOURCE_POC`.

## 6. Execution order

Discovery → this plan → logic/data extraction → engine app → P0 fixes → tests → contracts →
Docker/docs → validation → `MIGRATION_REPORT.md`.
