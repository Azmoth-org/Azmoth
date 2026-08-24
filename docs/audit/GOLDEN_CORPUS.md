# The golden case corpus

**Date:** 2026-08-24 · **Cases:** `logic/tests/cases/` · **Snapshots:** `logic/tests/golden/` ·
**Runner:** `apps/engine/tests/test_manual_cases.py`, `apps/engine/tests/test_golden_snapshot.py`

Eight synthetic encounters, each one chosen because it pins a rule the others do not. Cases 001 to
003 came with the migration. Cases 004 to 008 were added here to cover the edge cases a randomised
property sweep reaches rarely or never: the ends of the factor ladder, arbitration where the
evidence and the money disagree, § 4 Abs. 2a against a well-documented component, and one large
encounter in which every mechanism fires at once.

**No solver logic, rule table, catalog or schema was modified.** Every `expected.json` records what
the engine at `51e8601` actually decides, and each decision below was read back and checked against
the GOÄ text before it was frozen. One provenance imprecision surfaced while doing that and is
recorded as G-1 — it is not fixed here.

## What each case pins

| Case | Setting | Charged | Blocked | The assertion that only this case makes |
|---|---|---|---|---|
| `case_001_knee` | ambulant | 5 | 3 | all three suppression layers in one solve, plus the `mittel` rung |
| `case_002_cardiology` | ambulant | 9 | 1 | Nr. 650–653 arbitration; § 5 Abs. 4 band; a justification that must not leak |
| `case_003_dermatology` | ambulant | 6 | 0 | § 6 Abs. 2 Analogansatz, including the collision rule |
| `case_004_factor_cap` | ambulant | 6 | 0 | the Höchstsatz is **per band**: the same `schwer` reason gives 3.5 and 1.3 |
| `case_005_mutual_exclusion` | ambulant | 5 | 1 | arbitration where the better-documented position is the **cheaper** one |
| `case_006_zielleistung` | ambulant | 5 | 1 | § 4 Abs. 2a beats a component's own confidence **and** its own justification |
| `case_007_missing_docs` | ambulant | 6 | 0 | no reason anywhere → Schwellenwert, not rejection; every gap reported |
| `case_008_complex_polytrauma` | stationär | 14 | 7 | 21 Ziffern, three clusters, layer stratification, § 6a Minderung |

### case_004_factor_cap — the top of the ladder

Suspected septic arthritis of the shoulder. Three written reasons of three severities land on three
rungs of the § 5 Abs. 2 ladder at once:

| Line | Band | Severity documented | Factor | Basis |
|---|---|---|---|---|
| Nr. 302 puncture | 2.3 / 3.5 | `schwer` | **3.5** | `hoechstsatz` |
| Nr. 7 examination | 2.3 / 3.5 | `mittel` | 2.6 | `ueber_schwellenwert` |
| Nr. 3741 CRP | 1.15 / **1.3** | `schwer` | **1.3** | `hoechstsatz` |
| Nr. 3, Nr. 410, Nr. 3550 | — | none | Schwellenwert | `schwellenwert` |

The point of the pairing: the identical `schwer` severity produces 3.5 on a general-band position
and 1.3 on a § 5 Abs. 4 laboratory position. A ceiling hard-coded at 3.5 anywhere in the ladder
would pass every other case in the corpus and fail this one. The second point is that a factor
*at* the maximum with a written reason is **accepted and capped**, never refused — the three lines
that carry a reason are `justification_required: true` with `justification_present: true`, and the
three that do not stay at their Schwellenwert, so a per-service justification provably does not
raise the rest of the invoice.

### case_005_mutual_exclusion — evidence outranks revenue

Nr. 422 to Nr. 424 are not chargeable next to one another, so Datalog exports the pair as a
`conflict` rather than letting negation-as-failure delete both. The record documents Nr. 423 fully
(confidence 1.0, all standard planes) and Nr. 424 as an aborted Doppler study with no image
documentation (0.60).

Nr. 424 is worth **700 Punkte**, Nr. 423 only **500** — and Nr. 423 is charged. The evidence
objective is resolved before the revenue objective, so the engine gives up 200 Punkte rather than
bill the better-paying position on the weaker record. This is the only case in the corpus where the
two objectives point in opposite directions: in `case_001` and `case_002` the better-evidenced
position also happened to pay more, so both would still pass if the ordering were inverted.

### case_006_zielleistung — a hard rule is not a trade-off

A wrist puncture with a compression dressing. The wrist is named in neither Nr. 301 (elbow, knee,
vertebral joint) nor Nr. 302 (shoulder, hip), so the act yields only the generic **Nr. 300** and no
specificity contest happens — which makes the firing rule `ziel_man_300_200` rather than the
`ziel_man_301_200` that `case_001` exercises.

The dressing is deliberately given every advantage: confidence 1.0, a detailed record, and its own
`mittel` justification. It is blocked anyway, because § 4 Abs. 2a is resolved in Datalog and is not
reachable by any objective. The justification bound to it is silently irrelevant rather than
redirected somewhere it could inflate a line that *is* charged.

### case_007_missing_docs — the fallback, and the report

Every act is recorded as `komplex` with confidence 1.0, and the record contains no besondere
Schwierigkeit, no erhöhter Zeitaufwand and no erschwerende Umstände. Two things must both hold:

- **complexity alone must not raise a factor.** All six lines sit exactly on their Schwellenwert
  (2.3 for Nr. 3, 7, 301, 410; 1.15 for Nr. 3550 and Nr. 3741) and none is flagged
  `justification_required`. `max_factor` in the expectation is pinned *equal to* the factor here, so
  a future ladder that read `complexity` would fail rather than quietly bill more.
- **a missing reason must not reject the line.** Nothing is blocked. Instead all six appear in
  `missing_documentation` with the factor the band would allow, which is the engine saying "the
  record does not support more" and never "charge more".

That second half is what the new
`test_case_reports_the_expected_documentation_gaps` assertion exists for: the gap report is the only
part of the response that would vanish with no visible effect on the invoice.

### case_008_complex_polytrauma — everything at once

An inpatient primary survey after a traffic accident. 21 Ziffern across chapters B, C, F, M and O
reach the rules engine; 14 are charged, 7 are blocked, each with its own reason:

| Mechanism | Blocked | Winner | Why |
|---|---|---|---|
| exclusion cluster Nr. 5 / 7 / 8 | 5, 7 | **8** | whole-body status is the best documented (1.0 / 0.85 / 0.60) |
| exclusion cluster Nr. 422 / 423 / 424 | 422, 423 | **424** | the full Doppler study is the one with documentation |
| exclusion cluster Nr. 650–653 | 650 | **651** | twelve-lead ECG over a monitor strip; Nr. 659 is chargeable alongside |
| specificity | 300 | **301** | knee-specific position displaces the generic one |
| Zielleistung § 4 Abs. 2a | 200 | **301** | the dressing is a component of the puncture |

The Zielleistung entry is the one worth reading twice. Nr. 200 is blocked by **Nr. 301** — the
parent that survived the specificity layer — and not by Nr. 300, which was itself suppressed one
layer earlier. That is exactly the guarantee the stratification of `goae_rules.dl` is built for: a
position that has already lost must not suppress a third one. A single self-referential `blocked`
relation would have produced `blocked_by: 300` here and nobody would have noticed on a smaller case.

Two justifications raise exactly two lines (Nr. 8 to 3.5, Nr. 301 to 2.6) and leave twelve at their
Schwellenwert; in particular the shoulder puncture Nr. 302 stays at 2.3 even though the knee
puncture's reason names an act of the same type. And because the encounter is `stationaer`, § 6a
Abs. 1 reduces every line by 25 %: **429.72 € gross → 322.29 € net**. It is the only bundled case
in which the reduction fires, so it is the one that fails if the rate or the § 6a Abs. 1 Satz 3
exemption list moves.

`pytest tests/test_manual_cases.py tests/test_golden_snapshot.py` is 130 tests over the eight cases
in about 15 s, `case_008` included; the full engine suite is 997 tests in about 90 s.

## G-1 — a blocked position can cite the wrong rule row of the right Anmerkung

**Severity:** low. No amount and no code is affected; the legal basis shown to a reader is correct.
Only the `rule_id` is imprecise. **Status:** open, deliberately not fixed here.

In a cluster of three or more mutually exclusive positions, `BlockedCode.rule_id` names *a* rule the
losing position is party to, not the rule against the position that actually won:

```
GOÄ 5   blocked_by 8    rule_id excl_man_7_5      ← the (5,7) row, not (5,8)
GOÄ 7   blocked_by 8    rule_id excl_man_7_5      ← the (7,5) row, not (7,8)
GOÄ 423 blocked_by 424  rule_id excl_man_423_422  ← the (423,422) row, not (423,424)
```

`app/solvers/clingo_solver.py::_parse_model` picks it with a `next(...)` over
`rules_result.conflicts` that filters on membership only:

```python
rule = next((c.rule_id for c in rules_result.conflicts if ziffer in (c.ziffer_a, c.ziffer_b)), "")
```

while `blocked_by` a few lines above is resolved correctly against the winner. `legal_basis` is then
read off that same row — and today it stays correct, because a mutual cluster is always built from
one Anmerkung, so every row in it quotes the same sentence of the GOÄ. The citation becomes wrong
the day a cluster spans two Anmerkungen.

The fix is to prefer the conflict row whose other member is the winner and fall back to the current
behaviour, which is a two-line change in `_parse_model`. It is not made here because it moves the
`rule_id` field of `blocked_codes` in a committed golden snapshot, and `CONTRIBUTING.md` hard rule 2
says a change that moves a snapshot is investigated and confirmed by a second person, not folded
into a commit that adds tests. Suggested branch: `fix/blocked-code-cites-the-deciding-rule`.

The behaviour is pinned rather than hidden: `case_008`'s `expected.json` records these `blocked_by`
values as assertions, notes the imprecision in the entry for Nr. 7, and the golden snapshot freezes
the current `rule_id` strings — so the day the fix lands, the snapshot fails and has to be
re-verified by hand.

## Adding a case

1. Write `logic/tests/cases/<case>/input.json`. It is a bare `ClinicalExtraction`, which forbids
   unknown fields, so the explanation of what the case tests goes in `notes` — there is nowhere else
   to put a comment, and `test_case_uses_only_synthetic_data` requires the word "synthetic" there
   anyway. That test also rejects a payload containing `@`, `geb.`, `geboren`, `strasse` or
   `versicherungsnummer`, which is a PII guard and will happily trip on prose about objectives.
2. Only entity types present in `data/mappings/entity_to_ziffer.csv` produce a Ziffer. Anything else
   is either an `unmapped_entity` warning or an Analogansatz, and the service is not charged.
3. Run the case and read the output before writing `expected.json` — never the other way round.
4. Freeze the snapshot: `canonical()` of the `solver_result`, `indent=2`, `ensure_ascii=False`, no
   trailing newline, written to `logic/tests/golden/<case>.golden.normalized.json`.
   `test_golden_snapshots_exist` fails for a case without one.
5. Add the directory name to `test_there_are_synthetic_cases`. Everything else is parametrised off
   the directory listing and picks the case up on its own.
