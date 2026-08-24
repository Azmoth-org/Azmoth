# Property-test findings

**Date:** 2026-08-24 · **Suite:** `apps/engine/tests/property/` (Hypothesis) · **Engine:** `7f77afa`,
findings re-checked after the analog/exclusion fix

Five invariants were added over randomly generated `POST /api/v1/solve` requests, and one defect
came out of the first wide sweep. At the time of writing **no solver logic, rule table, catalog or
schema was modified** — the fix was a legal-posture change and belonged in its own reviewed branch.

> **F-1 is now fixed** on `fix/analog-respects-exclusions`. The write-up below is kept as the
> record of how it was found and what was decided; the "what changed, and what did not" section at
> the end says what actually landed. A sixth property and a golden case
> (`case_009_analog_exclusion`) replaced the `xfail`, and the generator no longer avoids the
> region — it aims at it.

## What was run, when the defect was found

Historical — these are the runs that found F-1, against the engine *before* the fix. The post-fix
runs are in "What changed, and what did not" at the end.

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

**Status: FIXED.** Both constraints now range over `charged/1`. The reproduction below is pinned as
`tests/property/test_financial_invariants.py::test_the_analog_ladder_respects_exclusions_against_the_final_invoice`
— no longer an `xfail`, and now asserting the invoice it produces rather than only the absence of a
violation.

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

### The change that fixed it

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

**Two things needed deciding before it landed, and both were carried out as predicted:**

1. **It can make the program UNSAT.** `1 { analog(A, Z) } 1` demands exactly one analog position
   per unlisted service. If every candidate on a ladder is excluded against something already
   billed, a hard constraint has no model, and the caller gets "nothing is chargeable" instead of
   an invoice — the failure mode the `@5` comment in that file explicitly avoids by keeping
   collisions soft. **Done:** the cardinality is now `0 { ... } 1`, and an uncovered request is
   reported as an `analog_uncovered` warning.

   The companion change turned out to need a third piece. `0 { ... } 1` on its own makes the
   coverage *worse*, not better: an uncovered request scores 0 collisions at `@5` while a
   colliding one scores 1, so the solver would rather charge nothing than charge a colliding
   candidate. So `analog_uncovered` feeds the **same** `@5` term — `analog_collision(A, "")` —
   which makes "no candidate at all" exactly as expensive as one collision, and `@2` (similarity)
   and `@1` (points) then break the tie toward covering the service. Coverage therefore still wins
   whenever any candidate is legal, and the relaxation only ever bites where the alternative was
   UNSAT. Feeding the existing term rather than adding an `@6` was deliberate:
   `test_the_objective_ordering_is_untouched` forbids a new priority level, and rightly — that
   would be an objective-ordering change requiring legal review, which this is not.

   With the current tables the uncovered branch is **unreachable**: Nr. 750 and Nr. 410 appear in
   no exclusion or Zielleistung row, so the OCT ladder always has a legal rung. It is defensive,
   and it is there because adding one exclusion row on Nr. 750 would otherwise convert this `500`
   into a different `500`.

2. **It changes what is billed.** **Confirmed, and only where it had to.** On the reproduction the
   solver now charges Nr. 750 analogously with a collision warning instead of Nr. 5. Across the
   whole bundled corpus the change is provably contained:
   `test_the_engine_still_reproduces_the_frozen_snapshot` compares every leaf of all eight frozen
   snapshots against the live engine, and the **only** value that moved is
   `audit_trail.logic_version`, the SHA over the logic programs,
   which must move when one of them changes. No charged position, factor, amount, blocked entry or
   proof step differs in any of the eight.

Branch: `fix/analog-respects-exclusions`.

### What changed, and what did not

**The logic** — `logic/asp/goae_optimize.lp`, four edits:

| Change | Why |
|---|---|
| both legality constraints `bill/1` → `charged/1` | the fix itself |
| `1 { analog(A,Z) } 1` → `0 { analog(A,Z) } 1` | the widened constraints can leave a ladder with no legal rung; UNSAT is a `500` too |
| `analog_uncovered/1`, scored via `analog_collision(A, "")` | keeps coverage strictly preferred, without a new priority level |
| `analog_blocked/4` | reports *which* rungs the invoice ruled out, and under which relation |

`analog_blocked/4` is the one addition that is not strictly required to stop the `500`. It is there
because "the § 6 Abs. 2 ladder silently skipped its two closest candidates" is not an auditable
statement, and the § 6 Abs. 2 decision is the one a Rechnungsprüfer is most likely to challenge. It
surfaces through the existing `BlockedCode` contract — `reason: "exclusion" | "zielleistung"`,
which the schema already had — so no response field was added or changed.

**One latent bug surfaced with it.** The arbitration-loss loop in `ClingoSolver._parse_model`
tested `ziffer in billed`, so a member of a mutual cluster that the solver did not bill directly but
*did* put on the invoice as someone else's Analogziffer was reported `conflict_lost` while being
charged — the same Ziffer in `proposed_codes` and `blocked_codes` at once. It was unreachable while
the generator avoided this region, and `test_uniqueness_invariant` caught it within one wide sweep
of the guard being removed. It now tests the full charged set.

**The test suite.** The generator no longer avoids anything. `_analog_conflicts()` — the filter that
kept this region out — became `_analog_exclusion_rows()`, the same derivation over
`analog_candidates.csv`, `exclusions*.csv` and `zielleistung*.csv`, feeding
`analog_exclusion_requests()`: a strategy that documents an Analogansatz service *together with*
something incompatible with one of its candidates, on purpose. The region is still one pair —
`optische_kohaerenztomographie` against `vollstaendige_untersuchung_organsystem` (Nr. 7) and
`untersuchung_ganzkoerperstatus` (Nr. 8) — and `test_the_generated_space_is_worth_exploring` still
pins it, but as a **floor** now rather than a ceiling: widening is welcome, emptying it out is what
fails.

| Sweep, after the fix | Result |
|---|---|
| `pytest tests/property/ --hypothesis-seed=0` | 8 passed, no xfail |
| `HYPOTHESIS_MAX_EXAMPLES=1500 pytest tests/property/ --hypothesis-seed=random` | 8 passed (~9 000 requests, the previously-excluded region included) |
| `pytest` (whole engine suite) | 1009 passed, 7 skipped, **0 xfailed** |

**What was not changed:** no database schema, no response schema, no objective and no priority
level, no rule table, no catalog, and no `expected.json` for cases 001–008.

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
