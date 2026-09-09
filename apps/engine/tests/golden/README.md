# Golden cases

Five PADnext deliveries whose answers were worked out from the fee schedule, plus two reproducers
for fixed defects. The runbook is [`docs/api/E2E_GOLDEN.md`](../../../../docs/api/E2E_GOLDEN.md);
this file is the map.

```
oracle.py                          the expectations, computed from data/ — imports nothing from app/
case_a_known_answer/               5 positions, 78.81 €, nothing wrong and nothing confirmed
case_b_verified_exclusion/         excl_auto_34_4 fires; GOÄ 4 blocked, GOÄ 34 untouched
case_c_verified_factor_cap/        cap_auto_440 fires at 2.3; the same Ziffer at exactly 1.0 survives
case_d_arithmetic_mismatch/        case A with one gesamtbetrag +10.00 €
case_e_echtdaten_gate/             case A with no @echtdaten → 422, then anonymised → case A
bug_positionsnr_collision/         a regular case now — findings keyed by id(row), not positionsnr
case_f_cross_patient_boundary/     excl_auto_34_4 must not cross an <abrechnungsfall> boundary
case_g_cross_date_same_patient/    excl_auto_34_4 across two service dates is advisory, not wrong
```

`case_f_cross_patient_boundary/` and `case_g_cross_date_same_patient/`, like
`bug_positionsnr_collision/`, have a hand-computed `expected.json` rather than one `oracle.py`
derived — see the comment above their tests in
[`tests/test_golden_cases.py`](../test_golden_cases.py) for why the oracle's generic per-delivery
walker cannot be the source of truth for either.

Each directory is a `delivery_padx.xml` + `expected.json` pair. Two runners read them and must never
disagree:

* [`tests/test_golden_cases.py`](../test_golden_cases.py) — in process, over `TestClient`;
* [`scripts/e2e_partner_api.py`](../../../../scripts/e2e_partner_api.py) — over real HTTP, with a
  real minted API key, against a running stack.

Both compare through `oracle.compare_report`, which is why there is one definition of "matches" and
not two.

## The rule that makes this worth running

**No expectation here was produced by running the engine.** `oracle.py` reads
`data/catalogs/goae_current/goae.official.json` and the `verified=true` rows of `data/rules/*.csv`,
and recomputes every amount as `ROUND_HALF_UP(punkte × faktor × punktwert_cent ÷ 100, cent)` in
`Decimal`. A test asserts the module imports nothing from `app`, in a subprocess, because an oracle
that could reach the engine could only ever agree with it.

Regenerate after a catalog or rules change, and **read the diff**:

```bash
apps/engine/.venv/bin/python apps/engine/tests/golden/oracle.py --write
apps/engine/.venv/bin/python apps/engine/tests/golden/oracle.py          # check only
```

`test_expectations_are_not_stale` fails if a committed `expected.json` has drifted from `data/`, so
this cannot go quietly out of date. A changed euro figure is a changed fee schedule, not a formatting
nit — and if the data is unchanged and the engine disagrees, the engine is the thing to fix.
