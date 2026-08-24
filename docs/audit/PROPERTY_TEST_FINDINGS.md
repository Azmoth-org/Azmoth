# Property-test findings

**Date:** 2026-08-24 · **Suite:** `apps/engine/tests/property/` (Hypothesis) · **Engine:** `7f77afa`

Five invariants were added over randomly generated `POST /api/v1/solve` requests. One open defect
came out of the first wide sweep. **No solver logic, rule table, catalog or schema was modified** —
the fix for the defect below is a legal-posture change and belongs in its own reviewed branch.

## What was run

| Sweep | Command | Result |
|---|---|---|
| Documented run | `pytest tests/property/ --hypothesis-seed=0` | 6 passed, 1 xfail, ~40 s |
| Wide sweep, before the guard | `HYPOTHESIS_MAX_EXAMPLES=1500 pytest tests/property/ --hypothesis-seed=random` | **5 failed** — all five properties, one shared cause |
| Wide sweep, after the guard | `HYPOTHESIS_MAX_EXAMPLES=2000 pytest tests/property/ --hypothesis-seed=random` | 6 passed, 1 xfail |

The five failures were one bug, not five: every property calls the same `_solve`, and the request
that broke it made the *validator* refuse the invoice, so every assertion downstream never ran.

## F-1 — an Analogansatz position escapes both legality constraints

**Severity:** high. A clinically ordinary request returns `500`. No wrong amount is ever billed —
the validator catches it — but the engine cannot answer a question it should be able to answer.

**Status:** open. Recorded as
`tests/property/test_financial_invariants.py::test_the_analog_ladder_ignores_exclusions_against_the_final_invoice`,
an `xfail(strict=True)` that reproduces it in four lines and fails the build the day it is fixed.

### Minimal reproduction

```json
{
  "patient": {"age": 50, "sex": "m", "setting": "ambulant"},
  "examinations": [{"type": "vollstaendige_untersuchung_organsystem"}],
  "procedures": [
    {"type": "dermatoskopie", "organ": "haut"},
    {"type": "sonographie"},
    {"type": "optische_kohaerenztomographie"}
  ]
}
```

→ `500 VALIDATION_FAILED`:

```
exclusion_violation(7): GOÄ 5 und GOÄ 7 stehen gemeinsam auf der Rechnung,
                        obwohl Regel excl_man_5_7 das ausschließt.
exclusion_violation(5): GOÄ 7 und GOÄ 5 stehen gemeinsam auf der Rechnung,
                        obwohl Regel excl_man_7_5 das ausschließt.
```

### Root cause

The two hard constraints in `logic/asp/goae_optimize.lp` range over `bill/1`:

```prolog
:- bill(A), bill(B), excluded(A, B), A != B.
:- bill(C), bill(P), zielleistung(P, C).
```

An analog position never enters `bill/1`. It arrives through the § 6 Abs. 2 choice rule and
contributes to `charged/1` only:

```prolog
1 { analog(A, Z) : has_analog_cand(A, Z) } 1 :- analog_needed(A, _).
charged(Z) :- bill(Z).
charged(Z) :- analog(_, Z).
```

So it faces neither constraint. Nothing else is missing: `ClingoSolver.build_facts` computes
`in_play` as `billable | arbitration_candidates | analog_ziffern` and *does* inject
`excluded("5","7")`. The fact is there and unused.

Walking the reproduction:

| Step | Result |
|---|---|
| Bridge | `a1→7`, `a2→750`, `a4→410`; `a3` (OCT) has no mapping → analog request |
| Soufflé | `billable = [410, 7, 750]`, nothing blocked |
| OCT ladder | Nr. 750 (0.75), Nr. 410 (0.55), Nr. 5 (0.25) |
| Clingo | 750 and 410 are billed directly, and `@5 #minimize analog_collision` outranks `@2` similarity → picks **Nr. 5** |
| Validator | Nr. 5 ⊕ Nr. 7 is enforced → refuses, `500` |

The layered design is what makes this visible: the component that picks the number is not the
component that approves it, and here the approver was right.

### The change that would fix it — for review, not applied

Widening both constraints to the relation that already includes analog positions:

```diff
-:- bill(A), bill(B), excluded(A, B), A != B.
-:- bill(C), bill(P), zielleistung(P, C).
+:- charged(A), charged(B), excluded(A, B), A != B.
+:- charged(C), charged(P), zielleistung(P, C).
```

The catalog guard immediately below them already reads `:- charged(Z), not code_info(Z, _, _).`,
which suggests `charged/1` was the intent for legality throughout and these two heads were simply
left behind.

**Two things need deciding before that lands, and neither is a test author's call:**

1. **It can make the program UNSAT.** `1 { analog(A, Z) } 1` demands exactly one analog position
   per unlisted service. If every candidate on a ladder is excluded against something already
   billed, a hard constraint has no model, and the caller gets "nothing is chargeable" instead of
   an invoice — the failure mode the `@5` comment in that file explicitly avoids by keeping
   collisions soft. Relaxing the cardinality to `0 { ... } 1` and reporting an uncovered analog
   request is the obvious companion change, and it adds a new honest outcome to the response
   contract.
2. **It changes what is billed.** On the reproduction above the solver would charge Nr. 750
   analogously *with* a collision warning instead of Nr. 5. That is a better answer, but it is a
   different invoice, and `CONTRIBUTING.md` puts changes to what the system is willing to bill
   behind legal and domain review.

Suggested branch: `fix/analog-respects-exclusions`.

### What the test suite does about it meanwhile

`tests/property/conftest.py::_analog_conflicts` keeps the generator out of exactly this region: an
Analogansatz service is not documented alongside a service whose Ziffer is mutually exclusive with
one of that analog type's candidate targets. It is derived from `analog_candidates.csv`,
`exclusions*.csv` and `zielleistung*.csv` rather than written out, so a new analog candidate or a
new exclusion widens it automatically instead of quietly reopening the hole — and
`test_the_generated_space_is_worth_exploring` pins its current size, so a widening fails rather
than silently costing coverage.

Today that region is one pair: `optische_kohaerenztomographie` (the only analog type in the
tables) against `vollstaendige_untersuchung_organsystem` (Nr. 7) and
`untersuchung_ganzkoerperstatus` (Nr. 8). No assertion was weakened to accommodate it, and the
Analogansatz path itself — including the collision warning — is still generated everywhere else.

## What held

Everything else, across ~10 000 generated requests over two sweeps:

- **Money.** Punktzahl x Punktwert x Faktor, § 6a Minderung per line, ROUND_HALF_UP at the cent,
  summed — exact against a recomputation from the catalog, including the unrounded cent amount,
  which is the one comparison with no rounding on either side to hide an error.
- **Uniqueness and ordering.** No Ziffer twice; lines always in canonical order; no position both
  charged and reported blocked.
- **Proof.** Every charged line and every blocked position carries its reason, and every reconciled
  blocker is genuinely on the final invoice.
- **Factors.** Always inside `[1.0, Höchstsatz]`, narrowed by any Leistungslegende cap, and never
  above the Schwellenwert without a written reason (§ 12 Abs. 3 GOÄ).
- **Determinism.** Same request → same `Coding` and same `receipt_hash`, with the result cache off
  so each run genuinely re-solved.
