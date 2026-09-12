# GOÄ coverage sprint — batch 2 report (ADR-002 rule types)

Internal engineering reference. Stand: 2026-09-12. Companion to `docs/content/coverage-sprint-
plan.md` (batch 1) and `docs/content/adr-002-complex-constraints.md` (the schema this batch fills
in). Every number below is either read live off `data/rules/*.csv` + `data/catalogs/goae_current/
goae.official.json`, or printed by `apps/engine/scripts/engine_cli.py check`.

**Scope.** ADR-002 shipped the mechanism (Datalog layers 3.5–3.8, `patient_ziffer_history`,
`app.services.patient_history`) with one worked example each, but declined to materialize
`data/rules/quantity_limits.manual.csv` and its three siblings — see the ADR §6 for why (an empty
file still reorders `files_loaded` in the frozen migration-parity snapshots). This batch does two
things: hardens the parity test so a new rule-file format can carry data (or stay empty) without
re-freezing anything, and materializes the four files with real, cited rows.

---

## 1. Parity-test hardening

`apps/engine/tests/test_golden_snapshot.py` compared every leaf of the frozen response against the
live one, including `audit_trail.rule_summary.files_loaded`, by array index — the general-purpose
comparison the whole file uses. `files_loaded` is sorted but not stable in *content*: inserting a
new filename shifts every alphabetically-later entry's index, which the old comparison read as N
values having changed and/or N new "fields" appearing, for a change that is neither.

Fixed by special-casing that one path in both tests:

- `test_the_engine_still_reproduces_the_frozen_snapshot` now compares `files_loaded` as a set
  (`frozen_files <= live_files`) — every file the snapshot saw must still load; new files are
  always fine — and strips that path's indices out of the generic index-by-index comparison.
- `test_no_undeclared_field_was_added` excludes the same path's indices from the "did the contract
  grow an undeclared field" check, since a new index there is new *data*, not a new *field*.

Nothing else changed about either test: a real value drifting anywhere else in the response still
fails both, with no allow-list. Verified by materializing all four files below (one of them,
`time_relations.manual.csv`, ends up with zero data rows this batch — see §3) and re-running
`test_golden_snapshot.py`. All 23 of its tests pass unmodified.

**Correction (2026-09-12).** An earlier revision of this section said the four files were
materialized "without touching any of the nine frozen `logic/tests/golden/*.golden.normalized
.json` files". That is true of the data commit itself, but not of the branch: the follow-up commit
that taught `refreeze_rule_coverage.py` the same `files_loaded` lesson re-froze all nine. The
claim worth making is the narrower one, and it holds — the re-freeze was **purely additive**. The
complete diff across all nine files is 36 added lines, four per file, each a new filename inside
`rule_summary.files_loaded`; **zero lines were removed and no value changed**. No billing
behaviour moved. See §6 of `docs/content/coverage-sprint-batch2-validation.md`.

---

## 2. What got materialized

37 new rule rows across three files, citing 37 distinct Ziffern (`verified: true`,
`verified_at: 2026-09-12`, `source: manual_verification:coverage_sprint_batch2`). None of them are
folded into the published `enforced_rule_count` / `total_constraint_rule_count` / catalog-coverage
figures — see §5 for why, and both numbers reported side by side.

### 2.1 Mengenbegrenzung — `data/rules/quantity_limits.manual.csv` (13 rows)

Only sentences whose window is literally `im Behandlungsfall` (a calendar quarter — the one window
`patient_history.behandlungsfall_bounds` computes) were encoded. A same-Ziffer cap phrased as
`je Sitzung`, `je Behandlungstag`, `je Kalenderjahr`, or `innerhalb von N Monaten/Jahren` asserts a
*different* window than the one this engine can evaluate, and encoding it under `window:
behandlungsfall` would silently strengthen or weaken the actual rule — see §4.

| Ziffer | max_count | Citation |
|---|---|---|
| 4 | 1 | "Die Leistung nach Nummer 4 ist im Behandlungsfall nur einmal berechnungsfähig." |
| 380 | 30 | official text: "Epikutantest, je Test (1. bis 30. Test je Behandlungsfall)" |
| 381 | 20 | official text: "Epikutantest, je Test (31. bis 50. Test je Behandlungsfall)" |
| 382 | 50 | official text: "Epikutantest, je Text [sic] (51. bis 100. Test je Behandlungsfall)" |
| 385 | 20 | official text: "Pricktest, je Test (1. bis 20. Test je Behandlungsfall)" |
| 386 | 20 | official text: "Pricktest, je Test (21. bis 40. Test je Behandlungsfall)" |
| 387 | 40 | official text: "Pricktest, je Test (41. bis 80. Test je Behandlungsfall)" |
| 388 | 10 | official text: "Reib-, Scratch- oder Skarifikationstest, je Test (bis zu 10 Tests je Behandlungsfall)" |
| 390 | 20 | official text: "Intrakutantest, je Test (1. bis 20. Test je Behandlungsfall)" |
| 807 | 1 | "Die Leistung nach Nummer 807 ist im Behandlungsfall nur einmal berechnungsfähig." |
| 842 | 1 | "Die Leistung nach Nummer 842 ist im Behandlungsfall nur einmal berechnungsfähig." |
| 860 | 1 | "Die Nummer 860 ist im Behandlungsfall nur einmal berechnungsfähig." |
| 4601 | 3 | "Eine mehr als dreimalige Berechnung der Leistung nach Nummer 4601 im Behandlungsfall ist nicht zulässig." |

The `[sic]` on 382 is not a typo in this table: the catalog entry really does read "je Text",
an upstream OCR defect in `goae.official.json`. `quantity_limits.manual.csv` quotes it verbatim,
defect included, because a citation that has been tidied is no longer the catalog's sentence —
`validate_batch2_csvs.py::citation_verbatim` enforces exactly that, and an earlier revision of
this table silently printed the corrected spelling. Nothing in the engine reads the quote, so
`max_count: 50` is unaffected either way.

380/381/382 (Epikutantest) and 385/386/387 (Pricktest) are banded: each Ziffer's own official text
states an explicit, non-overlapping test-number range for that specific billing code (e.g. 382 is
"test 51 through 100" — 50 tests, full stop, regardless of whether 380/381 were ever billed), so
`max_count` is the width of that Ziffer's own stated range, not a cross-code inference. 390's own
range (1–20) is decidable the same way; its sibling 391 ("jeder weitere Test") is **not** — see §3.

### 2.2 Zeitbeziehung — `data/rules/time_relations.manual.csv` (0 rows)

Zero "nicht am selben Tag" / "innerhalb von … Tagen" sentences relating two named Ziffern exist
anywhere in `goae_current` — confirmed by an independent full-catalog scan for this batch (not only
the previously-uncovered subset batch 1 scanned). The file is materialized with its header row and
no data, deliberately: this is the "a new rule-file format ships with zero rows" case §1's parity
hardening exists for. The Zeitbeziehung golden pair in `tests/test_complex_constraints.py`
(`test_same_day_time_relation_blocks_the_named_loser` /
`test_same_day_time_relation_does_not_fire_across_different_dates`) remains the only proof of this
layer — synthetic, because there is no real citation yet to replace it with. See §3 for the five
near-miss sentences this scan found and declined to encode.

### 2.3 Geschlecht — `data/rules/gender_restrictions.manual.csv` (15 rows)

| Ziffer | allowed_gender | Citation |
|---|---|---|
| 27 | w | "Untersuchung einer Frau zur Früherkennung von Krebserkrankungen …" |
| 1700 | m | "Spülung der männlichen Harnröhre …" |
| 1701 | m | "Dehnung der männlichen Harnröhre …" |
| 1702 | m | "Dehnung der männlichen Harnröhre mit filiformen Bougies …" |
| 1703 | m | "Unblutige Fremdkörperentfernung aus der männlichen Harnröhre" |
| 1704 | m | "Operative Fremdkörperentfernung aus der männlichen Harnröhre" |
| 1708 | m | "Kalibrierung der männlichen Harnröhre" |
| 1709 | w | "Kalibrierung der weiblichen Harnröhre" |
| 1710 | w | "Dehnung der weiblichen Harnröhre …" |
| 1711 | w | "Unblutige Fremdkörperentfernung aus der weiblichen Harnröhre" |
| 1728 | m | "Katheterisierung der Harnblase beim Mann" |
| 1729 | m | "Spülung der Harnblase beim Mann …" |
| 1730 | w | "Katheterisierung der Harnblase bei der Frau" |
| 1731 | w | "Spülung der Harnblase bei der Frau …" |
| 1782 | w | "Transurethrale Resektion des Harnblasenhalses bei der Frau" |

Every one names the anatomy in the Leistungslegende itself ("männliche/weibliche Harnröhre",
"beim Mann"/"bei der Frau", or, for 27, "Untersuchung einer Frau"). GOÄ 1051, used as the
illustrative example in `tests/test_complex_constraints.py`, is **not** duplicated here: its
restriction (an obstetric service, by medical necessity female-only) is not stated by an explicit
gendered word in the catalog text, only inferable from what "Fehlgeburt" means clinically — outside
this batch's "explicit sentence, cited" bar. It stays a synthetic test fixture, not a shipped rule.

### 2.4 Alter — `data/rules/age_restrictions.manual.csv` (9 rows)

| Ziffer | min_age | max_age | Citation |
|---|---|---|---|
| 26 | — | 13 | "… bei einem Kind bis zum vollendeten 14. Lebensjahr …" |
| 250a | — | 7 | "Kapillarblutentnahme bei Kindern bis zum vollendeten 8. Lebensjahr" |
| 273 | — | 3 | "… bei einem Kind bis zum vollendeten 4. Lebensjahr" |
| 412 | — | 1 | "… bei einem Säugling oder Kleinkind bis zum vollendeten 2. Lebensjahr" |
| 413 | — | 1 | "… bei einem Säugling oder Kleinkind bis zum vollendeten 2. Lebensjahr" |
| 1063 | — | 9 | "Vaginoskopie bei einem Kind bis zum vollendeten 10. Lebensjahr" |
| 5041 | — | 13 | "Beckenübersicht bei einem Kind bis zum vollendeten 14. Lebensjahr" |
| K1 | — | 3 | "Zuschlag zu Untersuchungen nach Nummer 5, 6, 7 oder 8 bei Kindern bis zum vollendeten 4. Lebensjahr" |
| K2 | — | 3 | "Zuschlag zu den Leistungen nach Nummer 45, 46, 48, 50, 51, 55 oder 56 bei Kindern bis zum vollendeten 4. Lebensjahr" |

Only sentences with an explicit "bis zum vollendeten N. Lebensjahr" number were encoded.
Bare "Neugeborenes" / "Säugling" / "Kleinkind" / "Kind" / "Jugendlicher" with no attached number
were quarantined — see §4; `Patient.age` is whole years, and a qualitative word alone does not fix
a defensible year boundary.

**Correction (2026-09-12) — GOÄ 26's lower bound, withdrawn.** This row originally shipped
`min_age: 2`, taken from the second half of its Anmerkung: "Die Leistung nach Nummer 26 ist **ab
dem vollendeten 2. Lebensjahr** je Kalenderjahr höchstens einmal berechnungsfähig." Treated as an
eligibility gate, that made the engine refuse the Früherkennungsuntersuchung to every child under
two — the U-Untersuchungen of the first two years, which is the population the service exists for.

The sentence does not say that. It says when a *frequency* cap begins to apply, and it is an
Anmerkung; in this catalog, eligibility is stated in the Leistungslegende, whose only age bound
here is the upper one. The wider evidence is one-sided: "ab dem vollendeten N. Lebensjahr" occurs
**exactly once** in all 2,343 Ziffern — this sentence — while "bis zum vollendeten N. Lebensjahr"
occurs in nine Leistungslegenden (all nine encoded here) and in one further Anmerkung, GOÄ 30's,
which is a fee adjustment and was itself quarantined. Both annotation-resident age numbers in the
catalog modify something other than eligibility.

`min_age` is therefore withdrawn and the Anmerkung is no longer cited by this row; `max_age: 13`
and its Leistungslegende citation stand unchanged. The fragment is recorded in
`tests/test_batch2_quarantine.py::QUARANTINED_AGE_FRAGMENTS` with the reason *"ambiguous:
eligibility gate vs frequency activation — requires human review"*, and
`test_no_shipped_age_rule_asserts_a_lower_bound` prevents any row from reintroducing a lower bound
without an explicit Leistungslegende one behind it. Full evidence: §10 (finding F1) of
`docs/content/coverage-sprint-batch2-validation.md`.

---

## 3. Quarantined — near-misses, and why (no guessing)

Grouped by the reason a sentence was held out, not encoded as a rule this batch. 81 Mengenbegrenzung
candidates were examined in total (73 from an unconditional regex pass over every Ziffer's
`official_text` + `annotations`, plus 8 more found by hand while checking the Epikutantest/Prick-
test/Intrakutantest band family) — 13 included (§2.1), 68 quarantined below.

**Mengenbegrenzung (68 quarantined):**

- *Conditional justification duty, not a prohibition* ("bedarf einer/ist … zu begründen"): **3,
  4610**.
- *Unsupported window — per Sitzung/Behandlungstag, not per Behandlungsfall*: **351, 360, 361, 420,
  440, 442, 443, 444, 445, 446, 447, 448, 449, 569, 626, 627, 628, 629, 5111, 5135, 5190, 5265,
  5315, 5316, 5328, 5335, 5442** (5442's annotation also states the 5440–5442 mutual exclusion,
  already enforced via batch 1's `exclusions.manual.csv`; only its per-Sitzung self-cap is new and
  quarantined here).
- *Unsupported window — per Kalenderjahr or a stated N-month/year period, not per Behandlungsfall*:
  **15, 21, 26, 30, 31, 33, 34**. (GOÄ 26's Anmerkung is now quarantined in full: the
  Mengenbegrenzung clause for its `je Kalenderjahr` window, and — since the 2026-09-12 correction
  in §2.4 — the `ab dem vollendeten 2. Lebensjahr` fragment too, which had been read as an Alter
  eligibility gate. Only 26's Leistungslegende upper bound is encoded.)
- *Conditioned on "aus demselben Untersuchungsmaterial/Probenmaterial" — not visible on an invoice
  line, same shape batch 1 already declined for GOÄ 4851→4850*: **3511, 3550, 4530, 4531, 4533,
  4538, 4539, 4551, 4715, 4716**.
- *Conditioned on distinguishing which fungus species ("je Pilz")*: **4717**.
- *Caps the number of participants in a group session, not one patient's billing frequency*: **847,
  862, 864, 871, 887** (871 also has a separate conditional-doubling clause tied to session length).
- *Anti-fragmentation of one imaging event ("mittels einer Röntgenaufnahme"), not a cross-quarter
  cap — a patient may legitimately repeat the study on a different day*: **5000, 5011, 5021, 5031,
  5035**.
- *Cross-code cumulative total, not expressible as one Ziffer's own count*: **391** ("mehr als 80
  Intrakutantests" sums 390 and 391 together; 391's own share depends on how much of 390 was used
  and is not stated on its own).
- *Once-per-simultaneously-treated-group-of-patients, not a per-patient repeat cap at all*: **560**.
- *Ambiguous or undefined window ("in engem/im zeitlichen Zusammenhang", "insgesamt", "für eine …
  Kur")*: **77, 430, 5803, 5851**.
- *Not a rule about this Ziffer at all — a pricing-provenance footnote naming an unrelated,
  superseded collective position, caught by the regex on "höchstens"*: **4572, 4573, 4574, 4575,
  4576**.

**Zeitbeziehung (5 examined, 0 included):**

- **45, 46**: permissive ("… können … berechnet werden" / bills the *next* visit under a different
  Ziffer), the opposite of an exclusion — encoding either as `same_day_excludes` would forbid a
  combination the text is actually authorizing.
- **247**: "nicht an demselben Tag angelegten Gipsverband" names no specific Ziffer for the cast
  placement to compare against.
- **726**: a real same-day condition (725 and 726 same day only if ≥ 45 minutes apart) — but stated
  in minutes, and `TimeRelationRule.min_hours` is a whole-hour field; representing "45 Minuten" as
  an integer number of hours would misstate the cited threshold, so this is held out on a schema/
  precision mismatch rather than guessed into a rounded number.
- **1407**: regex false positive ("Binnenohrmuskeln" contains "binnen" as a substring; no temporal
  content).

**Geschlecht (3 quarantined of 18 examined):**

- **6, 7**: the female/male anatomy mentioned is one optional organ system among several a doctor
  may choose to examine under a general comprehensive-exam Ziffer, not a gate on the whole Ziffer.
- **4851**: "z.B. aus dem Genitale der Frau" is one illustrative example specimen source ("z.B."),
  not an eligibility restriction on the Ziffer.

**Alter (27 Ziffern quarantined of 36 examined, plus one fragment — see §2.4):**

- *"Neugeboren(es/er)" with no attached number — whole-year age granularity cannot distinguish a
  newborn (~0–28 days) from any other infant under one year, and asserting `max_age: 0` would be
  materially looser than the cited term*: **25, 281, 283, 566, 1040, 2571, 3287**.
- *Qualitative "Kind"/"Jugendlicher" with no attached number*: **807, 817, 835, 885, 886, 887, 1080,
  1123a, 1294**.
- *Qualitative "Säugling"/"Kleinkind" with no attached number*: **716, 717, 2505, 2525, 3127, 3171,
  3189**.
- *Illustrative example only ("z.B. bei einem Säugling"), not an eligibility restriction*: **2429**.
- *Age band is part of a conditional fee-adjustment (half fee if child and session short), not a
  gate on who may be billed at all*: **30**.
- *Explicitly qualified as a guideline, not an absolute cutoff ("in der Regel bis zur Vollendung des
  7. Lebensjahres")*: **1406**.
- *A numeric band exists only by reference to an external statute (Jugendarbeitsschutzgesetz) not
  restated in the catalog text*: **32**.

---

## 4. Why the schema's `window: behandlungsfall` restriction matters here

`QuantityLimitRule.window` only ever evaluates `"behandlungsfall"` (§2 of the ADR): `patient_history
.behandlungsfall_bounds` computes calendar-quarter bounds, nothing narrower or wider. A GOÄ sentence
capping a Ziffer "je Sitzung" or "je Behandlungstag" describes a *tighter* window (one session/day);
enforcing it at the quarter level would block legitimate repeats on separate days within the same
quarter — an over-broad, wrong rule, not a conservative approximation of a correct one. A sentence
capping "je Kalenderjahr" or "innerhalb von 6 Monaten" describes a *different* window that spans
quarter boundaries in a way `behandlungsfall_bounds` cannot compute at all. Both shapes are real,
citable Mengenbegrenzung sentences and both are quarantined rather than mis-mapped onto the one
window this batch's mechanism supports — extending `window` to a second value is future work with
its own Datalog change (and its own `logic_version` bump), not a data-entry decision.

---

## 5. Coverage numbers — both, side by side

Per instruction, the public denominator is **not** changed this batch. `RuleStore.constraint_rules()`
/ `enforced_rule_count()` / `summary()` still only add up exclusions, Zielleistung, specificity and
factor caps — exactly as ADR-002 §7 designed it, so folding a new family in remains a product
decision made on purpose, not a side effect of shipping data.

| | Current (published) | If the four new families counted |
|---|---|---|
| Enforced rules | 944 | 944 + 37 = **981** |
| Total constraint rules loaded | 980 | 980 + 37 = **1,017** |
| Ziffern named by ≥1 enforced rule | 383 / 2,343 (16.35%) | 383 + 23 = **406 / 2,343 (17.33%)** |

The "+23" (not "+37") on the last row is not a typo: of the 37 Ziffern touched by a new rule this
batch, 14 (`4`, `26`, `27`, `273`, `807`, `860`, `1700`, `1701`, `1710`, `1728`, `1729`, `1730`,
`1731`, `5041`) were already named by an existing exclusion/Zielleistung/specificity/factor-cap
rule, so only 23 are *newly* represented in the "under rule" set at all. Both figures are computed
live by the script in the appendix of `coverage-sprint-plan.md`, extended to read the four new files
the same way; nothing here is typed from memory.

---

## 6. Golden tests added

`apps/engine/tests/test_coverage_sprint_batch2.py` — every test loads the **real** corpus via the
existing `rules`/`souffle` fixtures (`RuleStore.load(RULES_DATA_DIR)`), not a hand-built RuleStore,
deliberately the opposite isolation choice from `test_complex_constraints.py`: the point here is to
prove the shipped CSV rows fire against the real engine, not just that the Datalog layer can.

- Mengenbegrenzung: GOÄ 4601 blocked on a 4th claim (`history_counts={"4601": 3}`) / admitted on a
  3rd (`{"4601": 2}`), asserting `rule_id == "cnt_man_4601"`.
- Geschlecht: GOÄ 27 blocked for `sex="m"` / admitted for `sex="w"`, asserting
  `rule_id == "gr_man_27"`.
- Alter: GOÄ 26 blocked for `age=42` / admitted for `age=8`, asserting `rule_id == "age_man_26"`.
- **Two-invoice Mengenbegrenzung, end to end**: `record_occurrences` is called twice against a real
  in-memory database — invoice 1 (2026-07-10) records one GOÄ 4601, invoice 2 (2026-08-04) records
  two more — then `quarter_counts` reads them back as `{"4601": 3}` and that dict is handed, exactly
  as `app.solvers.souffle_engine` expects it, into a third run that claims a 4th GOÄ 4601 and is
  blocked by the real `cnt_man_4601` row. A sibling test proves a second patient pseudonym in the
  same organisation is unaffected by the first patient's history.

Zeitbeziehung keeps its existing synthetic golden pair in `test_complex_constraints.py` — see §2.2.

---

## 7. Engine check, full suite, logic guard, Soufflé

- `python scripts/engine_cli.py check`: `944 of 980 enforced`, `0 dangling` references (every new
  Ziffer — `380`, `K1`, `4601`, … — resolves in the loaded catalog), `openapi schema builds`.
- Full `apps/engine` pytest suite (run from `apps/engine`, not the monorepo root — running it from
  the wrong directory produces spurious fixture errors unrelated to this change): green, zero
  failures and zero errors.
- `logic/datalog/goae_rules.dl` / `logic/asp/goae_optimize.lp`: **not edited** this batch (the
  Datalog layers already existed, per ADR-002 §1); `logic_version` (`83fae8e7f0369c25`) is
  unchanged, so no 7f917db-style re-pin was needed for it.
- `rules_hash()` (`app/services/rule_coverage.py`) hashes every `*.csv` under `data/rules/`
  regardless of family, so it **did** move — four new files, three with real rows. That is inside
  `receipt_hash`, so `CASE_A_RECEIPT_PREFIX` (`tests/golden/oracle.py`) and `receipt_hash_prefix`
  (`tests/golden/case_a_known_answer/expected.json`) were re-pinned, following the exact batch-1
  precedent: confirmed stable across two runs (`test_case_a_receipt_is_stable_across_runs`) before
  either value was touched. Nothing about case A's own Ziffern, factors or amounts moved.
