# The Azmoth GOÄ Rule System — how it actually decides a bill

This document is descriptive, not prescriptive. It follows the real execution path — code that
runs, not filenames that sound authoritative — and cites `file:line` for every claim that can be
pinned to a line. Anything not verified from the code is marked **"Not determined from current
codebase."** No behavior was changed to produce this document.

Scope: `apps/engine/app/`, `apps/engine/logic/` → actually `logic/` at repo root, `data/`,
`apps/engine/scripts/`, `scripts/`.

---

## 0. Data-flow diagram

Two distinct flows share the same rule engine: the **coding path** (turn clinical entities into a
proposed invoice) and the **PADnext audit path** (check an invoice someone else already coded).
They diverge at the point marked `***`.

```
                              ┌─────────────────────────┐
                              │  data/catalogs/<edition>/│
                              │  goae.official.json       │  <- SHA-256'd, versioned per era
                              │  (+ overrides, unparsed)  │
                              └────────────┬─────────────┘
                                           │  Catalog.sha256()
                              ┌────────────┴─────────────┐
                              │   data/rules/*.csv         │  <- exclusions, zielleistung,
                              │   (RuleStore, rule_store.py)│     specificity, factor_caps,
                              │   verified / legal_basis /  │     analog_candidates
                              │   provenance columns        │
                              └────────────┬─────────────┘
                                           │
   CODING PATH                            │                      PADNEXT AUDIT PATH
   ClinicalExtraction (JSON)               │              PadnextDelivery (already-coded XML)
        │                                  │                      │
        ▼                                  │                      ▼
 ┌─────────────┐                           │            group by <abrechnungsfall>  (NOT
 │   bridge/    │  candidate Ziffern        │            <rechnung>! — one per patient
 │entity_to_    │  (deterministic CSV       │            encounter; see §5)
 │  ziffer.py   │   lookup, priorities)     │                      │
 └──────┬──────┘                           │                      │
        │                                  │                      │
        ▼                                  ▼                      ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │   souffle_facts.py :: build_fact_rows()                              │
 │   → .facts files (tab-separated) for every relation in INPUT_RELATIONS│
 │   → SouffleEngine.run(): subprocess `souffle -F facts -D out logic.dl`│
 │     (interpreter mode, no compiled binary)                            │
 │                                                                        │
 │   logic/datalog/goae_rules.dl  (stratified, 7 layers, negation only    │
 │   ever looks one layer up — see §3)                                    │
 │     proposed → surviving_specific → surviving_zielleistung →          │
 │     surviving_exclusion → billable | needs_arbitration → factor_band  │
 │     → mindered  (+ proof, one row per conclusion, positive or negative)│
 └───────────────────────────────┬────────────────────────────────────┘
                                  │  RulesResult (billable, needs_arbitration,
                                  │   blocked_*, conflicts, proof, factor_invalid…)
                       ***────────┼─────────────────────────────────── ***
                        │                                        │
             CODING PATH│                          PADNEXT AUDIT PATH
                        ▼                                        ▼
        ┌───────────────────────────┐            _audit_group() reads RulesResult
        │  ClingoSolver.solve()      │            DIRECTLY — no Clingo call. An
        │  (Python `clingo` bindings,│            already-coded/priced invoice has
        │   not subprocess)          │            nothing left to arbitrate; Soufflé's
        │  logic/asp/goae_optimize.lp│            billable/blocked/conflict facts alone
        │  arbitrates conflicts,     │            drive classify_position() (§6).
        │  picks factors & analogs,  │                        │
        │  objective §4 (revenue     │                        │
        │  is priority 1, LAST)      │                        │
        └──────────────┬────────────┘                        │
                        │  OptimizationResult                  │
                        ▼                                      │
        second SouffleEngine.run() — independent               │
        re-verification of the CHOSEN factors                 │
                        │                                      │
                        ▼                                      ▼
        ┌───────────────────────────┐            classify_position() → one of
        │  Validator.build()         │            confirmed_fine | confirmed_wrong |
        │  exact Decimal money,      │            unconfirmed   (§6)
        │  AuditTrail, receipt_hash  │                        │
        └──────────────┬────────────┘                        │
                        ▼                                      ▼
              Proposal (status=DRAFT)                 PDF / Prüfbericht / API JSON
              receipted, awaiting human                (per-position findings +
                        │                                rule_id → legal_basis → proof)
                        ▼
                 PDF / API response
```

---

## 1. Where GOÄ codes live

**Format.** Each catalog edition is a directory under `data/catalogs/<edition>/` (found:
`goae_1996`, `goae_2012`, `goae_current`, `goae_2026_current`, `goae_neu_draft`) holding a single
JSON file, `goae.official.json` (`CATALOG_FILENAME`, `apps/engine/app/config.py:64`), plus optional
`overrides.json` and `unparsed_rows.json` (config.py:65,72). Only `goae_current` is a real official
snapshot; the others are synthetic fixtures — `goae_1996/goae.official.json` carries
`"synthetic": true` and publisher `"Azmoth engine test fixtures — kein amtliches Werk"`, while
`goae_current` carries no `synthetic` key and publisher `"Bundesamt für Justiz / Bundesministerium
der Justiz"`. Loading a synthetic catalog logs a warning
(`apps/engine/app/catalog/catalog_loader.py:298-305`).

Top-level JSON keys: `catalog_version`, `source` (incl. `sha256_raw` of the upstream XML download),
`rules_version`, `punktwert_cent`, `rounding`, `minderung`/`minderung_exempt_ziffern`,
`factor_bands`, `special_factor_ziffern`, `coverage`, and `ziffern` — a list of Ziffer objects
(`ziffer`, `official_text`, `punkte`, `category`, `section`, `status`, `provenance`, `rule_coverage`,
`text_quality`, `minderung_exempt`).

**Versioning.** `resolve_catalog_dir()` (`catalog_loader.py:115-171`) maps an edition name to
`data/catalogs/{edition}/`; an unknown edition raises `CatalogNotFoundError` (HTTP 404,
`catalog_loader.py:68-93`) rather than silently falling back to another era — the module docstring
calls the wrong alternative "answering a question about 2019 with 2026 money" (line 23). Directory
names are validated against `_VERSION_RE` (line 98) to block path traversal. Each loaded `Catalog`
keeps `routed_version` (the directory it came from) separate from `catalog_version` (what the JSON
itself claims, line 227-232), so a mislabelled directory is detectable rather than silently trusted.

**SHA-256 pinning — two distinct hashes, easy to conflate:**
- `source.sha256_raw` — hash of the *raw upstream XML download*, recorded in
  `data/raw/manifest.json` and copied into the built catalog's `source.sha256_raw` field
  (`catalog_loader.py:215,346`). Answers "did the government's XML change?"
- `Catalog.sha256()` (`catalog_loader.py:465-467`) — `hashlib.sha256(self.path.read_bytes()).hexdigest()`,
  a hash of the *built* `goae.official.json` file. This is the one that travels: stored per-audit as
  `catalog_sha256` (`apps/engine/app/db/models.py:193`), threaded through `pipeline.py:178,360` and
  `padnext/audit.py:1559`, printed on PDFs as "Katalog-SHA-256" (`services/pdf.py:1370,1824`), and
  is one of the ten inputs to `receipt_hash()` (§7). **Changing one byte of the catalog JSON changes
  every receipt hash ever issued against it** — this is by design, not a bug to route around.

A third identity hash exists alongside it: `Settings.logic_version` (`apps/engine/app/config.py:534-544`)
is `sha256(datalog_path.read_bytes() + b"\0" + asp_path.read_bytes() + b"\0")` — i.e. the `.dl` and
`.lp` source files are hashed together, so editing either one moves `logic_version`, the cache key,
and the receipt without a human needing to bump a version string.

---

## 2. Where rules live

`data/rules/*.csv`, loaded by `RuleStore` (`apps/engine/app/rules/rule_store.py`):

| File | Columns | Rows | Source |
|---|---|---|---|
| `exclusions.csv` | `rule_id,from_ziffer,to_ziffer,direction,legal_basis,quote,verified,verified_at,source,parser_verdict,parser_reason,parser_provision,review_note,ai_verdict,ai_reasoning,ai_model,ai_checked_at` | 837 | `deterministic_parser:auto_extracted:*` |
| `exclusions.manual.csv` | (no parser/ai columns) | 31 | `manual_verification` |
| `exclusions.residue.csv` | + `parser_verdict, parser_reason, review_note` | 7 | quarantined rows (see §8) |
| `zielleistung.manual.csv` / `zielleistung.csv` | `rule_id,parent_ziffer,child_ziffer,legal_basis,quote,verified,verified_at,source` | 4 / 0 | manual |
| `specificity.csv` | `rule_id,specific_ziffer,general_ziffer,legal_basis,quote,verified,verified_at,source` | 3 | manual |
| `factor_caps.csv` | + `ai_verdict,ai_reasoning,ai_model,ai_checked_at` | 23 | `ai_verified:<model>:*` |
| `analog_candidates.csv` | `rule_id,source_entity_type,target_ziffer,similarity,legal_basis,quote,verified,verified_at,source` | 4 | `illustrative` (unverified) |
| `factor_bands.csv` | `category,threshold,max,legal_basis,verified,verified_at` | 17 | manual; **baked into the catalog JSON's `factor_bands` key by `import_goae.py`, not read by `rule_store.py` at all** — `souffle_facts.py:150-153` reads `catalog.factor_bands`. |

**Column meaning:**
- `verified` — gates enforcement. `_admit()` (`rule_store.py:246-263`): a `rejected` row is always
  suppressed; a `verified` row is always enforced; an unreviewed row's fate depends on
  `UnverifiedRulePolicy` (`config.py:124-127`: `WARN` default suppresses it with a warning, `BLOCK`
  enforces it anyway, `IGNORE` drops it silently).
- `legal_basis` — the cited GOÄ provision text, stored verbatim on `Rule.legal_basis`
  (`rule_store.py:79`) and carried all the way to the API/PDF (§7).
- `source` / `provenance` — who or what produced the row. `Rule.provenance` (property,
  `rule_store.py:114-126`) bundles `legal_basis, quote, verified, source, review_status,
  reviewed_by`. `Rule.hand_verified` (lines 101-112) checks `source.startswith("manual")` — used to
  prefer a curated citation over a machine-derived one when two rows collide
  (`_dedupe_exclusions`, lines 289-318).

**Quarantined rows.** `deterministic_rule_parser.py` re-derives every exclusion sentence
independently of `import_goae.py` and, for a row it cannot confidently confirm, writes
`parser_verdict = QUARANTINE = "NEEDS_HUMAN_REVIEW"` (`deterministic_rule_parser.py:314`) to
`exclusions.residue.csv` with a human-readable `review_note`. Live count:
`data/rules/deterministic_parse_report.json` — 837 examined, 831 confirmed, 6 quarantined (all
`conditional`). A `PENDING`/`REJECTED`/`VERIFIED` review can later be layered on top from Postgres
via `RuleStore.with_reviews()` (`rule_store.py:165-187`), which re-runs `_admit()` from scratch
rather than mutating in place.

---

## 3. Soufflé: fact generation, stratification, blocked vs. billable

**Fact generation** (`apps/engine/app/solvers/souffle_facts.py:78-176`, `build_fact_rows()`) is the
single place every `.decl … .input` relation in `logic/datalog/goae_rules.dl` gets populated:

| Relation | Source | Line |
|---|---|---|
| `ziffer` | `Catalog` entries (punkte/category/is_active) for the case's relevant Ziffern | 108-115 |
| `exclusion`, `zielleistung`, `specificity`, `factor_cap` | `RuleStore` (admitted rows only, filtered to relevant Ziffern) | 131-163 |
| `act`, `candidate` | `BridgeResult` (clinical extraction → candidate Ziffern) | 146-149 |
| `sf_band`, `sf_override` | `Catalog.factor_bands` / `Catalog.special_factor_ziffern` | 150-158 |
| `proposed_factor` | caller-supplied `proposed_factors` dict (chosen factor for verification pass, or a PADnext-claimed `faktor`) | 164-166 |
| `patient_setting`, `minderung_rate`, `minderung_exempt` | extraction + `Catalog` | 167-174 |
| `datum` | `bridge.acts[*].service_date` joined to candidates by `act_id` — **only populated when a caller sets `service_date`, which today is the PADnext audit path** (`padnext/audit.py:442`) | 119-127 |

`write_fact_files()` (line 179) hard-fails if the emitted relations don't exactly match
`INPUT_RELATIONS` — a schema drift between Python and the `.dl` file is a startup error, not a
silent gap.

**Invocation** (`apps/engine/app/solvers/souffle_engine.py:146-187`): writes the `.facts` files to a
temp dir and runs `souffle -F <facts_dir> -D <out_dir> <logic/datalog/goae_rules.dl>` via
`subprocess.run(..., timeout=souffle_timeout_s)`. **Interpreter mode** — the `.dl` source path is
passed directly, no compiled C++ binary — the docstring is explicit: "no C++ toolchain needed at
runtime." Only `OSError` is retried (up to 3 attempts, lines 121-126); a non-zero exit or timeout is
not retried. Outputs are Soufflé's default tab-separated `.csv` files, one per `.output` relation,
parsed back by `_parse()` (lines 226-375) into a `RulesResult`.

**Stratification** (`logic/datalog/goae_rules.dl:7-16`): suppression in the GOÄ is layered —
`proposed → surviving_specific → surviving_zielleistung → surviving_exclusion → billable`. Each
layer's negation looks only at the layer immediately above it, which is why the whole program is
stratified and has a unique minimal model. The file's own comment states the alternative explicitly
rejected: "A single self-referential `blocked` relation — the obvious first attempt — is NOT
stratifiable and would either be rejected outright or quietly produce a wrong model." (lines 14-16)

**`blocked_*` vs. `billable`:**
- A position is `blocked_less_specific`, `blocked_zielleistung`, or `blocked_exclusion` when a hard
  rule fires against it one-directionally (lines 114-208) — these are certain, monotone
  conclusions.
- `billable` = survived every hard rule **and** has no mutually-exclusive competitor
  (`goae_rules.dl:228-230`).
- `needs_arbitration` = survived every hard rule but **does** have a mutual competitor
  (`conflict`, line 233-235) — handed to Clingo, not decided here. Mutual clusters (e.g. Nr. 5/6/7/8,
  Nr. 422-424) are deliberately *not* resolved by negation-as-failure: under NAF every member would
  block every other and the whole cluster would silently vanish, destroying a legitimate charge
  (lines 18-23). Datalog exports `conflict` and refuses to guess.
- `blocked_exclusion_cross_date` (lines 186-194) is a **separate** relation from
  `blocked_exclusion`, for the case where two Ziffern are known to have been rendered on different
  dates. It is deliberately excluded from `billable`/`surviving_exclusion` — a human still has to
  look at it, because "Neben" (alongside) is a clinical, same-encounter term, not a bookkeeping one.

Every conclusion — positive and negative — is exported as a `proof(Z, rule, detail, rule_id)` row
(lines 284-326), so any verdict is machine-traceable back to the CSV row and legal quote that
produced it.

---

## 4. Clingo: when it runs, when it doesn't, and the objective hierarchy

**Fact translation** (`apps/engine/app/solvers/clingo_solver.py:168-250`, `build_facts()`) restricts
everything to `in_play = billable ∪ arbitration_candidates ∪ analog_ziffern` (lines 182-186) and
emits ASP text facts: `code_info/3`, `sf/3`, `cap/2` from catalog/rule data (188-198); `conf/2`,
`spec_priority/2` from the strongest candidate per Ziffer (200-210); `fixed/1` from
`billable` (212-213); `arbitrate/1` from `arbitration_candidates` (214-215); `conflict_pair/2` from
`conflicts` (216-217); `analog_needed/2`/`analog_cand/3` from analog requests (219-226);
`excluded/2`/`zielleistung/2` restricted to `in_play` (228-233); `justification/2`,
`encounter_justification/1`, `base_policy/1` from settings/extraction (235-249). **Soufflé and
Clingo are chained through the Python `RulesResult` object, not through shared files.**

**Invocation** (`clingo_solver.py:24,271-304`): via the **Python `clingo` module bindings**, not a
subprocess — `clingo.Control(["--models=0", "--opt-mode=opt"])`, program text = the `.lp` file
contents concatenated with the generated facts, grounded, then solved asynchronously
(`ctl.solve(on_model=on_model, async_=True)`) bounded by `handle.wait(timeout)` /
`handle.cancel()`. The best model's shown atoms are parsed by `_parse_model()` (lines 368-572) into
an `OptimizationResult`.

**Objective hierarchy** (`logic/asp/goae_optimize.lp:14-26`, lexicographic, `#minimize`/`#maximize`
at explicit priority levels — **higher number wins first**):

| Priority | What it optimizes | Why |
|---|---|---|
| `@5` | never charge an analog position already charged directly; never leave a § 6 Abs. 2 request uncovered when a legal candidate exists | soft, so an over-constrained candidate set degrades to a warning, not UNSAT |
| `@4` | never drop a documented, chargeable service off the invoice entirely | `covered/2` over `conflict_pair` |
| `@3` | stronger clinical evidence wins | decides e.g. Nr. 5 vs. Nr. 7 |
| `@2` | more specific position wins | `spec_priority` |
| `@1` | higher total points | **tiebreaker only** |

The file states the intent directly: "Evidence and specificity outrank money on purpose. An
objective that maximised revenue would systematically pick whichever of two competing positions
pays more, which is upcoding." No objective can override a hard constraint (lines 89-110): a charged
position must not co-occur with something it excludes or is a component of (`:- charged(A),
charged(B), excluded(A,B), A!=B.` / `:- charged(C), charged(P), zielleistung(P,C).`) — these are
integrity constraints, immune to the objective.

**When Clingo is NOT invoked.** The normal coding path (`Pipeline.run_symbolic`,
`apps/engine/app/services/pipeline.py:212-268`) always runs Soufflé then Clingo then a second
Soufflé verification pass. The **PADnext audit path does not call Clingo at all**. All three PADnext
callers build a full `Pipeline` (which constructs both `self.souffle` and `self.clingo`,
`pipeline.py:102-104`) but wire only the Soufflé callable into the audit function:
`apps/engine/app/api/audit.py:264`, `apps/engine/app/api/padnext.py:149`,
`apps/engine/app/services/batch_audit.py:244` — all pass `souffle_run=pipe.souffle.run`; none
references `pipe.clingo`. `padnext/audit.py`'s own docstring explains why: "A PADnext file arrives
already coded, so this is not the coding pipeline — it is the coding pipeline run backwards... there
is no arbitration/optimization choice left to make." The claimed positions and their claimed
factors (`faktor`) are fed in as `candidate`/`proposed_factor` facts, and Soufflé's `billable` /
`blocked_*` / `invalid_factor*` relations alone drive `classify_position()` (§6). Clingo's whole job
— choosing among `needs_arbitration` candidates, picking factors, picking analogs — is structurally
moot when the invoice already made those choices; the engine's job is to check them, not repeat
them.

---

## 5. The grouping key: `<abrechnungsfall>`, and why

PADnext nests positions as `<lieferung><rechnung><abrechnungsfall><position>`. `audit_delivery`
groups strictly at `<abrechnungsfall>` — one patient encounter — never at the wider `<rechnung>`
(invoice) or the whole delivery. The reason is a fixed bug, documented in a block comment at
`apps/engine/app/padnext/audit.py:797-815`: the Datalog rules engine is keyed by Ziffer alone
(`billable(z)`, `blocked_exclusion(z, blocked_by, rule_id)`) with no patient/case dimension built
in. Before the fix, `PadnextDelivery.positions()` flattened every position in the delivery into one
list before handing it to Soufflé, so an exclusion like `excl_auto_34_4` "fired the moment GOÄ 34
and GOÄ 4 both appeared *anywhere* in the batch" — false positives scaling quadratically with
delivery size, and worse, convicting one patient's GOÄ 4 because a *different* patient happened to
have billed GOÄ 34.

The fix: `audit_delivery` (`audit.py:1455-1473`) builds one `(rechnungs_id, abrechnungsfall_id,
positions)` group per case and calls `_audit_group()` once per group — Soufflé runs once per
patient encounter, never once per delivery. The per-position duplicate-Ziffer check received the
same fix for the same reason (comment at `audit.py:879-893`; commit `c09c3bb`, "scope duplicate
check per billing case").

Git history confirms this was a real production defect, not a hypothetical: commit `7f917db` ("fix:
stop a verified exclusion from firing across patients and service dates") states the bug plainly —
`excl_auto_34_4` fired "even when [the two Ziffern] belonged to different patients... or to the
same patient's services months apart" — and adds `case_f_cross_patient_boundary` and
`case_g_cross_date_same_patient` as permanent regression fixtures. A related, separate defect —
findings attributed by `positionsnr` alone (which collides across cases, since PADnext numbers
positions per-case starting at 1) — is fixed by keying findings off `id(row)` instead
(`bug_positionsnr_collision` golden case).

**This is the single most safety-critical invariant in the audit path**: any refactor of
`audit_delivery`/`_audit_group` must preserve "never build a fact base wider than one
`<abrechnungsfall>`." See the do-not-touch list, item 1.

---

## 6. PASS/FAIL/UNKNOWN → confirmed_fine / confirmed_wrong / unconfirmed

`classify_position()` (`apps/engine/app/padnext/audit.py:680-794`) is the single place a position's
fate is decided, and its own docstring states the design rule: *"The order of the tests is the
argument. Proof that a position is wrong comes first and is not softened by advisory noise.
Everything that follows is a reason we cannot speak, and only a position that survives all of them
is called safe."* In order (first match wins):

| # | Condition | Bucket |
|---|---|---|
| 1 | `verified_defects` non-empty (a verified check — e.g. `invalid_factor`, `invalid_factor_cap`, arithmetic mismatch — actually failed) | `confirmed_wrong` |
| 2 | `blocked` and the position is a **mutual-exclusion survivor** (needs_arbitration, no way to say which side loses) | `unconfirmed` |
| 3 | `blocked` and the blocking rule is verified **and** `cross_date_match` is true | `unconfirmed` |
| 4 | `blocked` and the blocking rule is verified (plain, same-date/undated one-way exclusion) | `confirmed_wrong` |
| 5 | `verdict == "out_of_scope"` (a non-GOÄ Gebührenordnung) | `unconfirmed` |
| 6 | `verdict == "surcharge_not_modelled"` (percentage Zuschlag, e.g. Nr. 441) | `unconfirmed` |
| 7 | `verdict == "unknown_ziffer"` | `unconfirmed` |
| 8 | `blocked` but no verified rule fired (Soufflé didn't confirm it, but nothing proven either) | `unconfirmed` |
| 9 | unresolved advisory (unverified) rules touch this Ziffer | `unconfirmed` |
| 10 | not accepted as claimed for an unverified reason | `unconfirmed` |
| 11 | no verified rule covers this Ziffer at all | `unconfirmed` |
| 12 | (fallthrough — survived everything above) | `confirmed_fine` |

Note there is no separate "FAIL" bucket beyond `confirmed_wrong`; "PASS" is `confirmed_fine`, and
everything the engine cannot prove either way collapses into `unconfirmed` rather than defaulting to
either extreme — absence of a confirmed defect is explicitly *not* treated as proof of correctness
(rule 8's comment: "'Not confirmed' is the absence of evidence, so it must not be counted as
evidence of a defect").

**Cross-date handling** (rule 3 above) is the one place a hard Datalog conclusion is deliberately
*softened* on the Python side. `blocked_exclusion_cross_date` in `goae_rules.dl` fires when the
solver knows — from `datum` facts — that the two excluded Ziffern were rendered on different
service dates; `cross_date_match` is read straight off `BlockedCode.cross_date`
(`audit.py:1340-1346`) and is `None` (not `False`) whenever nothing suppressed the position at all,
or either side's date was unknown — the docstring is explicit that unknown-date must never read as
"different dates," or a caller that never tracks dates would have every exclusion look cross-date.
This was originally a Python-side date comparison inside `classify_position` itself (commit
`43eccf6`), then moved into Datalog proper (commit `7f917db`) once `datum` facts existed, "retiring
the classify_position Python workaround for it" — i.e. the rule engine, not the audit function, is
now the source of truth for what counts as "alongside."

---

## 7. Provenance chain: rule_id → legal citation → proof row → receipt_hash

**Rule → legal citation.** A blocked position's `legal_basis` is not looked up separately at
classification time — it travels *on* the solver's own output object
(`BlockedCode.legal_basis`, `apps/engine/app/schemas/facts.py:76`) all the way from
`goae_rules.dl`'s `proof` relation through `RuleStore` (which stamped `legal_basis` onto the CSV row
in the first place) to `SouffleEngine._parse()`. `_audit_group` copies it straight onto both the
report row and the `PadnextFinding` shown to the user (`audit.py:1064-1090`). A later lookup,
`RuleStore.rule_by_id()` (`rule_store.py:483-491`), exists specifically so the *verification* step
can ask "is the rule that blocked this position actually verified?" (`blocking_rule_verified`,
`audit.py:1333-1338`) — a second, independent use of `rule_id` from the first.

**Proof row.** For a billable position, `audit.py:923-925` collects every `proof` step Soufflé
emitted for that Ziffer (`proof_by_ziffer`) and attaches the sorted list as `row.proof` — the exact
Datalog derivation chain (`catalog_match → derived_from_act → most_specific_candidate →
not_zielleistung_component → not_excluded → no_unresolved_conflict`, per `goae_rules.dl:287-303`),
so "why is this billable" is answerable without re-running the solver.

**Receipt hash.** `receipt_hash()` (`apps/engine/app/services/receipt.py:50-76`) is a SHA-256 over a
`ReceiptInputs` Pydantic model whose ten fields are, in the module's own words, "everything the
receipt hash is computed over, serialised into the hash in this order":

```
catalog_version, catalog_sha256, rules_version, rules_hash,
logic_version, solver_version, rules_engine_version,
policy (dict), facts (canonicalized input), output (canonicalized output)
```

Call site (`audit.py:1557-1571`): `catalog.sha256()` (§1), `rule_coverage_service.rules_hash(...)`
(a hash over the rule CSVs), `settings.logic_version` (SHA-256 over the `.dl`+`.lp` files, §1),
`settings.clingo_version` (read from the installed library, not hand-pinned —
`config.py:525-531`), `settings.policy_fingerprint()` (every setting that can change an answer,
deliberately excluding timeouts/debug flags that only change *how* an answer is produced), and the
claimed positions / audited results themselves — with `rechnungs_id`/`abrechnungsfall_id` explicitly
excluded from the hashed output (`RECEIPT_EXCLUDED_POSITION_FIELDS`, `audit.py:153`) so which
invoice a position came from never moves the hash, only what was decided about it.

The module docstring is explicit about the guarantee's shape: **same hash implies same
catalog/rules/logic/solver/policy/input; the converse does not hold across engine versions** — the
hash covers the canonical *response*, so adding a field to the response (it cites `BlockedCode.proof`
being introduced as a real past example) changes the hash even when the billing decision is
identical. A receipt is comparable *within* one engine version, not across one — treated as a design
decision, not a gap to be silently patched.

---

## 8. Extraction pipeline (`scripts/import_goae.py` + `deterministic_rule_parser.py`)

Reconstructed pipeline order (no single orchestrating Makefile exists; order inferred from each
script's own docstring):

1. **`fetch_goae.py`** — downloads the official GOÄ XML into `data/raw/`, recording
   `sha256_raw`/URL/timestamp in `data/raw/manifest.json`.
2. **`import_goae.py`** — parses the XML into the catalog JSON plus `exclusions.csv` /
   `zielleistung.csv` / `factor_bands.csv` / `import_report.json`, everything initially
   `verified=false`.
3. **`deterministic_rule_parser.py`** — re-reads the same Anmerkungen prose *independently* of step
   2 and either confirms a row or quarantines it to `exclusions.residue.csv`.
4. **`auto_verify_rules.py`** — runs a model verification pass over the still-unverified rows,
   stamping `source=ai_verified:<model>:<original source>`.
5. **`refreeze_rule_coverage.py`** — updates golden-snapshot metadata; its own docstring instructs
   "run it after `auto_verify_rules.py` ... and commit the snapshot diff alongside the rule diff."

**The five sentence forms** (`deterministic_rule_parser.py:20-36`, edge always stored `n → d`, "n
blocks d"):

| Form | Pattern (German) | Regex |
|---|---|---|
| A `ist_neben` | "Die Leistung nach Nummer `<d>` ist neben den Leistungen nach den Nummern `<n...>` nicht berechnungsfähig." — forbidden Ziffer first | `\b(?:ist|sind)\s+(?:auch\s+)?neben\b` |
| B `neben_sind` | "Neben der Leistung nach Nummer `<n>` ist die Leistung nach Nummer `<d>` nicht berechnungsfähig." — object first | `\b(?:ist|sind)\s+(?:die|der|eine)\s+Leistung` |
| C `nicht_nebeneinander` (mutual) | "Die Leistungen nach den Nummern `<x...>` sind nicht nebeneinander berechnungsfähig." — every pair excludes | `nicht\s+nebeneinander\s+(?:berechnungsf\|berechnet\|berechenbar)` |
| D `darf_neben` | "Die Leistung nach Nummer `<d>` darf anstelle oder neben einer Leistung nach Nummer `<n...>` nicht berechnet werden." | `\bdarf\s+(?:anstelle\s+oder\s+)?neben\b` |
| E `neben_darf` | "Neben den Leistungen nach Nummer `<n...>` darf die Leistung nach Nummer `<d>` nicht berechnet werden." | `\bdarf\s+(?:die\|der\|eine)\s+Leistung` |

Adjacent, not one of the five forms but part of the same extraction: `ZIELLEISTUNG_RE` (§ 4 Abs. 2a
"Bestandteil der/des Leistung... Nummer"), `FACTOR_CAP_RE` ("nur mit dem einfachen Gebührensatz
berechnungsfähig"), and `QUANTITY_HINT_RE` — catches frequency phrasing (`nur einmal`, `je Sitzung`,
`je Behandlungsfall`, ...) that the engine deliberately does **not** attempt to model as a rule,
flagging it as a known gap instead.

**Quarantine** (`deterministic_rule_parser.py:331-385`, `adjudicate()`), first matching reason wins:
Ziffer not in catalog, self-edge, no parseable provision in the quote, direction reversed vs. the
quote, frequency/time restriction, a conditional marker phrase, a "bis"-range endpoint that isn't
itself a catalog Ziffer, a claimed-mutual rule with no reciprocal sentence, or a claimed one-way rule
whose sentence is actually mutual. Anything not caught by one of these is `CONFIRMED`. Quarantined
rows go to `exclusions.residue.csv` (§2), never silently into the enforced set.

**`unparsed_rows.json` provenance**: written to `data/catalogs/goae_current/unparsed_rows.json` by
`import_goae.py`'s `write_outputs()`. Every entry carries `table` (source table index), `row` (row
index), `cells` (raw cell text), and `reason` — e.g. "annotation text with no preceding Ziffer" or
"row too short to classify." Never bare free text with no traceable source position.

**Percentage-surcharge marker**: `PERCENTAGE_ZUSCHLAG_RE` matches phrasing like "beträgt 25 v.H. des
einfachen Gebührensatzes" (e.g. Nr. 441, 5298). When a Ziffer-headed row has no Punktzahl and the
*following* row matches this pattern, the unparsed entry gets `typ = "prozent_zuschlag"` plus the
Ziffer — read back downstream by `Catalog.is_percentage_surcharge`, which is what produces the
`surcharge_not_modelled` verdict in the audit path (§6, bucket rule 6) rather than a false
`unknown_ziffer`.

---

## 9. Test architecture

**Golden cases** (`apps/engine/tests/golden/`, map in `README.md`): five worked-by-hand answers plus
four regression reproducers for fixed defects.

- `case_a_known_answer` — 5 positions, €78.81, nothing wrong and nothing confirmed; the
  byte-identical baseline.
- `case_b_verified_exclusion` — `excl_auto_34_4` fires; GOÄ 4 blocked, GOÄ 34 untouched.
- `case_c_verified_factor_cap` — `cap_auto_440` fires at factor 2.3; the same Ziffer at exactly 1.0
  survives.
- `case_d_arithmetic_mismatch` — case A with `gesamtbetrag` inflated +€10.00.
- `case_e_echtdaten_gate` — case A without `@echtdaten` → HTTP 422 `ECHTDATEN_UNDECLARED`; after
  running the *real* `scripts/anonymize_padnext.py` as a subprocess (not mocked), re-audits
  identically to case A.
- `bug_positionsnr_collision` — regression: findings keyed by `id(row)`, not `positionsnr` (§5).
- `case_f_cross_patient_boundary` — `excl_auto_34_4` must not cross an `<abrechnungsfall>` boundary
  (§5).
- `case_g_cross_date_same_patient` — same exclusion, 5.5 months apart → advisory (`unconfirmed`),
  not `confirmed_wrong` (§6).
- `case_h_cross_invoice_duplicates` — 3 patients each billing GOÄ 1 once → zero duplicate warnings.
- `case_i_percentage_surcharges` — GOÄ 441 → `surcharge_not_modelled`, not `unknown_ziffer`.

`case_f`, `case_g`, and `bug_positionsnr_collision` have **hand-computed** `expected.json` — the
oracle's generic per-delivery walker cannot express `<abrechnungsfall>`/date grouping. `case_h` and
`case_i` **are** oracle-derived.

**Golden oracle isolation** (`apps/engine/tests/test_golden_cases.py:100-119`,
`test_the_oracle_imports_nothing_from_the_engine`): first a static grep of `oracle.py`'s own source
for `import app`/`from app` lines; then, to catch a *transitive* import a grep would miss, the test
actually executes `oracle.py` **in a fresh subprocess** and asserts exit code 0 and no `"STALE"` in
stdout. The premise, stated in the golden README: "an oracle that could reach the engine could only
ever agree with it" — `oracle.py` recomputes every amount independently as
`ROUND_HALF_UP(punkte × faktor × punktwert_cent ÷ 100, cent)` straight from
`data/catalogs/goae_current/goae.official.json` and `verified=true` CSV rows, never by calling
`app`.

**Mutation testing**: **not present**. No `mutmut`/`cosmic-ray` config or dependency exists anywhere
in the repo. The only hits for "mutation" concern an unrelated guarantee — append-only audit-log
rows, enforced by SQLAlchemy `before_update`/`before_delete` listeners in
`apps/engine/app/db/models.py:562-576` that raise `AuditLogIsAppendOnly`, tested in
`apps/engine/tests/test_audit_log.py`. **"Mutation-checked guards" as commonly understood (tests
that would fail under an automated code mutation) do not exist in this codebase as a distinct,
tooled practice** — the golden cases and the oracle-independence check are the closest analogue,
but they are hand-written regressions, not mutation-generated.

**Top-level runner** (`scripts/test-all.sh`): five test surfaces mirroring CI's five jobs, runnable
locally with one exit code. Phase 2 (engine) runs the full `pytest tests/` suite, then **re-runs**
`pytest tests/test_golden_cases.py -v` on its own — deliberately redundant (the comment: "it costs
about four seconds") so a golden-case failure is named on its own line rather than buried in the
full suite's output. If the full suite fails first, the golden re-run is recorded as a skip, not
silently omitted.

**`conftest.py` isolation** (`apps/engine/tests/conftest.py`): forces `DATABASE_URL` to
`sqlite+aiosqlite:///:memory:`, `UPLOAD_DIR` to a fresh tempdir, `APP_ENV=development` (bypasses
production-only guards), and `PADNEXT_SCHEMA_POLICY=strict` regardless of a developer's local
`.env`. Replaces the JWKS HTTP fetch with a fixed in-memory key (no network). If the Soufflé binary
is missing, engine-dependent tests **skip** locally but **fail** (not skip) when
`REQUIRE_ENGINES=1` — guaranteed set in CI — so a run that silently skipped everything can never
look like a pass.

---

## 10. The 20 things that are hard or dangerous to change

1. **`<abrechnungsfall>`-scoped grouping in `audit_delivery`/`_audit_group`** (`audit.py:797-815,
   1455-1473`). Widening the fact base back to `<rechnung>` or the whole delivery reintroduces the
   exact cross-patient bug `case_f`/`case_g` pin down. Any refactor here needs both golden cases to
   stay green, not just pass a diff review.
2. **The order of tests inside `classify_position`** (`audit.py:680-794`). It is a priority ladder,
   not an independent set of checks — reordering rules 1–4 changes which bucket a genuinely wrong
   position lands in. The docstring says this outright: "the order of the tests is the argument."
3. **`blocked_exclusion` vs. `blocked_exclusion_cross_date` as separate Datalog relations**
   (`goae_rules.dl:171-194`). Merging them back into one relation silently turns every
   date-uncertain exclusion into a confirmed defect — the opposite of the fix commit `7f917db`
   made.
4. **The stratification order in `goae_rules.dl`** (specificity → zielleistung → exclusion →
   conflict). The file states plainly that a single self-referential `blocked` relation is not
   stratifiable. Adding a new suppression layer requires proving it only negates the layer above it.
5. **The mutual-cluster / `conflict` split (Datalog) vs. arbitration (ASP)**. Resolving mutual
   exclusions inside Datalog via negation-as-failure is exactly the bug the two-solver split exists
   to avoid (comment, `goae_rules.dl:18-23`) — a whole cluster would vanish.
6. **Objective priority order in `goae_optimize.lp`** (`@5..@1`, revenue last). Reordering so revenue
   outranks evidence/specificity turns the optimizer into an upcoding engine — the file's comment
   calls this out explicitly as the failure mode being guarded against.
7. **`0 { analog(A,Z) : ... } 1` cardinality (not `1 { ... } 1`)** in `goae_optimize.lp:79`. Forcing
   exactly one analog choice means an over-constrained ladder produces UNSAT for the whole
   encounter instead of one reported gap.
8. **`charged/1` (not `bill/1`) as the relation the hard constraints range over**
   (`goae_optimize.lp:89-96`). A prior version used `bill/1`, which let an Analogansatz choice evade
   the legality constraints — the validator then contradicted the solver and produced a 500.
9. **`RECEIPT_EXCLUDED_POSITION_FIELDS`** (`audit.py:153`). Removing this exclusion makes the
   receipt hash move with invoice attribution rather than with the billing decision, breaking the
   "same hash ⇒ same decision" guarantee for reasons unrelated to the decision.
10. **The ten-field `ReceiptInputs` composition** (`receipt.py:35-47`). Adding a field to the hashed
    `output` is a legitimate but *breaking* change to comparability across engine versions — the
    module docstring records this happened once already (`BlockedCode.proof`) and moved two of
    three golden receipts with zero change to the actual totals. Any such change needs the same
    explicit acknowledgement, not a silent bump.
11. **`Settings.logic_version` hashing `datalog_path` and `asp_path` together** (`config.py:534-544`).
    Do not swap this for a hand-maintained version string — it exists precisely so an edited `.dl`/
    `.lp` file cannot silently keep an old cache/receipt identity.
12. **`UnverifiedRulePolicy` default (`WARN`)** (`config.py:124-127`, `rule_store.py:246-263`).
    Switching the default to `BLOCK` starts enforcing rules nobody has verified; switching to
    `IGNORE` silently drops coverage. Either is a policy decision, not a refactor.
13. **`Rule.hand_verified` tie-break in `_dedupe_exclusions`** (`rule_store.py:101-112,289-318`).
    Changing which source wins a collision (manual vs. machine-derived) changes which legal citation
    reaches the invoice without changing any test unless a fixture happens to hit that exact
    collision.
14. **The quarantine gate order in `deterministic_rule_parser.py::adjudicate`** (lines 331-385).
    First-match-wins; reordering changes which reason gets recorded for a quarantined row, breaking
    the audit trail's meaning even if the confirm/quarantine split itself doesn't change.
15. **`PERCENTAGE_ZUSCHLAG_RE` / `Catalog.is_percentage_surcharge` plumbing** — this is what keeps a
    percentage surcharge (Nr. 441/5298) out of `unknown_ziffer` territory. Losing this marker
    reclassifies a correctly-billed surcharge as a data gap, per `case_i`.
16. **`build_fact_rows`'s exact match against `INPUT_RELATIONS`** (`souffle_facts.py:179`). This is
    the only thing that turns a Python/Datalog schema drift into a loud startup failure instead of
    Soufflé silently running against an empty or missing relation.
17. **Golden oracle independence** (`test_golden_cases.py:100-119`). Any change that lets
    `oracle.py` import — even transitively — from `app` defeats the entire golden-test premise
    without necessarily failing any single assertion.
18. **`AuditLogIsAppendOnly` DB-level listeners** (`db/models.py:562-576`). This is enforced below
    the ORM layer on purpose (`REVOKE UPDATE, DELETE` for the app role is the other half, per
    `test_audit_log.py`'s docstring) — an ORM-only guard is bypassable by raw SQL.
19. **`souffle_engine.py` retrying only `OSError`, never a non-zero exit or timeout**
    (`souffle_engine.py:121-139`). Broadening the retry to cover a bad Datalog exit code risks
    silently re-running a program that is deterministically wrong, which would look like
    flakiness rather than a bug.
20. **`Catalog.routed_version` kept distinct from `catalog_version`** (`catalog_loader.py:227-232`).
    Collapsing these into one field removes the only signal that a catalog file was placed in the
    wrong edition directory.

---

## Current strengths

- Every hard suppression rule (specificity, Zielleistung, one-way exclusion) is decided in a
  stratified, monotone Datalog program with an exported `proof` row for every conclusion —
  legally traceable by construction, not by convention.
- The two-solver split (Soufflé for certainty, Clingo for arbitration) is not incidental — it is the
  direct answer to a named failure mode (negation-as-failure silently destroying mutual-exclusion
  clusters), and the ASP objective explicitly ranks evidence/specificity above revenue to structurally
  resist upcoding.
- The PADnext audit path reuses the *same* Datalog program as the coding path rather than a parallel
  reimplementation, so "what's chargeable" has one definition, checked twice (forwards and
  backwards).
- Provenance is compositional and cryptographic end-to-end: catalog SHA-256 → rules hash → logic
  hash → solver version → policy fingerprint → receipt hash, each independently inspectable.
- The extraction pipeline has two independent parsers (`import_goae.py` and
  `deterministic_rule_parser.py`) that must agree before a rule is confirmed, plus an AI verification
  pass and a human review queue — three tiers before a rule is enforced by default.
- The golden-test discipline (oracle computed independently of the engine, enforced in a subprocess,
  regenerated-and-diffed rather than hand-edited) is unusually rigorous for this kind of system.
- Two documented production bugs (cross-patient exclusion firing, positionsnr collision) were fixed
  by narrowing the grouping key rather than patching symptoms, and both are now permanent regression
  fixtures.

## Current bottlenecks

- **No mutation testing** exists despite the codebase's own vocabulary suggesting "mutation-checked
  guards" — the golden suite is comprehensive but hand-curated, not systematically adversarial.
- **`zielleistung.csv` is empty** (header only) — all four Zielleistung rules currently in force come
  from the manual file; the automated extraction path for this rule type is unproven at scale.
- **`analog_candidates.csv` rows are all `verified=false`/`illustrative`** — the § 6 Abs. 2 analog
  ladder currently runs on unverified data by default (subject to `UnverifiedRulePolicy`).
- **6 of 837 exclusion rows remain permanently quarantined** (`conditional`) — these represent GOÄ
  provisions the deterministic parser structurally cannot resolve (they require clinical context not
  present in an invoice), which is a ceiling on automatic coverage, not a bug to fix.
- **Receipt hashes are not stable across engine versions** by design — any consumer trying to use a
  receipt hash for long-term audit continuity across upgrades needs a narrower, explicitly-scoped
  hash that does not yet exist (the `receipt.py` docstring names this as a possible future change,
  not yet built).
- **The PADnext path's reliance on `service_date`** for cross-date exclusion softening (§6) means an
  invoice source that never populates `datum` gets the conservative (same-date) reading everywhere —
  correct, but a source of `unconfirmed` volume that a better upstream date signal could resolve.

## Do-not-touch list

See §10 above (20 items) — the same list, reasons included, is the do-not-touch list.

## Not determined from current codebase

- Whether any orchestration script (Makefile, CI job) runs the five extraction-pipeline steps in
  §8 automatically end-to-end, or whether each is triggered manually by a maintainer. No such
  orchestrator was found; the order was reconstructed entirely from cross-referenced docstrings.
- The intended cadence/trigger for re-running `fetch_goae.py` against a new official GOÄ release
  (e.g. on a legal amendment).
- Whether `data/rules/ai_verification_log.jsonl` and `data/rules/import_report.json`/
  `deterministic_parse_report.json` are consumed by any automated CI gate, or are purely
  human-read artifacts.
- The precise mechanism (if any) reconciling `goae_2026_current` / `goae_neu_draft` with a future
  cutover date — both exist on disk but neither was confirmed as reachable from a live
  configuration path in this review.

---

## Ten-line summary for a new engineer

A catalog (SHA-256-pinned JSON per GOÄ edition) and a rule store (CSVs, each row `verified` or not,
each with a `legal_basis` citation) feed two solvers chained through one Python object. Soufflé
(stratified Datalog, `logic/datalog/goae_rules.dl`) decides everything *certain*: what's chargeable,
what's hard-blocked by an exclusion or Zielleistung rule, and exports a `proof` row for every
conclusion — it never resolves a mutually-exclusive cluster, because negation-as-failure would
silently make the whole cluster vanish. Clingo (`logic/asp/goae_optimize.lp`) picks among what
Soufflé left open — which side of a conflict wins, which factor, which analog code — under an
objective that ranks clinical evidence and specificity above revenue, on purpose. The PADnext audit
path runs Soufflé only, never Clingo, because an already-coded invoice has no arbitration left to
do — it just gets checked. Everything is grouped per `<abrechnungsfall>` (one patient encounter),
never wider, because the opposite once caused one patient's charge to be blocked by another
patient's Ziffer. `classify_position` turns the solver's verdict into `confirmed_fine` /
`confirmed_wrong` / `unconfirmed` through an ordered ladder where absence of proof is never treated
as proof of correctness. A ten-field receipt hash (catalog + rules + logic + solver + policy +
input + output) makes "deterministic" falsifiable rather than asserted. Read `classify_position`,
`goae_rules.dl`, and `goae_optimize.lp` first — everything else is plumbing around those three.
