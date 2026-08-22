# Migration report — POC backend → `Govatax` monorepo

Executed against the plan in [`MIGRATION_PLAN.md`](./MIGRATION_PLAN.md).

```
SOURCE_POC      /home/oussama/Desktop/MVP/SOURCE_POC        READ-ONLY — provably untouched
TARGET_MONOREPO /home/oussama/Desktop/MVP/TARGET_MONOREPO   all writes here
```

**Status: complete.** 570 tests pass in a checkout, 566 pass + 4 documented repo-hygiene skips
inside the container image. The three frozen golden snapshots produced by the POC engine are
reproduced **field for field**, and the same input yields the same 64-hex receipt hash on the host
venv and inside the Docker image.

`SOURCE_POC` was verified untouched: no file under it has an mtime later than 2026-08-06, and the 49
dirty paths its git status reports predate this work (last commit `fc8af19`, 2026-07-29).

---

## 1. What was migrated

### 1.1 Logic — byte-identical

| Target | Source | Verified |
| --- | --- | --- |
| `logic/asp/goae_optimize.lp` | `backend/app/optimization/goae_optimize.lp` | `cmp` identical |
| `logic/datalog/goae_rules.dl` | `backend/app/rules/goae_rules.dl` | `cmp` identical |

Not a character changed. The objective ordering (`@5` analog collision → `@4` coverage → `@3`
evidence → `@2` specificity → `@1` points), the two integrity constraints and the factor ladder are
as they were, and `test_production_fixes.py::test_the_objective_ordering_is_untouched` now asserts
each term individually plus that no new priority level was introduced.

Both files moved *out* of the Python package and are read at runtime through `LOGIC_DIR`, so the
legal reasoning is reviewable without reading Python.

### 1.2 Data — byte-identical, provenance intact

| Target | Source |
| --- | --- |
| `data/catalogs/goae_current/{goae.official.json, overrides.json, unparsed_rows.json}` | `backend/data/catalog/` |
| `data/rules/*.csv` (7) + `import_report.json` | `backend/data/rules/` |
| `data/mappings/entity_to_ziffer.csv` | `backend/data/mappings/` |
| `data/raw/{goae_source.xml, manifest.json, README.md}` | `backend/data/raw/` |
| `data/licensed/README.md` | `backend/data/licensed/` |

All 17 files `cmp`-identical to source. Provenance preserved verbatim:
`catalog_version = goae_official_snapshot_2026-07-25`, `rules_version = auto_extracted_2026-07-25`,
`source.sha256_raw = d920ed67…78aa`, `retrieved_at = 2026-07-25T14:08:38+00:00`,
`legal_status = "Amtliches Werk, gemeinfrei nach § 5 UrhG"`, `coverage.rule_coverage = partial`,
`punktwert_cent = 5.82873`.

Rule verification flags, row-for-row:

| File | Rows | Verified |
| --- | --- | --- |
| `exclusions.csv` | 837 → 837 | 0 → 0 |
| `exclusions.manual.csv` | 30 → 30 | 30 → 30 |
| `zielleistung.csv` | 0 → 0 | 0 → 0 |
| `zielleistung.manual.csv` | 3 → 3 | 3 → 3 |
| `specificity.csv` | 2 → 2 | 2 → 2 |
| `factor_caps.csv` | 22 → 22 | 0 → 0 |
| `analog_candidates.csv` | 3 → 3 | 0 → 0 |

**No unverified rule was deleted and none was promoted to verified.**

### 1.3 Cases and fixtures — byte-identical

`logic/tests/cases/case_00{1,2,3}_*/{input,expected}.json`,
`logic/tests/golden/case_00{1,2,3}_*.golden.normalized.json`, and the PADnext delivery in
`logic/tests/cases/padnext/`. The `.auf` order file was extracted from the committed `.padx`
container (it was deleted from the POC's working tree) so the fixture is rebuildable with
`scripts/make_padnext_example.py`.

### 1.4 Engine code — refactored into `apps/engine`

6 863 lines of app code, 5 439 of tests, 1 893 of scripts.

| Target | From | What changed |
| --- | --- | --- |
| `app/schemas/{common,case,facts,solver,result,proposal,padnext,meta}.py` + `__init__.py` | `app/models.py` (529 lines) + `app/padnext/models.py` | split by concern, re-exported as one namespace. **No field semantics changed** — the golden test proves it |
| `app/config.py` | `app/config.py` | rewritten (see §3.1) |
| `app/catalog/catalog_loader.py` | `app/catalog.py` | imports only |
| `app/bridge/{entity_to_ziffer,vocabulary}.py` | same | imports only |
| `app/rules/rule_store.py` | same | imports only |
| `app/solvers/souffle_facts.py` | `app/rules/goae_facts.py` | moved beside the engine that writes them |
| `app/solvers/souffle_engine.py` | `app/rules/souffle_engine.py` | reads the `.dl` from `settings.datalog_path`, with a clear error naming the path it looked in |
| `app/solvers/clingo_solver.py` | `app/optimization/clingo_solver.py` | **hard timeout** (§3.2), `missing_documentation` derivation (§3.6), reads the `.lp` from `settings.asp_path` |
| `app/validation/validator.py` | same | `logic_version`, typed `rule_coverage_detail`, `solver_status`, `missing_documentation` threaded onto the output |
| `app/services/pipeline.py` | `app/pipeline.py` | LLM branch removed; cache, receipt and proposal wrapping added |
| `app/padnext/{reader,audit}.py` | same | settings-aware real-data refusal, rule coverage and receipt on the report |
| `app/core/limits.py` | `app/limits.py` | unchanged behaviour |
| `app/core/extraction_prompts.py` | `app/extraction/prompts.py` | constants only — no client |
| `app/core/canonical.py` | `verify_case_001.py` (`canonical`, `VOLATILE_KEYS`) | promoted from a script to a module: the cache key and the receipt hash are computed over it |
| `app/main.py` + `app/api/{health,solve,proposals,padnext,catalog,deps}.py` | `app/main.py` (398 lines) | split into routers; POC UI and LLM endpoints dropped |
| `scripts/engine_cli.py` | `app/cli.py` | `check` / `check-souffle` / `solve` / `padnext` / `catalog`; `code --manual` became `solve <file>` |
| `scripts/{import_goae,fetch_goae,generate_facts,make_padnext_example}.py` | `backend/scripts/` | repo-root-relative paths via `app.config` |
| `scripts/export_openapi.py` | *new* | §5 |

### 1.5 Tests — 570, none weakened

| File | Tests | Notes |
| --- | --- | --- |
| `test_property.py` | 84 | migrated as-is |
| `test_production_fixes.py` | 64 | **new** — the seven P0 fixes |
| `test_padnext.py` | 57 | migrated; 4 UI-coupled tests replaced (§2) |
| `test_bridge_and_data.py` | 54 | migrated as-is |
| `test_schema.py` | 44 | migrated; prompt import repointed |
| `test_manual_cases.py` | 41 | migrated; endpoint + CLI repointed, determinism strengthened |
| `test_souffle.py` | 36 | migrated as-is |
| `test_clingo.py` | 34 | migrated as-is (includes the brute-force differential) |
| `test_api.py` | 31 | migrated minus UI/LLM; new assertions for DRAFT, receipt, coverage |
| `test_import_goae.py` | 29 | migrated; paths repointed |
| `test_validation.py` | 28 | migrated as-is |
| `test_catalog_snapshot_identity.py` | 24 | migrated as-is |
| `test_golden_normalization.py` | 16 | migrated; now also asserts the cache-key direction |
| `test_golden_snapshot.py` | 11 | migrated + the new in-process snapshot comparison |
| `test_api_envelope.py` | 10 | migrated; endpoint repointed |

Every migrated test that failed did so for a path or an endpoint name, and the path or name was
fixed. **No assertion was relaxed and no test was deleted to make the suite green.**

---

## 2. What was intentionally not migrated

| Not migrated | Why |
| --- | --- |
| `frontend/**` — 90 files, marketing pages, workbench, i18n | brief: no POC frontend UI. `apps/web` untouched apart from one dependency line |
| `app/static/{manual,deck}.html` + `GET /`, `/manual`, `/deck` | POC UI served by the API |
| `demo_fallback/**`, `scripts/demo_snapshot.sh`, `test_demo_snapshot.py` | offline demo fallback |
| `test_deck.py`, `test_legacy_ui.py`, `test_ui_i18n.py` (1 068 lines) | assert on `deck.html` / `manual.html` and the static UI's i18n dictionary — the artefacts being dropped |
| `app/extraction/llm_extractor.py`, `openai==2.48.0`, `POST /api/v1/code`, `POST /api/v1/code/extract` | experimental LLM path. `EXTRACTION_MODE=manual` is mandated; a production engine should not carry an LLM SDK for a disabled path, and sending a real Befund to a third-party API is a § 203 StGB disclosure. **The boundary was kept**: `app/core/extraction_prompts.py`, `FORBIDDEN_PROMPT_TERMS`, all 44 schema-leak tests, and `docs/architecture/ENGINE.md` |
| `GET /api/v1/padnext/example`, `GET /api/v1/manual_cases` | endpoints that served test fixtures to the POC demo UI |
| `verify_case_001.py` (779 lines) | an HTTP-driving script with case-001 expectations baked into env-var defaults. Its `canonical()` / `VOLATILE_KEYS` became `app/core/canonical.py`; its 14 checks are covered by `test_manual_cases.py` + `test_golden_snapshot.py`, in-process and without a running server |
| `scripts/release_gate.sh`, `verify_ui_logic.mjs`, `scripts/verify.sh` | POC release gate wired to the POC's two apps and static UI |
| `backend/docs/*.md`, `docs/interview/**`, `docs/LEGACY_UI.md`, `REMEDIATION.md` | interview and presentation material. Provenance content restated in `docs/architecture/ENGINE.md`, `logic/README.md`, `data/raw/README.md` |
| `backend/docker-compose.yml`, `frontend/Dockerfile`, `.claude/` | replaced by `infra/docker/docker-compose.yml`; POC editor config |
| `data/raw/goae_source.zip` (1.1 MB) | duplicate of the extracted XML the manifest hashes; now gitignored |
| `backend/.venv/` | a virtualenv |

### The four replaced PADnext tests

`test_padnext.py` had four tests that read the POC's `app/static/manual.html` and asserted every
finding type and verdict had an English label there. That page is not in this monorepo, so the
assertion moved to what it was really about — the *contract*: `BlockedCode.reason` and
`PadnextAuditedPosition.verdict` must stay closed `Literal`s so a client can enumerate every label
it needs, and the generated TypeScript in `packages/contracts` carries the same unions. Four new
tests replaced them, plus three asserting the report's new rule-coverage and receipt fields.

---

## 3. P0 fixes implemented

### 3.1 Configuration ✅

`app/config.py` on `pydantic-settings`. `LOGIC_DIR` / `DATA_DIR` are found by walking up from the
module until a directory holding both `logic/` and `data/` appears — which resolves correctly from a
checkout (`apps/engine/app/config.py` → repo root) *and* from the image (`/srv/app/config.py` →
`/srv`) — and either can be overridden by environment. All required settings exist with the mandated
defaults: `APP_ENV=development`, `DEBUG=false`, `EXTRACTION_MODE=manual`,
`SOLVER_TIMEOUT_SECONDS=5`, `CACHE_ENABLED=true`, `UNVERIFIED_RULE_POLICY=warn`, `SOUFFLE_BIN=souffle`.
`CATALOG_VERSION` is empty by default (the catalog states its own version) and, when set, a mismatch
is a **startup failure** rather than a log line. `CLINGO_VERSION` is read from the library.

`.env.example` documents every field, holds no secret, and a test fails if a new setting is added
without documenting it. Another test enumerates the settings schema and fails if any field named
`*key*`, `*secret*`, `*token*`, `*password*` or `*credential*` appears — the engine holds no
credential at all.

`test_no_module_hardcodes_an_absolute_path` scans every `.py` under the engine (in a checkout *and*
in the image) for `/home/`, `/Users/` or a Windows drive literal.

### 3.2 Clingo timeout ✅

Asynchronous solve handle: `ctl.solve(on_model=…, async_=True)` → `handle.wait(timeout)` →
`handle.cancel()`. Models are captured eagerly in the callback, which is what lets a cancelled solve
return a usable answer.

- Timeout **with** a model → that model, `solver_status="TIMEOUT_PARTIAL"`, plus a
  `solver_timeout_partial` warning stating that optimality is unproven while every hard rule still
  holds.
- Timeout **without** a model → `ClingoTimeout` → HTTP `504`, no draft. An empty invoice would be
  indistinguishable from "nothing is chargeable".
- `solver_timeout_seconds` is `gt=0`, so "unbounded" is unrepresentable. `0` and negatives raise.
- The routes that reach a solver are sync `def`, so FastAPI runs them in its threadpool and the event
  loop is never blocked. A test asserts they are not coroutine functions.

`OptimizationResult` gained `solve_ms` and `timed_out`.

### 3.3 Content-addressed cache ✅

Key = SHA-256 over `{catalog_version, catalog_sha256, rules_version, rules_hash, logic_version,
solver_version, rules_engine_version, policy fingerprint, canonical facts}` plus a key-format
version. `rules_hash` hashes every rule CSV and `logic_version` hashes both logic programs, so
editing one cell or one line misses the cache — a cache that could serve a result computed under a
different rule set is a compliance defect, not a performance one. A 9-case parametrised test asserts
each input moves the key.

Stores exactly what the brief requires: `solver_result`, `proof_atoms`, `warnings`, `rule_coverage`,
`missing_documentation`, `receipt_hash`, `created_at`. Backend is a thread-safe bounded LRU behind a
`CacheBackend` protocol (three methods) so Redis drops in without touching a caller.
`CACHE_ENABLED=false` makes every operation a no-op.

A cached hit returns a **new `DRAFT` proposal with a new id**: the result is reusable, the
responsibility for it is not. A test approves a proposal, re-solves, and asserts the second one comes
back `DRAFT` with `approved_by: null`.

### 3.4 Proposal and approval status ✅

`ProposalStatus{DRAFT, APPROVED, REJECTED, EXPORTED}`. `Proposal` carries every field the brief lists
plus `catalog_sha256`, `rules_hash`, `rules_engine_version`, `logic_version`, `rejected_reason`,
`rule_coverage` and `cached`. Solver output is wrapped as `DRAFT` by default.

```
POST /api/v1/proposals/{id}/approve   approved_by REQUIRED — an approval nobody signed is not one
POST /api/v1/proposals/{id}/reject    reason REQUIRED, terminal
POST /api/v1/proposals/{id}/export    reachable only from APPROVED
GET  /api/v1/proposals[?status=]      list
GET  /api/v1/proposals/{id}
```

Transitions are `DRAFT → APPROVED|REJECTED` and `APPROVED → EXPORTED`; anything else is `409`
`illegal_transition`. The store is in-memory, deliberately — `app/services/proposal_store.py` states
what that costs (no durability, not shared between workers) and why no schema was invented (retention,
access control and audit logging are legal questions first).

### 3.5 Rule coverage transparency ✅

Typed `RuleCoverage` on every solve response (`audit_trail.rule_coverage_detail`, plus the counts
flattened onto the proposal), on every PADnext report, and on `GET /api/v1/catalog`:
`enforced_rule_count`, `advisory_rule_count`, `suppressed_unverified_rule_count`,
`policy_for_unverified_rules`, `rule_coverage`, `verified_share`.

Current values: **35 enforced, 862 advisory, 859 of those unverified and not enforced** under the
default `warn`. The solve path warns via `rule_coverage_incomplete` (naming the count); the PADnext
path, which previously said nothing, now emits `advisory_rules_present`. A test switches the policy to
`block` and asserts the counts move — under `block` the suppressed count is 0 and the enforced count
rises.

### 3.6 Missing documentation ✅

`missing_documentation: [{ziffer, current_factor, possible_factor, missing, legal_basis}]` on every
solve response and proposal. Derived **only** from decisions the solver already made — the chosen
factor, the § 5 band, the Leistungslegende cap and whether a written reason is present. The objective
is not consulted and not changed.

For `case_001_knee` it reports four positions (3, 410, 5030, 7) charged at the Schwellenwert where the
band would allow more, and correctly reports **nothing** for GOÄ 301, which carries a documented
reason and is charged at 2.6. A test asserts the invariant that matters: what is billed always equals
`current_factor`, never `possible_factor`.

The pre-existing `justification_required` / `justification_present` / `justification` flags are
untouched and still asserted.

### 3.7 Receipt hash ✅

`app/services/receipt.py`. SHA-256 over catalog version + file hash, rules version + rule-table hash,
logic hash, Clingo and Soufflé versions, policy fingerprint, canonical input facts and canonical
output. Returned on `/solve` (on the proposal) and on `/padnext/audit`. A 9-case parametrised test
asserts each input moves the hash, and another recomputes it independently from the pipeline's own
components and asserts equality.

`case_001_knee` receipts `6bc5f6542c24bad7143172c7b003b2271a46bc7efe5c01b81f8407cce57a22a3` — the
same value from the host venv, from a live `uvicorn` server, and from inside the Docker image.

---

## 4. Test results

```
$ cd apps/engine && .venv/bin/python -m pytest
570 passed in 20.49s

$ docker run --rm govatax-engine:0.3.0 python -m pytest -q
566 passed, 4 skipped in 18.90s
```

The four image skips are repo-hygiene checks that have nothing to assert outside a source checkout,
and each says so: two need `.env.example` (developer documentation, deliberately not copied into the
image), one needs `.gitignore`, one needs a git checkout. They skip in the image and run in CI.

Failures encountered and fixed during the migration, for the record:

| Failure | Cause | Fix |
| --- | --- | --- |
| 66 collection errors / failures on the first full run | POC paths (`padnext_examples/`, `MANUAL_CASES_DIR`), `app.models`, `app.extraction`, `pipeline.run_manual`, `/api/v1/code/rules` | paths and names repointed — no assertion touched |
| `test_no_undeclared_field_was_added` ×3 | the key-walk descended into declared new subtrees | a declared subtree now covers its members |
| `test_the_objective_ordering_is_untouched` | counted `@5` in the `.lp`'s own header comment | count in non-comment lines only; also assert `@2` has exactly two terms and no `@6`/`@0` exists |
| 3 failures **inside the image only** | tests read the ambient environment (`APP_ENV=production`) and `REPO_ROOT/apps/engine`, which does not exist in the image | assert the *field defaults* from the model schema rather than an env-built instance; scan `ENGINE_DIR`, which is real in both layouts; skip the repo-hygiene checks outside a checkout. The default-assertion test is now strictly stronger than it was |

**Nothing was hidden, deleted, or weakened.** The one test-strength change was an increase.

---

## 5. Behaviour differences from the POC

Every difference is deliberate; the golden test enforces that there are no others.

| # | Difference | Why |
| --- | --- | --- |
| 1 | `POST /api/v1/code/rules` → **`POST /api/v1/solve`**, returning a `Proposal` whose `solver_result` is the old `CodingResponse` | the brief mandates `api/solve.py` and a DRAFT wrapper. The POC frontend was not migrated, so nothing consumed the old path |
| 2 | `POST /api/v1/code`, `/api/v1/code/extract`, `GET /`, `/manual`, `/deck`, `/api/v1/manual_cases`, `/api/v1/padnext/example` return **404** | §2. A test asserts each is really gone, so a stale client gets a clean 404 rather than a half-answer |
| 3 | Responses gained `coding.missing_documentation`, `audit_trail.logic_version`, `audit_trail.rule_coverage_detail`, `audit_trail.solver_status` | P0 fixes 3.5–3.6. These four are enumerated in `test_golden_snapshot.py::ADDED_BY_MIGRATION`; **any fifth addition fails the suite** |
| 4 | A solve can now return `solver_status="TIMEOUT_PARTIAL"`, or `504` | P0 fix 3.2. Unreachable at the 5 s default with ~30 ms solves |
| 5 | Second identical request is served from cache (`"cached": true`) | P0 fix 3.3. Byte-identical result, new proposal id |
| 6 | PADnext reports gained `receipt_hash`, `logic_version`, the three coverage counts and an `advisory_rules_present` finding | P0 fixes 3.5, 3.7 |
| 7 | `PADNEXT_ALLOW_REAL_DATA` is now a typed setting as well as an environment variable | the env var still wins, so an operator can tighten it without a restart; a test pins that precedence |
| 8 | `logic/` and `data/` are read from outside the Python package | the brief's layout, and it makes the legal reasoning reviewable without reading Python |
| 9 | `app/models.py` split into eight schema modules | the brief's layout. **No field semantics changed** — the golden snapshot proves it field for field |
| 10 | CLI `code --manual <file>` → `solve <file>` | the flag was redundant once the LLM path was gone |

**What did not change**: every accepted Ziffer, every blocked Ziffer and reason, every factor, every
amount, every proof step, every rule id, every legal basis, the § 6a Minderung, the rounding, and the
catalog and rule identity. `case_001_knee` still bills `3, 7, 301, 410, 5030` at **130.39 €** / 1030
Punkte, blocking `5` (conflict lost to 7 on evidence), `300` (less specific than 301) and `200`
(Zielleistung component of 301).

---

## 6. Remaining risks

| # | Risk | Severity | Mitigation / status |
| --- | --- | --- | --- |
| 1 | **No access control, no audit logging, no PHI handling, no § 203 StGB workflow** | **Blocker for any real data** | fully documented in `docs/compliance/PRIVATE_DATA_WARNING.md`. Synthetic data only |
| 2 | ~~Approvals are in-memory: they do not survive a restart and are not shared between workers~~ | ~~High~~ **closed** | Superseded by the Postgres migration: `proposals` + append-only `audit_events`, Alembic, the lifecycle enforced under a row lock. See [`../architecture/DATABASE.md`](../architecture/DATABASE.md). What remains open from the original note is the *legal* half — retention and access control — tracked in `PRIVATE_DATA_WARNING.md` |
| 3 | Rule coverage is `partial`: 859 unverified rules suppress nothing, and **zero** auto-extracted Zielleistung pairs exist (only 3 hand-verified ones) | High | reported on every response. The engine can miss a § 4 Abs. 2a violation — a human review of the invoice is not optional |
| 4 | The cache is per-process; two workers can hold divergent entries after a rule edit without a restart | Medium | `CacheBackend` protocol is the Redis seam. `CACHE_ENABLED=false` is the safe operational answer during a rule change |
| 5 | Soufflé is an external binary at a pinned version, installed from a GitHub release `.deb` | Medium | pinned to 2.5 in the Dockerfile and recorded in the receipt hash; the build fails if it cannot evaluate a trivial program |
| 6 | `souffle` missing on a developer machine makes rules-engine tests **skip**, so a green run can mean nothing was tested | Medium | documented prominently in `tests/README.md`; CI should run in the image, where 566 pass and only the 4 hygiene checks skip |
| 7 | 256 Ziffern-rows failed to parse at import (`unparsed_rows.json`) and 187 rules need review | Medium | retained beside the catalog rather than dropped; asserted present by `test_catalog_snapshot_identity.py` |
| 8 | The perimeter body-size check reads `Content-Length`, so a chunked request bypasses it and reaches the in-handler check | Low | known and documented in `app/core/limits.py`; defence in depth retained. Proper fix is streaming byte counting |
| 9 | The engine has no rate limiting and no request timeout above the solver's | Low | belongs at the ingress, which does not exist yet |
| 10 | Catalog snapshot is dated 2026-07-25; the GOÄ can be amended | Low | `CATALOG_VERSION` turns a mismatch into a startup failure; `scripts/fetch_goae.py` + `import_goae.py` rebuild from source |
| 11 | `data/raw/goae_source.xml` (1.3 MB) is committed | Low | deliberate: it is what `manifest.json` hashes, and `test_catalog_snapshot_identity.py` asserts the committed catalog was built from the committed snapshot |

---

## 7. Next 10 tasks

1. **Legal review before anything else** — § 203 StGB, GDPR Art. 9, AVV, DPIA, EU hosting. Nothing in
   tasks 2–10 makes real data lawful; this does. (`docs/compliance/PRIVATE_DATA_WARNING.md` is the
   agenda.)
2. **Persist proposals with a tamper-evident audit log** — Postgres + Alembic behind the existing
   `ProposalStore` interface. Record every solve, read, approval, rejection and export with actor and
   timestamp. This is what makes an approval demonstrable, and therefore real.
3. **Authentication, authorisation and multi-tenancy** — per-practice tenancy, per-user roles, least
   privilege. Today every endpoint answers unauthenticated.
4. **Verify the rule set, starting with Zielleistung** — 859 unverified exclusions and only 3
   Zielleistung pairs. Build a review workflow that writes `verified`, `verified_at` and a reviewer
   into the CSVs, and track the enforced count as a project metric. Highest-value work for output
   quality.
5. **Redis-backed cache** behind `CacheBackend`, so multiple workers share one content-addressed
   namespace and a rule edit invalidates everywhere at once.
6. **CI** — `pytest` inside the engine image (not on a bare runner, so nothing skips),
   `export_openapi.py --check`, `pnpm turbo lint typecheck build`, and a `cmp` gate that fails if
   `logic/` or `data/` changed without a corresponding golden-snapshot review.
7. **Build the review UI in `apps/web`** against `@workspace/contracts`: the invoice draft, the proof
   tree per line, blocked positions with their reasons, the documentation gaps, the rule-coverage
   banner, and the approve/reject action. The contract path exists; no screens were built, as
   instructed.
8. **Structured logging with a request id**, plus Prometheus metrics for solve latency, cache
   hit rate, timeout rate and validation-failure rate. `stage_timings_ms` already exists per response
   and is the natural source.
9. **Grow the golden corpus** — 3 synthetic cases is thin for a fee schedule with 2192 positions.
   Target the § 5 bands (A/E/O vs B–D/F–H vs M and Nr. 437), the mutual clusters (5/6/7/8,
   422–424, 650–653), § 6a settings and the Analogansatz path. Each new case is a frozen snapshot.
10. **Close the chunked-body gap** in `RequestSizeLimitMiddleware` with streaming byte counting, and
    add ingress-level rate limiting and request timeouts.

---

## 8. Summary

**Migration status** — complete. All seven P0 fixes implemented. Every file the plan listed was
migrated or explicitly declined, and nothing outside `TARGET_MONOREPO` was written.

**Test status** — 570 passed, 0 failed in a checkout; 566 passed + 4 documented skips in the image.
The three POC golden snapshots reproduce field for field. The same input produces the receipt
`6bc5f654…22a3` on the host, on a live server and inside the container.

**Created** — 121 files: `apps/engine/` 76, `logic/` 15 (including `logic/README.md`), `data/` 17,
`packages/contracts/` 7, `docs/` 4, `infra/docker/` 1, and `.dockerignore`. Modified 6 existing
files: `.gitignore` (Python + licensed-data rules), `package.json` (a `generate:contracts` script),
`turbo.json` (a `generate` task), `apps/web/package.json` (one dependency line), `pnpm-lock.yaml`,
and the root `README.md` (rewritten from the shadcn template stub). **`apps/web` source is
untouched**: it still typechecks, lints and builds, and its only pre-existing lint warning (an
unused `Geist` import in `app/layout.tsx`) is unchanged.

**Skipped** — the entire POC frontend, both static HTML pages and their three test files, the
`demo_fallback/`, the LLM extractor and its two endpoints with the `openai` dependency, the four
fixture-serving endpoints, `verify_case_001.py`, the POC release-gate scripts, and the interview
documentation. Listed exhaustively in §2.

**Critical warnings**

1. 🔴 **Synthetic data only.** No access control, no audit logging, no PHI handling, no § 203 StGB
   workflow. Real data requires legal review first — `docs/compliance/PRIVATE_DATA_WARNING.md`.
2. 🔴 **Rule coverage is partial**: 35 rules enforced, 859 unverified and not enforced, and no
   auto-extracted Zielleistung pairs. The engine can miss a § 4 Abs. 2a violation. Every response
   says so; a human review of the invoice is not optional.
3. 🟠 **Output is a `DRAFT`, never an invoice.** It leaves `DRAFT` only when a named person approves
   it, and that approval currently lives in memory and dies with the process.
4. 🟠 **The objective ordering in `logic/asp/goae_optimize.lp` is the legal posture of the system.**
   `@5/@4/@3/@2/@1` with revenue last, and the hard rules as integrity constraints. Changing any of
   it requires legal and domain review — see `logic/README.md`.
5. 🟡 **No secrets exist anywhere in this engine, and it should stay that way.** A test enumerates the
   settings schema and fails if a credential field appears.
