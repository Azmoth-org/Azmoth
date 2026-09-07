# Golden cases

Five PADnext deliveries whose answers were worked out from the fee schedule, plus one reproducer for
an open defect. The runbook is [`docs/api/E2E_GOLDEN.md`](../../../../docs/api/E2E_GOLDEN.md); this
file is the map.

```
oracle.py                        the expectations, computed from data/ — imports nothing from app/
case_a_known_answer/             5 positions, 78.81 €, nothing wrong and nothing confirmed
case_b_verified_exclusion/       excl_auto_34_4 fires; GOÄ 4 blocked, GOÄ 34 untouched
case_c_verified_factor_cap/      cap_auto_440 fires at 2.3; the same Ziffer at exactly 1.0 survives
case_d_arithmetic_mismatch/      case A with one gesamtbetrag +10.00 €
case_e_echtdaten_gate/           case A with no @echtdaten → 422, then anonymised → case A
bug_positionsnr_collision/       NOT a golden case — a strict xfail; see the runbook §5
```

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
