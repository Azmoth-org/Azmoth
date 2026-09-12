# GOÄ coverage sprint — batch 2 validation report

Internal engineering reference. Stand: 2026-09-12. Independent validation of
`docs/content/coverage-sprint-report-batch2.md` — every figure below was recomputed or re-run
against the checkout, not read out of that report.

**Final status: VALIDATED WITH QUALIFICATIONS.**

The corpus is schema-clean, citation-exact, deterministic and correctly quarantined; the parity
relaxation is sound and narrowly scoped; every published metric reproduces to the digit. Two
findings qualify it: one shipped row (`age_man_26`) encodes an over-restrictive lower age bound
that its own citation does not support (**F1**), and all 37 rows are inert on the PADnext
ingestion path because no production call site supplies the facts the three layers need (**F2**).
Neither is caused by the parity work, and neither is visible in any public claim — the batch is
deliberately excluded from every published number, which is what keeps F2 from being a
misstatement rather than a limitation.

---

## 1. Repository state

| | |
|---|---|
| Repository | `/home/oussama/Desktop/MVP/TARGET_MONOREPO` |
| Branch | `feat/goae-coverage-sprint-batch1` |
| HEAD at start | `cc8ff7b` — *fix(rules): refreeze_rule_coverage.py — files_loaded is metadata* |
| Merge base vs `main` | `673d5b0` |
| Working tree at start | **clean** — no pre-existing modifications, nothing stashed or discarded |
| Batch 2 commits | `3e1bbad` (data + tests), `cc8ff7b` (refreeze tool + snapshot re-freeze) |
| Preceding, in scope for context | `a5ad632` (ADR-002 mechanism), `7323630` (batch 1) |

Environment, verified before any test was run:

| Tool | Found | Note |
|---|---|---|
| Python | 3.11.15 (`apps/engine/.venv`) | `pip check` → no broken requirements |
| Soufflé | 2.5, `/home/oussama/.local/bin/souffle` | on `$PATH`, as `souffle_engine.py` expects |
| Clingo | 5.8.0, **Python module** | no CLI binary; `app/solvers/clingo_solver.py` imports it, so this is correct — `engine_cli.py check` reports `[PASS] clingo available — 5.8.0` |
| Node / pnpm | 22.19.0 / 10.33.4 | workspace `node_modules` already installed |

No installation or build step was needed; nothing was missing.

---

## 2. The artifacts, as they actually are

Four files under `data/rules/`, all loaded by `RuleStore._parse` via the `*_FILES` tuples in
`apps/engine/app/rules/rule_store.py:58-61`.

| File | Header | Data rows | Loaded | Suppressed |
|---|---|---|---|---|
| `quantity_limits.manual.csv` | `rule_id,ziffer,max_count,window,legal_basis,quote,verified,verified_at,source` | **13** | 13 | 0 |
| `gender_restrictions.manual.csv` | `rule_id,ziffer,allowed_gender,…` | **15** | 15 | 0 |
| `age_restrictions.manual.csv` | `rule_id,ziffer,min_age,max_age,…` | **9** | 9 | 0 |
| `time_relations.manual.csv` | `rule_id,ziffer_a,ziffer_b,relation,min_hours,…` | **0** (header only) | 0 | 0 |
| **Total** | | **37** | 37 | 0 |

37 is the reported number and the real one. The 37 rows name **37 distinct Ziffern**: the three
non-empty families are pairwise disjoint (`quantity ∩ gender = ∅`, `quantity ∩ age = ∅`,
`gender ∩ age = ∅`), verified in
[test_batch2_semantic_boundaries.py](apps/engine/tests/test_batch2_semantic_boundaries.py).

Every row is `verified: true`, `verified_at: 2026-09-12`,
`source: manual_verification:coverage_sprint_batch2`. No duplicate rule ids, no duplicate
subjects, no malformed rows, no missing required values.

### 2.1 Citation fidelity — all 37 verbatim

Each row's `quote` was matched against the `official_text` and `annotations` of its own Ziffer in
`data/catalogs/goae_current/goae.official.json`, normalising only NFC and whitespace. **37 of 37
matched verbatim**, including the two-part quote on `age_man_26` (both parts independently).

One thing this surfaced is worth recording. GOÄ 382's catalog text contains an upstream OCR
defect — `"Epikutantest, je **Text** (51. bis 100. Test je Behandlungsfall)"`. The CSV quotes it
faithfully, defect included, which is the correct behaviour for a verbatim citation. The batch 2
report's §2.1 table silently prints it as *"je Test"*. Nothing in the engine depends on this, and
the encoded `max_count` is unaffected, but a report that presents a tidied string under the label
"official text" is no longer quoting the catalog. See §9, claim C5.

### 2.2 Band arithmetic

The six banded allergy-test rows encode the width of each Ziffer's own stated range, and each is
correct: 380 `1..30`→30, 381 `31..50`→20, 382 `51..100`→50, 385 `1..20`→20, 386 `21..40`→20,
387 `41..80`→40, 388 "bis zu 10"→10, 390 `1..20`→20.

### 2.3 `vollendet` age arithmetic

"bis zum vollendeten N. Lebensjahr" is satisfied while the patient has *not yet* completed year N
— i.e. `age ≤ N-1`, since `Patient.age` is whole years. All nine shipped rows satisfy this, checked
mechanically by the validator's `vollendet_max_age`: 26→13, 250a→7, 273→3, 412→1, 413→1, 1063→9,
5041→13, K1→3, K2→3. The `min_age` on `age_man_26` is the exception, and is finding **F1**.

---

## 3. The validator

**`apps/engine/scripts/validate_batch2_csvs.py`** — 1,545 checks over the four files, exit 0 on
the shipped corpus with **0 errors, 5 warnings**.

It exists because `RuleStore._parse` is deliberately permissive — `int(row.get("max_count") or
"1")`, `(row.get("window") or "behandlungsfall")` — which is right for a loader that must not
fail the whole engine on one bad row, and wrong for a release gate. The strictness lives here.

File-level: existence, UTF-8, BOM, CSV parse, exact header (schema drift), blank rows, line
endings. Row-level: required fields, rule-id format/charset/uniqueness, Ziffer syntax and catalog
resolution, placeholder detection, `verified` vocabulary, ISO `verified_at`, control characters,
duplicate subjects, per-family numeric and vocabulary checks, the `vollendet` cross-check, and
`citation_verbatim`.

Two checks carry most of the weight:

**`citation_verbatim`** is what separates "cited" from "asserted". Every part of a multi-part
quote is checked independently, so one real sentence cannot carry an invented one.

**`window_supported`** is a code-derived gate, not a style rule. `build_fact_rows`
(`app/solvers/souffle_facts.py:200`) emits `quantity_limit` as `(rule_id, ziffer, max_count)` —
**`window` is not in the fact at all** — and LAYER 3.5 compares against `history_count`, which
`patient_history.quarter_counts` computes over a calendar quarter and nothing else. A row saying
`window: sitzung` would therefore not be skipped and not fail: it would be silently enforced at
the wrong width. Batch 2 keeps such rows out by hand (report §4); this check makes that a gate.

The five warnings on the shipped corpus:

| Warning | Files | Assessment |
|---|---|---|
| `line_endings_are_lf` | all four | **Benign, verified.** The files are CRLF. `RuleStore._rows` opens with `newline=''` and hands the handle to `csv`, which strips the terminator — confirmed by loading all 37 rows and finding zero values carrying a CR or edge whitespace. `exclusions.csv` and `factor_bands.csv` are CRLF too, so this is the existing convention. Reported so a reviewer knows it is deliberate. |
| `min_age_is_eligibility_not_frequency` | `age_man_26` | **Real.** This is finding **F1**. |

Tests: **`apps/engine/tests/test_validate_batch2_csvs.py`**, 65 tests, all passing. Every check
that can fail is driven against a deliberately broken copy in `tmp_path`; `data/rules/` is never
written to.

---

## 4. Semantic boundaries

**`apps/engine/tests/test_batch2_semantic_boundaries.py`** — 188 tests, all passing, every one
against the shipped corpus through the `souffle` fixture (not a hand-built store). Both halves
are asserted: the verdict *and* the audit trail (`reason`, `rule_id`, `legal_basis`, `detail`).

**Mengenbegrenzung** (LAYER 3.5, `Count >= Max`), swept per Ziffer across all 13 rows:
`Max-1` admitted · `Max` blocked · `Max+5` blocked · no history admitted · empty history admitted
· explicit `0` admitted · history for another Ziffer irrelevant · history for an unclaimed Ziffer
filtered out of the fact base · a Ziffer with no rule never capped · **same-invoice repetition is
not a quantity block** (the layer reads prior invoices, not this one's multiplicity — a different
question it correctly declines to answer).

**Geschlecht** (LAYER 3.7, `G != Allowed`), across all 15 rows: matching admitted · opposite
blocked with full trail · unknown (`sex=None`) **admitted** · `d` **blocked by every row** · a
Ziffer with no rule never blocked · no leakage between Ziffern.

**Alter** (LAYER 3.8, `Age < MinAge ∨ Age > MaxAge`), across all 9 rows: exactly at the upper
bound admitted · one year above blocked · age 0 admitted wherever `min_age` is unset · unknown
admitted · the `NO_MIN_AGE=0` / `NO_MAX_AGE=999` sentinels proven unreachable for a valid
`Patient.age`.

Two points of interpretation, stated rather than assumed:

* **Day-granularity boundary tests are not applicable by design.** The task asked for "one day
  below / one day above" cases. `Patient.age` is whole years and the engine never sees a date of
  birth — ADR-002 §5.2 makes this an explicit data-minimisation stance, and
  `test_no_parsed_model_can_hold_patient_identity` forbids the field that would be needed. The
  boundary sweep is therefore per **year**, which is the real granularity. An out-of-contract age
  (`-1`, `131`) is rejected by Pydantic before the engine, asserted directly.
* **"Conservative" means permissive here.** An absent `patient_age` / `patient_gender` is read as
  *unknown*, and unknown never counts as a mismatch — so a restricted Ziffer is **admitted** when
  the attribute is missing. That is conservative about asserting a violation and permissive about
  billing. It is the documented intent ("silence is not evidence"), and it is now pinned so that
  changing it has to be a decision somebody makes.

**Zeitbeziehung** has no shipped rows. Verified that the file is loaded, that `rules.time_relations`
is empty, that two same-day Ziffern from the same clinical family produce no block, and that no
advisory is emitted. I re-ran the catalog scan independently rather than trusting §2.2: of 40
sentences matching a temporal pattern, 7 also name another Ziffer, and none is an encodable
same-day exclusion. The only real same-day condition is GOÄ 726 — *"neben der Leistung nach
Nummer 725 an demselben Tage nur berechnungsfähig, wenn … mindestens 45 Minuten"* — which is a
conditional **permission** stated in minutes, correctly quarantined. GOÄ 247's "nicht an demselben
Tag angelegten Gipsverband" names no counterpart Ziffer, also as reported. **§2.2 is confirmed.**

---

## 5. Quarantine

**`apps/engine/tests/test_batch2_quarantine.py`** — 156 tests, all passing. All 103 quarantined
Ziffern from report §3 are transcribed as data, grouped by the stated reason, and the per-family
totals are asserted against the report's own counts (68 / 5 / 3 / 27 — all match, no duplicates,
every Ziffer resolves in the catalog).

Checked two ways. **Not encoded**: no quarantined Ziffer carries a rule in the family it was held
out of — deliberately family-scoped, because three Ziffern are quarantined in one family and
shipped in another, and conflating them would be wrong in both directions:

| Ziffer | Quarantined for | Shipped for |
|---|---|---|
| 26 | Mengenbegrenzung ("je Kalenderjahr") | Alter |
| 807 | Alter (qualitative "Kind") | Mengenbegrenzung |
| 887 | both | neither |

**Not executed**: a sample across every stated reason is claimed through the real engine and must
produce no block from the layer it was held out of — including `history_counts={z: 999}` against
each quarantined quantity Ziffer (no cap is invented), every sex against GOÄ 6/7/4851 (the "z.B.
aus dem Genitale der Frau" example does not become a gate), and ages 0/7/42/90 against the
qualitative-age Ziffern (no band is invented from "Neugeborenes" or "Säugling").

One summarising assertion covers the conservative-behaviour claim: with age, sex and history all
absent — the exact state of every PADnext audit — none of the three layers contributes a block to
any Ziffer they name.

Finally, no quarantined or advisory functionality is counted publicly: `enforced_rule_count()`
provably sums only exclusions + Zielleistung + specificity + factor caps, and no Batch 2 rule
appears in `constraint_rules()`.

---

## 6. Parity hardening

**`apps/engine/tests/test_batch2_parity_hardening.py`** — 18 tests, all passing, importing the
real helpers from `test_golden_snapshot.py` rather than re-implementing them.

The carve-out is **correct and correctly scoped**. It is subset semantics on one path
(`/audit_trail/rule_summary/files_loaded`): `frozen_files - live_files` must be empty.

| Case | Behaviour | Correct? |
|---|---|---|
| Identical, same order | passes | ✅ |
| Identical, different order | passes | ✅ order-independent |
| New file inserted at front / middle / end | passes | ✅ the index-shift bug, fixed |
| All four Batch 2 files at once | passes | ✅ |
| Empty frozen list | passes | ✅ |
| A file that no longer loads | **caught** | ✅ the regression that matters |
| Live list emptied | **caught** | ✅ |
| File renamed | **caught as a drop** | ✅ |
| Duplicate entry | not caught | ⚠️ set semantics; covered instead by asserting no duplicates on the real store |
| Sibling `enforced_rule_count` changed | **caught** | ✅ **not weakened** |
| A billing amount elsewhere changed | **caught** | ✅ **not weakened** |
| A hypothetical `files_loaded_count` sibling | **caught** | ✅ prefix test does not over-match |

The parity checks are **not weakened**: the carve-out removes exactly the `files_loaded[i]` leaves
and nothing else, asserted directly.

`refreeze_rule_coverage.py` received the same treatment in `cc8ff7b`, and it is the same shape —
`flatten()` keeps `files_loaded` as one leaf, `is_allowed()` permits it only when
`set(old) <= set(new)`, so a dropped file still lands in "REFUSING TO WRITE".

### One correction to the report

Report §1 says the four files were materialised *"without touching any of the nine frozen
`logic/tests/golden/*.golden.normalized.json` files"*. That is true of the data commit `3e1bbad`
(0 golden files changed), but **not of the branch**: `cc8ff7b` re-froze all nine.

What matters is that the re-freeze was **purely additive**. Across all nine files the complete
diff is 36 added lines — the four new filenames in each `files_loaded` array — and **zero removed
lines, zero changed values**. No behavioural value moved. That is the claim worth defending, so
it is the one the test asserts, scoped to the Batch 2 commit range (derived from the commit that
introduced `quantity_limits.manual.csv`, not hardcoded, and deliberately not the merge base —
that range also spans batch 1, which legitimately moved rule counts everywhere).

---

## 7. Reproducibility

**`apps/engine/tests/test_batch2_reproducibility.py`** — 14 tests, all passing.

| Artifact | Check | Result |
|---|---|---|
| `engine_cli.py check` | run twice, byte-compare | **identical**; exit 0 both times |
| Engine verdict, all three layers firing | 5 identical runs, full normalised result | **1 distinct result** |
| Each layer alone | 5 runs each | **1 distinct result** each |
| Position ordering | forward vs reverse bridge | same verdicts |
| `rules_hash()` | 5 computations | **stable** — `4fbec3c5b99b850f…` |
| `rules_hash()` coverage | perturb each of the 4 new CSVs | hash moves for **all four** ✅ |
| `RuleStore.load` | loaded twice | identical rule ids and `files_loaded` |
| Timestamp / uuid leakage | regex over `rule_id`/`detail`/`legal_basis`/`explanation` | **none**; re-run byte-identical |

`logic_version` is `83fae8e7f0369c25`, unchanged — and Batch 2's own commit provably edited **0**
files under `logic/datalog/` or `logic/asp/` (the `.dl` change belongs to `a5ad632`, the ADR
commit). Report §7's claim is accurate for the batch.

The receipt re-pin is confirmed: `CASE_A_RECEIPT_PREFIX` and `receipt_hash_prefix` moved
`8e8f5e96b745eac8` → `9f2a7e385de0fc51` in `3e1bbad`, and the **only** line changed in
`expected.json` is that hash — no Ziffer, factor or amount moved.
`test_case_a_receipt_is_stable_across_runs` passes.

---

## 8. Mutation validation

**`apps/engine/scripts/mutate_batch2.py`** — 29 mutations, **25 detected, 4 survivors, 0
unexpected outcomes**, exit 0.

Isolation is by file copy into a fresh `tempfile.mkdtemp()` per mutation, removed afterwards. No
git operations of any kind. The harness SHA-256s the four real files before the run and re-checks
them after: **`working tree unchanged: True`**.

Detected (25), by class — boundary shifts `M01 M02 M03 M04 M06 M07`; unsupported windows
`M08 M09 M10`; gender vocabulary `M12 M13`; provenance `M14 M15 M16 M17 M18 M19`; structural
`M22 M23 M24 M25 M26 M27`; time-relation `M28 M29`.

Two are worth naming. **M16** silently corrects the catalog's `je Text` typo on GOÄ 382 to
`je Test` — caught by `citation_verbatim`, which is the check doing exactly its job. **M17** swaps
GOÄ 273's citation for GOÄ 412's: a real GOÄ sentence, attached to the wrong Ziffer, also caught.

### Survivors — reported, not fixed

| ID | Mutation | Why it survives | Covered elsewhere |
|---|---|---|---|
| **M05** | GOÄ 4601 `max_count` 3 → 4 | `max_count` is a free integer; nothing in the German is machine-comparable to it | `test_batch2_semantic_boundaries.py` asserts the cap per Ziffer (`QUANTITY_ROWS`) |
| **M11** | GOÄ 27 `allowed_gender` w → m | `m` is in-vocabulary and the citation stays verbatim; the contradiction is between prose and a one-letter code | `GENDER_ROWS` parametrisation |
| **M20** | GOÄ 388 `verified` true → false | a legal value — unverified is a supported state handled by `UnverifiedRulePolicy` | engine-level enforced counts |
| **M21** | delete the GOÄ 4601 row | a validator cannot know which rows *should* exist | `test_coverage_sprint_batch2.py` + pinned row counts |

All four are structural limits of a *schema* validator, each covered by a test at a different
level. None was repaired to make a number look better.

One change did come out of this run. M01/M02/M04 (age boundary shifts) initially survived because
`vollendet_max_age` was a WARN. That was wrong: "bis zum vollendeten N. Lebensjahr" is an
eligibility ceiling in every Leistungslegende that uses it and `N-1` is arithmetic, not judgement.
It is now an **ERROR**; the shipped corpus still passes, and the three mutations are now detected.
The lower-bound checks stay WARN, because `ab dem vollendeten N.` demonstrably *can* scope
something other than eligibility — which is finding F1.

---

## 9. Recomputed metrics

**`apps/engine/scripts/recompute_batch2_metrics.py`** — every figure read live, each printing its
formula. Catalog: 2,343 Ziffern, `goae_official_snapshot_2026-07-25`.

| Metric | Report (historical) | Recomputed | Δ |
|---|---|---|---|
| `enforced_rule_count` | 944 | **944** | — |
| `total_constraint_rule_count` | 980 | **980** | — |
| Ziffern under ≥1 enforced rule | 383 / 2343 (16.35%) | **383 / 2343 (16.35%)** | — |
| Batch 2 rows | 37 | **37** | — |
| — quantity / gender / age / time | 13 / 15 / 9 / 0 | **13 / 15 / 9 / 0** | — |
| Distinct Ziffern named | 37 | **37** | — |
| Already under an older rule | 14 | **14** | — |
| Newly represented | 23 | **23** | — |
| *If counted* — enforced | 981 | **981** | — |
| *If counted* — constraint total | 1,017 | **1,017** | — |
| *If counted* — Ziffern under a rule | 406 / 2343 (17.33%) | **406 / 2343 (17.33%)** | — |

**Every published figure reproduces exactly.** The 14 already-covered Ziffern are the same set the
report names, in the same membership: `4, 26, 27, 273, 807, 860, 1700, 1701, 1710, 1728, 1729,
1730, 1731, 5041`. Percentages are computed from the union and never added.

The distinctions the script keeps apart, because the headline depends on which is meant:

| Category | Count | Meaning |
|---|---|---|
| **Represented** | 37 rows / 37 Ziffern | named by a loaded rule |
| **Validated** | 37 | schema-clean, citation-verbatim, boundary-tested |
| **Enforceable given the facts** | 37 | reachable through the general clinical-extraction API, where a caller can populate `Patient.age` / `Patient.sex` / `history_counts` |
| **Executable today on PADnext** | **0** | see finding **F2** |
| **Quarantined** | 103 | held out with a stated reason, verified not executed |
| **Counted publicly** | **0** | deliberately outside `enforced_rule_count` |

---

## 10. Findings

### F1 — `age_man_26` encodes a frequency condition as an eligibility gate · **severity: high (billing correctness)** · blocks release: **no, but should be fixed before this row is relied on**

**Symptom.** The shipped rule carries `min_age: 2`, so the engine refuses GOÄ 26 for any patient
aged 0 or 1.

**Reproduce.**

```
result = souffle.run(_extraction(age=1), make_bridge(("a1", "26", 100, "1.0")))
# → billable=[]  blocked=[('26', 'age_restricted', 'age_man_26')]  detail='patient_age:1/band:2-13'
```

Also flagged independently, from the data alone, by
`validate_batch2_csvs.py` → `min_age_is_eligibility_not_frequency`.

**Cause.** `min_age` was read out of the Anmerkung *"Die Leistung nach Nummer 26 ist **ab dem
vollendeten 2. Lebensjahr** je Kalenderjahr höchstens einmal berechnungsfähig."* That sentence
limits how **often** the service may be billed from age 2 onward. It does not exclude younger
children — and the Leistungslegende itself bounds only the upper side (*"bei einem Kind bis zum
vollendeten 14. Lebensjahr"*). Under-twos are the population for whom this service is billed most
frequently, and the cited text is silent about excluding them, not supportive of it.

The report's own §3 quarantines GOÄ 26's Mengenbegrenzung clause as an unsupported
(`je Kalenderjahr`) window while §2.4 keeps "its Alter clause" — but the age phrase is not a
separate clause; it is the scope qualifier *of* the quarantined frequency sentence. Splitting it
out inverted its meaning.

The existing batch 2 test asserts `age=42` blocked and `age=8` admitted, so it never exercises the
lower bound. The defect was untested, not tested-and-accepted.

**Next action.** Drop `min_age` from `age_man_26` (leaving `max_age: 13`, which the
Leistungslegende does support) and adjust the `age_man_26` case in
`test_batch2_semantic_boundaries.py::test_goae_26_blocks_a_one_year_old`, which pins the current
behaviour deliberately so the change cannot happen silently. **Not done here**: this is a change
to shipped billing semantics, which is out of scope for a validation task and is a rules decision,
not a test-fixing one.

### F2 — every Batch 2 rule is inert on the PADnext ingestion path · **severity: medium (scope/claim accuracy)** · blocks release: **no**

**Symptom.** None of the 37 rules can fire on the shipped PADnext path. All three layers need a
fact that no production call site supplies.

**Evidence, traced in code.**

* **Mengenbegrenzung** — `app/services/pipeline.py:197` is the only production solver entry:
  `self.souffle.run(extraction, bridge, proposed_factors=proposed_factors)`. No `history_counts`.
  `app/services/patient_history.py` (`quarter_counts`, `record_occurrences`) is imported by
  **no** production module — the only references outside tests are comments in
  `souffle_facts.py`, `rule_store.py` and `db/models.py`. The `patient_ziffer_history` table
  exists via migration `0013`, and nothing writes to or reads from it in the request path.
* **Geschlecht / Alter** — `app/padnext/audit.py:468` builds `Patient(setting=setting)`, leaving
  `age` and `sex` as `None`. An absent fact is read as unknown, and unknown never blocks.

**Assessment — a limitation, not a misstatement.** ADR-002 §5.2 and §5.3 state the age and gender
gaps explicitly and call wiring `<geschlecht>` the first recommended follow-up. The quantity gap
is the less clearly stated of the three: the batch 2 report §6 demonstrates `record_occurrences`
→ `quarter_counts` → `souffle.run` end to end *in a test*, which proves the mechanism works but
is easy to read as proving it is wired. It is not.

Critically, **no public claim is affected**: Batch 2 is deliberately excluded from
`enforced_rule_count`, `total_constraint_rule_count` and the catalog-coverage share, so nothing
the marketing site or `facts.md` prints counts a rule that cannot fire. That is exactly the
property that keeps F2 a scoping limitation.

**Next action.** Record it explicitly in the batch 2 report's §5, next to the coverage table, so
"37 rules shipped" is never read as "37 rules in force on the production path".

### F3 — `window` is enforced by data discipline, not by code · **severity: low (latent)** · blocks release: **no**

`build_fact_rows` drops `window` from the `quantity_limit` fact, so a future row with
`window: sitzung` would be enforced at quarter width rather than rejected. No shipped row is
affected (all 13 are `behandlungsfall`). Now gated by `window_supported`, which is an ERROR — but
only if the validator is actually run. **Next action:** add
`validate_batch2_csvs.py` to the `contract-and-logic-gate` CI job.

### F4 — `d` (divers) is blocked by every gendered Ziffer · **severity: low–medium (open question)** · blocks release: **no**

`Sex = Literal["m","w","d"]` and LAYER 3.7 blocks on any `G != Allowed`, so a patient recorded as
`d` is refused all 15 gender-restricted Ziffern — including the urological ones whose restriction
is anatomical rather than administrative. Neither ADR-002 nor the batch 2 report takes a position
on `d`. Currently unreachable in production (F2). Pinned as a test so the behaviour is visible and
any change is deliberate. **Next action:** a product/clinical decision, not an engineering one.

### F5 — report §1 overstates the "no snapshots touched" claim · **severity: informational**

See §6. The substance holds (purely additive, no value moved); the sentence does not. **Next
action:** amend §1 of the batch 2 report.

---

## 11. Public-claim review

| # | Claim | Where | Verdict |
|---|---|---|---|
| C1 | `ENFORCED_RULE_COUNT = 944`, `CONSTRAINT_RULE_COUNT = 980` | `apps/marketing/src/lib/engine-facts.ts` | **Accurate** — recomputed 944 / 980; pinned by `test_published_numbers.py`, which passes |
| C2 | `ZIFFERN_UNDER_RULE_COUNT = 383`, `CATALOG_ZIFFER_COUNT = 2343` | same | **Accurate** — recomputed exactly |
| C3 | F01–F04 in `docs/content/facts.md` | `facts.md:26-49` | **Accurate**, each sourced to the constant and the pinning test |
| C4 | `"~15,3 %"` and `"358 von 2.343"` in `engine-facts.ts` doc comments | lines 56, 75 | **Was stale** — pre-batch-1 values left behind when the constant moved 358 → 383. Rendered output is computed from the constants, so nothing user-facing was wrong. **Fixed** to `~16,3 %` / `383 von` |
| C5 | Batch 2 report §2.1 prints GOÄ 382's official text as *"je Test"* | `coverage-sprint-report-batch2.md:61` | **Inaccurate by one character** — the catalog says *"je Text"*. The CSV is correct; the report tidied it. Recommend restoring the verbatim string with a `[sic]` |
| C6 | Batch 2 report §1: snapshots untouched | §1 | **Overstated** — see F5 |
| C7 | Batch 2 report §5 coverage table (944/981, 980/1017, 383/406, +23) | §5 | **Accurate** — every cell reproduced, including the 14-Ziffer overlap set |
| C8 | Batch 2 report §2.2: zero encodable Zeitbeziehung sentences | §2.2 | **Confirmed** by an independent scan |
| C9 | Batch 2 report §7: `logic_version` unchanged, no `.dl` edit | §7 | **Accurate** for the batch's own commit |
| C10 | Implied by report §6: Mengenbegrenzung works end to end | §6 | **Needs qualification** — true in test, not wired in production. See F2 |

No claim anywhere asserts that Batch 2 rules are enforced in production, and no published number
counts them. Words like "mathematically provable", "legally traceable", "production-ready" and
"all rules" do not appear attached to this batch.

**Documentation changed in this task:** only C4 — two stale illustrative figures in code comments.
Nothing else was edited; C5 and C6 are recommendations, left for the batch 2 report's author.

---

## 12. Command log

Working directory `apps/engine` unless noted. Full output under
`docs/content/batch2-validation-logs/`.

| # | Command | Exit | Result |
|---|---|---|---|
| 1 | `pytest tests/test_coverage_sprint_batch2.py tests/test_complex_constraints.py -q` | 0 | 24 passed (baseline) |
| 2 | `python scripts/validate_batch2_csvs.py` | 0 | 1,545 checks, 0 errors, 5 warnings |
| 3 | `pytest tests/test_validate_batch2_csvs.py -q` | 0 | 65 passed |
| 4 | `pytest tests/test_batch2_semantic_boundaries.py -q` | 0 | 188 passed |
| 5 | `pytest tests/test_batch2_parity_hardening.py tests/test_refreeze_rule_coverage.py tests/test_golden_snapshot.py -q` | 0 | 51 passed |
| 6 | `python scripts/engine_cli.py check` ×2 | 0, 0 | identical output; 944/980, 0 dangling, openapi builds |
| 7 | `pytest tests/ -q -k "receipt_is_stable or case_a"` | 0 | 31 passed |
| 8 | `python scripts/recompute_batch2_metrics.py` | 0 | all figures reproduce |
| 9 | `pytest tests/test_batch2_quarantine.py -q` | 0 | 156 passed |
| 10 | `python scripts/mutate_batch2.py` | 0 | 25 detected / 4 survivors / 0 unexpected; tree unchanged |
| 11 | `pytest tests/test_batch2_reproducibility.py -q` | 0 | 14 passed |
| 12 | `pytest tests/ -q -rs` (full engine suite) | 0 | **2,224 collected — 2,217 passed, 7 skipped, 0 failed, 0 errors.** The 7 skips are the 3 benchmarks (`--benchmark-skip`) and 4 Postgres-dialect tests (`POSTGRES_TEST_URL` unset), each naming its reason under `-rs` |
| 13 | CI logic guard, simulated on `main...HEAD` | — | **SATISFIED** (legal artefacts + golden evidence both present) |
| 14 | `python scripts/export_openapi.py --check` | 0 | up to date — 35 paths, 90 schemas |
| 15 | `pnpm turbo lint typecheck` (repo root) | 0 | 9/9 tasks; 0 errors, 6 pre-existing warnings unrelated to this work |

**Not run, and why:** `pnpm test` phase 4 (E2E) needs a stack answering on two ports, and
`engine-database` CI needs a Postgres service — neither was available, and neither exercises the
Batch 2 rule families. `pnpm turbo build` was skipped as it is unaffected by Python-only changes
(lint and typecheck, which do cover the one TypeScript comment edit, both passed).

---

## 13. Unresolved questions

1. **Is `age_man_26`'s `min_age: 2` intended?** F1 argues it is not. Needs a rules decision.
2. **Should `d` be blocked, admitted, or flagged for review?** F4. Needs a product decision.
3. **Is the Mengenbegrenzung wiring gap (F2) planned work or an oversight?** The table, the
   service and the tests all exist; only the call site is missing.
4. **Should the validator run in CI?** F3 — the `window` gate is only a gate if something runs it.

---

## 14. Artifacts

**Added**

| Path | Purpose |
|---|---|
| `apps/engine/scripts/validate_batch2_csvs.py` | CSV schema + citation + semantic validator |
| `apps/engine/scripts/recompute_batch2_metrics.py` | live coverage-metric recomputation |
| `apps/engine/scripts/mutate_batch2.py` | copy-isolated mutation harness |
| `apps/engine/tests/test_validate_batch2_csvs.py` | 65 tests — validator + harness |
| `apps/engine/tests/test_batch2_semantic_boundaries.py` | 188 tests — boundary sweep |
| `apps/engine/tests/test_batch2_quarantine.py` | 156 tests — quarantine enforcement |
| `apps/engine/tests/test_batch2_parity_hardening.py` | 18 tests — the `files_loaded` carve-out |
| `apps/engine/tests/test_batch2_reproducibility.py` | 14 tests — determinism, hashes, audit trail |

**441 tests added in total** (65 + 188 + 156 + 18 + 14), taking the engine suite from 1,783 to
2,224 collected. All pass; no existing test was modified, skipped or weakened.
| `docs/content/coverage-sprint-batch2-validation.md` | this report |
| `docs/content/batch2-validation-logs/` | raw command output |

**Modified**

| Path | Change |
|---|---|
| `apps/marketing/src/lib/engine-facts.ts` | two stale figures in doc comments (C4) — no constant, no rendered value |

**Unchanged:** `data/rules/`, `logic/`, and every production module. No rule was added, removed or
edited; no billing semantics were changed to make a test pass.
