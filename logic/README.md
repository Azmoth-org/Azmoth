# `logic/` — the symbolic layer

Everything in this directory is **declarative legal reasoning**, deliberately kept outside the
Python service so that it can be read, reviewed and diffed by someone who does not read Python.
`apps/engine` loads these files at runtime from `LOGIC_DIR` (default: this directory).

```
logic/
├── asp/
│   └── goae_optimize.lp        Clingo answer-set program — resolves the choices Datalog leaves open
├── datalog/
│   └── goae_rules.dl           Soufflé Datalog program — derives what is CERTAIN
└── tests/
    ├── cases/                  synthetic inputs (input.json) + expectations (expected.json)
    │   ├── case_001_knee/               all three suppression layers + the § 5 Abs. 2 ladder
    │   ├── case_002_cardiology/         EKG arbitration, § 5 Abs. 4 lab band, one-line justification
    │   ├── case_003_dermatology/        § 6 Abs. 2 Analogansatz incl. the collision rule
    │   ├── case_004_factor_cap/         Höchstsatz reached with a written reason, per band
    │   ├── case_005_mutual_exclusion/   mutual exclusion where evidence beats revenue
    │   ├── case_006_zielleistung/       § 4 Abs. 2a against a well-documented component
    │   ├── case_007_missing_docs/       no justification anywhere: fall back to the Schwellenwert
    │   ├── case_008_complex_polytrauma/ 21 Ziffern, three clusters, § 6a Minderung
    │   └── padnext/            synthetic PADnext delivery (.auf order file, _padx.xml payload, .padx container)
    └── golden/                 frozen, canonicalised full responses — <case>.golden.normalized.json
```

## Where things live

| Asset | Path | Loaded by |
| --- | --- | --- |
| Clingo ASP program | `logic/asp/goae_optimize.lp` | `app/solvers/clingo_solver.py` (`settings.asp_path`) |
| Soufflé Datalog program | `logic/datalog/goae_rules.dl` | `app/solvers/souffle_engine.py` (`settings.datalog_path`) |
| Golden snapshots | `logic/tests/golden/*.golden.normalized.json` | `apps/engine/tests/test_golden_snapshot.py` |
| Synthetic cases | `logic/tests/cases/<case>/{input,expected}.json` | `apps/engine/tests/test_manual_cases.py` |
| What each case tests | `docs/audit/GOLDEN_CORPUS.md` | — (prose; the assertions live in `expected.json`) |
| PADnext fixture | `logic/tests/cases/padnext/` | `apps/engine/tests/test_padnext.py` |

The rule *data* (exclusions, Zielleistung, specificity, analog candidates, factor caps) is not
here — it is versioned data, not logic, and lives in `data/rules/`. The GOÄ catalog lives in
`data/catalogs/goae_current/`.

---

## ⚠️ Rule verification status must be preserved

Every row in `data/rules/*.csv` carries `verified`, `verified_at`, `source`, `legal_basis` and
`quote`. The bulk of the exclusion rules (837 of them) were **extracted automatically from the
fee schedule's prose** and are *not* human-verified. `UNVERIFIED_RULE_POLICY` decides what they
may do:

| Policy | Effect |
| --- | --- |
| `warn` **(default)** | the rule suppresses nothing; the response carries a warning and the rule is counted as *advisory* |
| `block` | the rule is enforced exactly like a verified one |
| `ignore` | the rule is dropped entirely and counted |

`warn` is the safe default: **a machine-read rule must not suppress a chargeable service until a
human has confirmed it against the law.**

Consequently:

- Do **not** delete unverified rules. They are reported, not hidden.
- Do **not** flip `verified` to `true` without a named reviewer and a `verified_at` date.
- Do **not** edit the catalog JSON or the rule CSVs by hand. Corrections go through
  `data/catalogs/goae_current/overrides.json`, which requires `reason`, `source` and
  `verified_at` on every entry and is rejected without them.
- Every solve and audit response reports `enforced_rule_count`, `advisory_rule_count` and
  `suppressed_unverified_rule_count` so the API can never imply that unverified rules are
  enforced.

## ⚠️ Objective priorities must not be changed without legal and domain review

`goae_optimize.lp` optimises **lexicographically**, and revenue is last:

```
@5  never charge an analog position that is already charged directly   (§ 6 Abs. 2 GOÄ)
@4  never leave a documented, chargeable service off the invoice entirely
@3  prefer the position with the stronger clinical evidence
@2  prefer the more specific position
@1  higher total points   ← tiebreaker ONLY
```

This ordering is the legal posture of the whole system:

- Evidence and specificity outrank money **on purpose**. An objective that maximised revenue
  would systematically pick whichever of two competing positions pays more — that is upcoding.
- `@1` only separates options that are equally well evidenced and equally specific.
- The hard rules are **integrity constraints** (`:- bill(A), bill(B), excluded(A,B).` and
  `:- bill(C), bill(P), zielleistung(P,C).`), not weighted objectives. No objective can trade
  them away.
- The Zielleistungsprinzip (§ 4 Abs. 2a GOÄ) is resolved in **Datalog**, not in the optimiser,
  precisely because components are frequently worth more in sum than the target service.
- The Steigerungsfaktor ladder never exceeds the § 5 band, and any factor above the
  Schwellenwert is marked `justification_required` (§ 12 Abs. 3 GOÄ). Factor choice without
  documentation is not permitted.

Changing the order of `@5/@4/@3/@2/@1`, converting a hard constraint into a soft one, or adding a
revenue term above `@1` changes what this system is willing to bill for. Any such change requires
sign-off from legal **and** medical-billing domain review, and the golden snapshots in
`logic/tests/golden/` must be re-verified by hand — not regenerated — because they are the record
of what the previous posture produced.
