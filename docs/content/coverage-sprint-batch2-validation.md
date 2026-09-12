# GOÄ coverage sprint — batch 2 validation report

Internal engineering reference. Stand: 2026-09-12. Independent validation of
`docs/content/coverage-sprint-report-batch2.md` — every figure below was recomputed or re-run
against the checkout, not read out of that report.

**Final status: VALIDATED WITH QUALIFICATIONS.**

The corpus is schema-clean, citation-exact, deterministic and correctly quarantined; the parity
relaxation is sound and narrowly scoped; every published metric reproduces to the digit.

**F1 is resolved.** `age_man_26` was blocking GOÄ 26 for every child under two on the strength of
a sentence that sets when a *frequency* cap starts, not who may be billed. Its `min_age` is
withdrawn, the fragment is quarantined with a regression test, and the receipt hash is re-pinned.
Evidence, decision and diff in §10 (finding F1).

**F2 remains the standing qualification**: all 37 rows are inert on the PADnext ingestion path,
because no production call site supplies `history_counts`, `Patient.age` or `Patient.sex`. That is
a wiring gap, not a false claim — the batch is deliberately excluded from every published number,
and nothing public counts a rule that cannot fire. It stays open until the pipeline wiring lands.

Three lower-severity findings (F3–F5) are documented and, where they were documentation defects,
fixed in place.

---

## 1. Repository state

| | |
|---|---|
| Repository | `/home/oussama/Desktop/MVP/TARGET_MONOREPO` |
| Branch | `feat/goae-coverage-sprint-batch1` |
| HEAD at start | `cc8ff7b` — *fix(rules): refreeze_rule_coverage.py — files_loaded is metadata* |
| Validation commit | `4025fed` — validator, harness, 441 tests, first revision of this report |
| F1 resolution | this revision — one CSV line, receipt re-pin, test updates, report corrections |
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
5041→13, K1→3, K2→3.

`age_man_26` originally also carried `min_age: 2`, taken from an Anmerkung rather than the
Leistungslegende. That was finding **F1**, now resolved — see §10. After the fix **no shipped row
asserts a lower age bound**, which `test_no_shipped_age_rule_asserts_a_lower_bound` enforces.

---

## 3. The validator

**`apps/engine/scripts/validate_batch2_csvs.py`** — 1,539 checks over the four files, exit 0 on
the shipped corpus with **0 errors, 4 warnings**.

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

The warnings on the shipped corpus:

| Warning | Files | Assessment |
|---|---|---|
| `line_endings_are_lf` | all four | **Benign, verified.** The files are CRLF. `RuleStore._rows` opens with `newline=''` and hands the handle to `csv`, which strips the terminator — confirmed by loading all 37 rows and finding zero values carrying a CR or edge whitespace. `exclusions.csv` and `factor_bands.csv` are CRLF too, so this is the existing convention. Reported so a reviewer knows it is deliberate. |

The fifth warning in the first revision of this report was
`min_age_is_eligibility_not_frequency` on `age_man_26` — a real defect, and the one that became
finding **F1**. It is **gone** now that the row no longer asserts a lower bound: the shipped
corpus raises **0 errors and 4 warnings**, all four the benign CRLF notice.

Tests: **`apps/engine/tests/test_validate_batch2_csvs.py`**, 65 tests, all passing. Every check
that can fail is driven against a deliberately broken copy in `tmp_path`; `data/rules/` is never
written to.

---

## 4. Semantic boundaries

**`apps/engine/tests/test_batch2_semantic_boundaries.py`** — 192 tests, all passing, every one
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
bound admitted · one year above blocked · **age 0 admitted for every shipped row** (true of all
nine since F1 was resolved) · unknown admitted · the `NO_MIN_AGE=0` / `NO_MAX_AGE=999` sentinels
proven unreachable for a valid `Patient.age` · GOÄ 26 specifically admitted at ages 0, 1 and 2 and
still blocked at 14.

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

**`apps/engine/tests/test_batch2_quarantine.py`** — 160 tests, all passing. All 103 quarantined
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

### F1 — `age_man_26` encoded a frequency condition as an eligibility gate · **severity: high (billing correctness)** · **RESOLVED**

**Symptom (before).** The shipped rule carried `min_age: 2`, so the engine refused GOÄ 26 —
*Untersuchung zur Früherkennung von Krankheiten bei einem Kind* — to any patient aged 0 or 1:

```
souffle.run(_extraction(age=1), make_bridge(("a1", "26", 100, "1.0")))
# → billable=[]  blocked=[('26','age_restricted','age_man_26')]  detail='patient_age:1/band:2-13'
```

Flagged independently from the data alone by
`validate_batch2_csvs.py::min_age_is_eligibility_not_frequency`.

#### Evidence

`data/catalogs/goae_current/goae.official.json` holds **no structured age field of any kind** —
an entry's keys are `ziffer, official_text, punkte, category, section, section_title, status,
provenance, rule_coverage, text_quality, minderung_exempt, annotations`. All age information for
GOÄ 26 is free text in exactly two strings, and no `overrides.json` entry or unparsed row touches
this Ziffer.

**Sentence A — the source of `max_age: 13`** · field: `official_text` (the **Leistungslegende**)

> Untersuchung zur Früherkennung von Krankheiten bei einem Kind **bis zum vollendeten 14.
> Lebensjahr** (Erhebung der Anamnese, Feststellung der Körpermaße, Untersuchung von
> Nervensystem, Sinnesorganen, Skelettsystem, Haut, Brust-, Bauch- und Geschlechtsorganen) -
> gegebenenfalls einschließlich Beratung der Bezugsperson(en) -

**Sentence B — the source of `min_age: 2`** · field: `annotations[0]` (an **Anmerkung**)

> Die Leistung nach Nummer 26 ist **ab dem vollendeten 2. Lebensjahr** je Kalenderjahr höchstens
> einmal berechnungsfähig.

#### Which reading each text supports

**Sentence A → (a) eligibility gate, upper bound only.** "bei einem Kind bis zum vollendeten 14.
Lebensjahr" is an attributive qualifier on *Kind*: it defines who the service may be performed on,
inside the definition of the service. It states no lower bound.

**Sentence B → (b) frequency activation.** The predicate is *"ist … höchstens einmal
berechnungsfähig"*; "je Kalenderjahr" is its window and "ab dem vollendeten 2. Lebensjahr" is the
point from which that cap applies. The operative restriction the sentence exists to impose is the
once-per-year cap — an eligibility gate would read *"ist erst ab dem vollendeten 2. Lebensjahr
berechnungsfähig"*, with no frequency clause. Reading it as (a) requires inferring a prohibition
from a sentence whose subject is frequency, and it inverts clinical reality: the
Früherkennungsuntersuchungen of the first two years are the most frequently billed instances of
this service.

Two further facts from the catalog make the structural pattern one-sided, and neither depends on
reading German:

* **"ab dem vollendeten N. Lebensjahr" occurs exactly once in all 2,343 Ziffern** — this sentence.
  There is no second instance to compare against, and no instance anywhere of the phrase used as
  an eligibility gate.
* **"bis zum vollendeten N. Lebensjahr" occurs in 9 Leistungslegenden and in 1 Anmerkung.** All
  nine Leistungslegende occurrences are the age rules this batch ships. The single Anmerkung
  occurrence is GOÄ 30's — *"Dauert die Erhebung einer homöopathischen Erstanamnese bei einem Kind
  bis zum vollendeten 14. Lebensjahr weniger als eine Stunde, …"* — a conditional **fee
  adjustment**, which report §3 had already quarantined for exactly that reason.

So both annotation-resident age numbers in this catalog modify something other than eligibility,
and every eligibility bound lives in a Leistungslegende. Sentence B is an Anmerkung.

#### Decision

The decision rule was: *if the Leistungslegende states an explicit lower age bound, keep `min_age`
and re-cite it; otherwise remove it.* **The Leistungslegende for Nr. 26 states no lower age
bound** — its only age phrase is the upper one in Sentence A. Therefore `min_age` is **removed**.

`max_age: 13` is kept, re-cited to Sentence A alone. Sentence B is moved to the quarantine list
with the reason *"ambiguous: eligibility gate vs frequency activation — requires human review"* —
recorded under the weaker "ambiguous" label deliberately, because the operative decision is
identical under readings (b) and (c) and only (a) could justify blocking, which no
Leistungslegende text supports.

#### Diff

```diff
--- a/data/rules/age_restrictions.manual.csv
+++ b/data/rules/age_restrictions.manual.csv
-age_man_26,26,2,13,GOÄ Leistungslegende Nr. 26 + Anmerkung,"Untersuchung zur Früherkennung … -  | Die Leistung nach Nummer 26 ist ab dem vollendeten 2. Lebensjahr je Kalenderjahr höchstens einmal berechnungsfähig.",true,2026-09-12,…
+age_man_26,26,,13,GOÄ Leistungslegende Nr. 26,"Untersuchung zur Früherkennung … -",true,2026-09-12,…
```

One line. `min_age` emptied, `legal_basis` narrowed to the Leistungslegende, and the Anmerkung
dropped from `quote` — a row must not keep citing a sentence it no longer encodes anything from.
CRLF line endings preserved byte-for-byte.

#### Behaviour after

| Age | Before | After |
|---|---|---|
| 0 | blocked | **admitted** |
| 1 | blocked | **admitted** |
| 2 | admitted | admitted |
| 13 | admitted | admitted |
| 14 | blocked | blocked — `detail: patient_age:14/band:0-13`, `legal_basis: GOÄ Leistungslegende Nr. 26` |

The cited upper bound still fires; only the uncited lower bound is gone.

#### Regression protection

* `test_batch2_semantic_boundaries.py::test_goae_26_admits_a_child_under_two` (ages 0, 1, 2) —
  replaces the old `test_goae_26_blocks_a_one_year_old`, which had pinned the defect.
* `…::test_goae_26_still_blocks_above_its_cited_upper_bound` — the fix removed one bound, not both.
* `test_batch2_quarantine.py::QUARANTINED_AGE_FRAGMENTS` plus three tests: the fragment's bound is
  not encoded, the rule no longer cites it, and **the engine never blocks a child under two on
  GOÄ 26**, asserted end to end.
* `…::test_no_shipped_age_rule_asserts_a_lower_bound` — the general form. No row may carry a
  `min_age` at all; a future one may only do so with an explicit Leistungslegende lower bound.

#### Consequences

`rules_hash()` moved `4fbec3c5…` → `6cfde287…`, and with it the case A receipt,
`9f2a7e385de0fc51` → **`a6ab0366db492a08`**. Both pins (`tests/golden/oracle.py::
CASE_A_RECEIPT_PREFIX` and `case_a_known_answer/expected.json`) were re-pinned following the exact
batch-1/batch-2 precedent: the new value was confirmed identical across two separate processes
**before** either pin was touched, and the comment records why it moved. No case A Ziffer, factor
or amount changed — the rest of `test_golden_cases.py` (23 tests) passes unmodified, and case A
claims none of the Ziffern this batch constrains.

`refreeze_rule_coverage.py` reports **all nine golden snapshots CLEAN — "Nothing to do: every
snapshot already matches"** — so no billing behaviour moved anywhere in the golden corpus. That
report is what the real CI logic guard needed and did not have at the time — see F6: the branch's
own self-check was run against a stale diff base, and the mechanical gate correctly found no
evidence in `logic/tests/`. Closed by committing `logic/tests/golden/refreeze_report.json` and the
`scripts/logic_guard.py` carve-out that checks it.


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

### F5 — report §1 overstated the "no snapshots touched" claim · **severity: informational** · **FIXED**

See §6. The substance holds (purely additive, no value moved); the sentence did not. §1 of the
batch 2 report now carries a dated correction saying so.

### F6 — row 13's "CI logic guard: SATISFIED" was checked against the wrong diff · **severity: medium (process)** · **FIXED**

**Symptom.** The real `contract-and-logic-gate` CI job failed on this branch: `data/rules/age_restrictions.manual.csv`
changed (F1) but the diff carried no file under `logic/tests/(golden|cases)/`, and the guard's bash
refused it exactly as designed.

**Why the self-check missed it.** Row 13 below was "simulated on `main...HEAD`" against a local
`main` that had not been updated past `cc8ff7b`/`a5ad632`/`7323630` — commits already merged to
`origin/main` by the time this branch was validated. Diffed against the real base (`origin/main`),
those commits' `logic/tests/golden/*.json` changes drop out of the comparison entirely, leaving
only this branch's own commits — which touch `age_restrictions.manual.csv` and nothing under
`logic/tests/`. The local simulation was answering a different question than the one CI actually
asks.

**Why the gate was right to refuse it anyway, and why a real golden case can't fix that.** Investigated
whether a golden case could exercise GOÄ 26 to give the guard real evidence. It cannot:
`logic/tests/cases/*/input.json` only carries clinical extraction data, and the only path from an
extraction to a Ziffer is `data/mappings/entity_to_ziffer.csv` — which has zero rows for Ziffer 26,
or for any Ziffer in the other three ADR-002 families (quantity/gender/age/time). This is a sharper
version of F2: not just "the request-shaping fields are unpopulated in production", but "the
extraction pipeline has no way to request these Ziffern at all." No `logic/tests/cases/` fixture can
move, however real the rule edit is.

**Fix.** `scripts/logic_guard.py` (unit-tested in `tests/test_logic_guard.py`) now encodes the
gate's decision, including a narrow ADR-002 family carve-out: when every legal artefact changed is
one of the four family CSVs, the gate accepts a touched family regression test *and* a committed,
fresh, all-CLEAN `logic/tests/golden/refreeze_report.json` (`scripts/refreeze_rule_coverage.py
--report`, whose `rules_hash` is checked against the rule tables on disk — a stale or non-clean
report is refused like no evidence at all). Every other legal artefact — a `.dl`/`.lp` edit, the
catalog, any non-family CSV — still requires golden-corpus evidence exactly as before; the carve-out
never widens to cover them, even alongside a family CSV in the same diff. See the sunset item in
§13.

---

## 11. Public-claim review

| # | Claim | Where | Verdict |
|---|---|---|---|
| C1 | `ENFORCED_RULE_COUNT = 944`, `CONSTRAINT_RULE_COUNT = 980` | `apps/marketing/src/lib/engine-facts.ts` | **Accurate** — recomputed 944 / 980; pinned by `test_published_numbers.py`, which passes |
| C2 | `ZIFFERN_UNDER_RULE_COUNT = 383`, `CATALOG_ZIFFER_COUNT = 2343` | same | **Accurate** — recomputed exactly |
| C3 | F01–F04 in `docs/content/facts.md` | `facts.md:26-49` | **Accurate**, each sourced to the constant and the pinning test |
| C4 | `"~15,3 %"` and `"358 von 2.343"` in `engine-facts.ts` doc comments | lines 56, 75 | **Was stale** — pre-batch-1 values left behind when the constant moved 358 → 383. Rendered output is computed from the constants, so nothing user-facing was wrong. **Fixed** to `~16,3 %` / `383 von` |
| C5 | Batch 2 report §2.1 prints GOÄ 382's official text as *"je Test"* | `coverage-sprint-report-batch2.md` §2.1 | **Was inaccurate by one character** — the catalog says *"je Text"*. The CSV was always correct; the report had tidied it. **Fixed**: the table now reads *"je Text [sic]"* with a note explaining the upstream OCR defect and why the citation is not corrected |
| C6 | Batch 2 report §1: snapshots untouched | §1 | **Was overstated** — see F5. **Fixed**: §1 now carries a dated correction stating that `cc8ff7b` re-froze all nine, that the diff is 36 added lines and zero removed, and that no value moved |
| C7 | Batch 2 report §5 coverage table (944/981, 980/1017, 383/406, +23) | §5 | **Accurate** — every cell reproduced, including the 14-Ziffer overlap set |
| C8 | Batch 2 report §2.2: zero encodable Zeitbeziehung sentences | §2.2 | **Confirmed** by an independent scan |
| C9 | Batch 2 report §7: `logic_version` unchanged, no `.dl` edit | §7 | **Accurate** for the batch's own commit |
| C10 | Implied by report §6: Mengenbegrenzung works end to end | §6 | **Needs qualification** — true in test, not wired in production. See F2, which remains open |
| C11 | Batch 2 report §2.4 lists GOÄ 26 with `min_age: 2` | §2.4 | **Was unsupported** — see F1. **Fixed**: the table now shows `—`, and a dated correction records the withdrawal, the catalog-wide evidence and the quarantine entry |

No claim anywhere asserts that Batch 2 rules are enforced in production, and no published number
counts them. Words like "mathematically provable", "legally traceable", "production-ready" and
"all rules" do not appear attached to this batch.

**Documentation changed in this task:** C4 (two stale illustrative figures in code comments),
and — as part of resolving F1 and closing the gate — C5, C6 and C11 in
`docs/content/coverage-sprint-report-batch2.md`. Each is a dated, narrow correction that states
what the earlier text claimed and what the evidence shows; no number was changed without a
recomputation behind it, and §5's coverage table needed no change at all (the corpus is still 37
rows over 37 Ziffern).

---

## 12. Command log

Working directory `apps/engine` unless noted. Full output under
`docs/content/batch2-validation-logs/`.

| # | Command | Exit | Result |
|---|---|---|---|
| 1 | `pytest tests/test_coverage_sprint_batch2.py tests/test_complex_constraints.py -q` | 0 | 24 passed (baseline) |
| 2 | `python scripts/validate_batch2_csvs.py` | 0 | 1,539 checks, **0 errors, 4 warnings** |
| 3 | `pytest tests/test_validate_batch2_csvs.py -q` | 0 | 65 passed |
| 4 | `pytest tests/test_batch2_semantic_boundaries.py -q` | 0 | 192 passed |
| 5 | `pytest tests/test_batch2_parity_hardening.py tests/test_refreeze_rule_coverage.py tests/test_golden_snapshot.py -q` | 0 | 51 passed |
| 6 | `python scripts/engine_cli.py check` ×2 | 0, 0 | identical output; 944/980, 0 dangling, openapi builds |
| 7 | `pytest tests/ -q -k "receipt_is_stable or case_a"` | 0 | 31 passed |
| 8 | `python scripts/recompute_batch2_metrics.py` | 0 | all figures reproduce |
| 9 | `pytest tests/test_batch2_quarantine.py -q` | 0 | 160 passed |
| 10 | `python scripts/mutate_batch2.py` | 0 | 25 detected / 4 survivors / 0 unexpected; tree unchanged |
| 11 | `pytest tests/test_batch2_reproducibility.py -q` | 0 | 14 passed |
| 12 | `pytest tests/ -q -rs` (full engine suite) | 0 | **2,232 collected — 2,225 passed, 7 skipped, 0 failed, 0 errors.** The 7 skips are the 3 benchmarks (`--benchmark-skip`) and 4 Postgres-dialect tests (`POSTGRES_TEST_URL` unset), each naming its reason under `-rs` |
| 16 | `pytest tests/test_golden_cases.py -q` (after the F1 re-pin) | 0 | 23 passed — receipt re-pinned, no billing number moved |
| 17 | `python scripts/refreeze_rule_coverage.py` (after F1) | 0 | all 9 snapshots **CLEAN**; "Nothing to do: every snapshot already matches" |
| 13 | CI logic guard, simulated on `main...HEAD` | — | **Was wrong** — see F6. Simulated against a stale local `main`; the real `origin/main` base leaves no golden-corpus evidence in this branch's diff, and the mechanical gate correctly failed |
| 14 | `python scripts/export_openapi.py --check` | 0 | up to date — 35 paths, 90 schemas |
| 15 | `pnpm turbo lint typecheck` (repo root) | 0 | 9/9 tasks; 0 errors, 6 pre-existing warnings unrelated to this work |
| 18 | `python scripts/refreeze_rule_coverage.py --report ../../logic/tests/golden/refreeze_report.json` | 0 | all 9 CLEAN; report committed for `scripts/logic_guard.py`'s ADR-002 family carve-out (F6) |
| 19 | `pytest tests/test_logic_guard.py tests/test_validate_batch2_csvs.py -q` | 0 | 10 + 65 passed |

**Not run, and why:** `pnpm test` phase 4 (E2E) needs a stack answering on two ports, and
`engine-database` CI needs a Postgres service — neither was available, and neither exercises the
Batch 2 rule families. `pnpm turbo build` was skipped as it is unaffected by Python-only changes
(lint and typecheck, which do cover the one TypeScript comment edit, both passed).

---

## 13. Unresolved questions

1. ~~**Is `age_man_26`'s `min_age: 2` intended?**~~ **Closed.** The Leistungslegende states no
   lower bound, so it is withdrawn (§10, F1). What remains open is the narrower question a human
   should still answer: whether *"ab dem vollendeten 2. Lebensjahr je Kalenderjahr höchstens
   einmal"* should eventually be encoded as a **Mengenbegrenzung** once a `kalenderjahr` window
   exists — it is a frequency rule, and this engine has no window for it.
2. **Should `d` be blocked, admitted, or flagged for review?** F4. Needs a product decision.
3. **Is the Mengenbegrenzung wiring gap (F2) planned work or an oversight?** The table, the
   service and the tests all exist; only the call site is missing.
4. **Should the validator run in CI?** F3 — the `window` gate is only a gate if something runs it.
5. **Sunset the ADR-002 family carve-out, per family, as F2 closes.** F6. The carve-out in
   `scripts/logic_guard.py` exists only because quantity/gender/age/time Ziffern have no
   `entity_to_ziffer.csv` row, so no golden case can exercise them. The moment a family gets that
   wiring — production supplies the fact its Ziffern need, and at least one gets a mapping row — a
   real `logic/tests/cases/` fixture must be added for it and `FAMILY_CSVS` in `logic_guard.py`
   trimmed to drop that file. Tracked here rather than only in the script comment so it surfaces at
   the next batch's planning, not just to someone reading the gate's source.

---

## 14. Artifacts

**Added**

| Path | Purpose |
|---|---|
| `apps/engine/scripts/validate_batch2_csvs.py` | CSV schema + citation + semantic validator |
| `apps/engine/scripts/recompute_batch2_metrics.py` | live coverage-metric recomputation |
| `apps/engine/scripts/mutate_batch2.py` | copy-isolated mutation harness |
| `apps/engine/tests/test_validate_batch2_csvs.py` | 65 tests — validator + harness |
| `apps/engine/tests/test_batch2_semantic_boundaries.py` | 192 tests — boundary sweep |
| `apps/engine/tests/test_batch2_quarantine.py` | 160 tests — quarantine enforcement |
| `apps/engine/tests/test_batch2_parity_hardening.py` | 18 tests — the `files_loaded` carve-out |
| `apps/engine/tests/test_batch2_reproducibility.py` | 14 tests — determinism, hashes, audit trail |

**449 tests added in total** (65 + 192 + 160 + 18 + 14 — the extra 8 over the first revision are
F1's regression tests), taking the engine suite from 1,783 to 2,232 collected. All pass. The only
pre-existing tests touched are the two receipt pins, re-pinned for a hash that legitimately moved;
nothing was skipped, weakened or deleted.
| `docs/content/coverage-sprint-batch2-validation.md` | this report |
| `docs/content/batch2-validation-logs/` | raw command output |

**Modified**

| Path | Change |
|---|---|
| `apps/marketing/src/lib/engine-facts.ts` | two stale figures in doc comments (C4) — no constant, no rendered value |
| `data/rules/age_restrictions.manual.csv` | **F1**: `age_man_26` drops `min_age` and the Anmerkung it cited (§10) |
| `apps/engine/tests/golden/oracle.py` | `CASE_A_RECEIPT_PREFIX` re-pinned for the hash F1 moved, with the reason recorded |
| `apps/engine/tests/golden/case_a_known_answer/expected.json` | same pin; the only changed line |
| `docs/content/coverage-sprint-report-batch2.md` | §1 snapshot overstatement, §2.1 "je Text [sic]", §2.4 and §3 updated for F1 |

**Unchanged:** `logic/` and every production module. The one rule edit removes an uncited
restriction; no rule was added, and no billing semantics were changed to make a test pass — the
receipt re-pin follows a hash that moved *because* of the rule edit, which is the documented
precedent, and every case A amount is asserted unchanged independently.
