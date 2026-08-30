# State of the Engine — GOÄ Audit Core

**Date:** 2026-08-29 · **Branch:** `feat/azmoth-marketing-site` · **Commit:** `47d0e68`
**Catalog:** `goae_official_snapshot_2026-07-25` (sha256 `244b4033…`, 2192 Ziffern)
**Rules:** `auto_extracted_2026-07-25` · **Logic:** `b22558971483…` · **Policy:** `UNVERIFIED_RULE_POLICY=warn`
**Solvers:** Soufflé 2.5, Clingo 5.8.0

Every number in this document came from a command run against this working tree. Nothing is
inferred from what the code looks like it should do. Commands are named so each claim can be
re-run.

---

## 0. Verification baseline

```
apps/engine $ .venv/bin/python -m pytest -q
1068 passed, 7 skipped, exit 0     (1075 collected)
```

The 7 skips are declared and intentional: 3 benchmarks (`--benchmark-skip` in `pytest.ini`) and
4 Postgres-dialect tests (`POSTGRES_TEST_URL` unset). **The SQLite suite is green; the Postgres
dialect — JSONB, `FOR UPDATE`, timezone-aware timestamps — was not exercised in this run.**

```
apps/engine $ .venv/bin/python scripts/engine_cli.py check
check: OK    (21/21 checks pass)
```

Benchmarks, run explicitly (`pytest tests/benchmarks --benchmark-only`), 10 rounds each:

| Benchmark | Min | Mean | Max |
| --- | --- | --- | --- |
| `test_single_case_solve_time` | 72.78 ms | **73.34 ms** | 74.24 ms |
| `test_rule_store_load_time` | 20.90 ms | 25.33 ms | 56.47 ms |
| `test_proposal_db_write_read` | 8.20 ms | 8.82 ms | 11.15 ms |

Measured end-to-end during this audit: 9-position PADnext audit **40.29 ms** total (29.78 ms in the
solver); case_008 (21 Ziffern in, 14 billed) **74.06 ms**; case_009 **70.41 ms**.

---

## PART 1 — The synthetic benchmark: 9 deliberate errors

Command: `engine_cli.py padnext logic/tests/cases/padnext/00004711_20260726_ADL_000001_padx.xml --json`
Exit code 1 (findings present). Full JSON is reproduced in
[§ Appendix A](#appendix-a--full-json-output-of-the-9-error-file).

### Scorecard

**9 of 9 detected. 7 handled exactly. 2 detected but handled imprecisely. 0 missed. 0 crashes.**

| # | Planted error | Detected | Finding type | Severity | Bucket | Grade |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GOÄ 1, factor 3.5 at Höchstsatz, no `begruendung` | ✅ | `padnext_justification_missing` | error | `confirmed_wrong` | **exact** |
| 2 | GOÄ 301, factor 2.6 **with** justification — must NOT fire | ✅ | *(none)* | — | `confirmed_fine` | **exact** (true negative) |
| 3 | GOÄ 200 charged beside its Zielleistung GOÄ 301 | ✅ | `padnext_blocked_zielleistung` | error | `confirmed_wrong` | **exact** |
| 4 | GOÄ 5 charged alongside mutually exclusive GOÄ 7 | ✅ | `padnext_mutual_exclusion` ×2 | error | both `confirmed_wrong` | ⚠️ **imprecise** — see below |
| 5 | GOÄ 7 `gesamtbetrag` understated by €1.00 | ✅ | `padnext_amount_mismatch` (−1.00 €) | error | `confirmed_wrong` | **exact** |
| 6 | GOÄ 410 `punktzahl` 180, catalog says 200 | ✅ | `padnext_punktzahl_mismatch` | **warning** | **`unconfirmed`** | ⚠️ **under-graded** — see below |
| 7 | GOÄ 99999 not a GOÄ number | ✅ | `padnext_unknown_ziffer` | error | `unconfirmed` | **exact** |
| 8 | GOZ 2020, outside scope | ✅ | `padnext_fee_schedule_out_of_scope` | info | `unconfirmed` | **exact** |
| 9 | GOÄ 3, factor 4.0 above the 3.5 Höchstsatz | ✅ | `padnext_factor_above_maximum` | error | `confirmed_wrong` | **exact** |

Legal citations attached and correct on every applicable finding: § 12 Abs. 3 (1), § 4 Abs. 2a
i.V.m. Allg. Best. Abschnitt C VIII (3), Anmerkungen zu Nrn. 5–8 Abschnitt B I (4), § 5 Abs. 1 (5),
§ 5 Abs. 1, 2 (9).

Item 1 deserves credit specifically: the engine **correctly refused** the framing that 3.5 is "above
the maximum". 3.5 *is* the Abschnitt-B Höchstsatz. It fired § 12 Abs. 3 (missing written reason)
rather than § 5 Abs. 1 (cap exceeded). That is the legally right distinction.

### Money reconciliation — exact

| Field | Value | Check |
| --- | --- | --- |
| `claimed_total_eur` | 251.54 | = sum of all 9 `gesamtbetrag` ✅ |
| `confirmed_fine_eur` | 24.25 | 1 position |
| `confirmed_wrong_eur` | 88.49 | 5 positions |
| `unconfirmed_eur` | 138.80 | 3 positions |
| **buckets sum** | **251.54** | **= `claimed_total_eur` exactly** ✅ |
| `coverage_ratio` | 0.4482 | = (24.25 + 88.49) / 251.54 ✅ |
| `arithmetic_delta_eur` | −1.00 | matches the single planted €1.00 error ✅ |
| `unpriceable_claimed_eur` | 111.99 | = 99.99 (unknown) + 12.00 (GOZ) ✅ |
| `comparable_claimed_eur` + `unpriceable` | 139.55 + 111.99 = 251.54 | ✅ |

Every recomputed line was checked independently against `punkte × faktor × 5.82873 ct`,
`ROUND_HALF_UP` to the cent. All 7 priceable lines match to the cent.

### The two imprecise handlings

**#4 — a mutual exclusion blocks both sides, and both are billed to `confirmed_wrong`.**

This is deliberate (`_rule_endpoints` in `app/padnext/audit.py:322`: *"mutual: either could lose, so
both do"*), and it is defensible as a *finding* — the practice must remove one. It is **not**
defensible as a *money figure*. Isolated probe, a clean GOÄ 5 + GOÄ 7 pair with correct amounts:

```
   1  GOÄ 5  2.3  10.72  !! confirmed_wrong  blocked
   2  GOÄ 7  2.3  21.45  !! confirmed_wrong  blocked
   nachweislich falsch   32.17 EUR  (2 Positionen)
```

The true overcharge is at most **€10.72** (drop the cheaper of the two). The engine reports
**€32.17** — a 3× overstatement. On the 9-error file this happens not to distort the headline,
because position 5 carries an independent arithmetic defect anyway; on a clean pair it does.

> ✅ **Fixed** on `fix/engine-audit-honesty`. Each mutual-exclusion cluster now keeps its most
> valuable member and charges only the rest to `confirmed_wrong`; the same probe now reports
> **€10.72**. Both positions keep their `blocked` verdict and their `padnext_mutual_exclusion`
> finding — only the money moved. The 9-error file is unchanged at €88.49, because position 5 is
> `confirmed_wrong` on its own arithmetic defect regardless of the cluster.

**#6 — a wrong `punktzahl` control field is a warning, and the position lands in `unconfirmed`.**

GOÄ 410 was claimed with `punktzahl` 180 against a catalog value of 200. The engine flags it —
but at `severity: warning`, and the position is bucketed `unconfirmed` with the reason *"Keine
verifizierte Regel bildet diese Ziffer ab."* So €26.81 of a provably-wrong control field is reported
as "no statement possible" rather than as a finding. The *money* was right (the engine recomputed
from its own 200 points and got the claimed 26.81), so nothing was overcharged; the defect is in the
delivered data, not the invoice. Warning severity is arguable. The `unconfirmed` bucket is not —
the engine *did* make a verified statement here, against the versioned catalog.

### One cosmetic data defect

Position 9 (GOÄ 3, factor 4.0) reports `justification_required: false`. At factor 4.0 a written
reason is plainly required. The cause is the `if faktor > band.max / elif faktor > band.threshold`
chain at `app/padnext/audit.py:721-737` — the cap branch short-circuits the justification branch.
No finding was lost (the position carries a `begruendung` and the cap violation fired correctly),
but the field is wrong and it is exposed in the API contract.

> ✅ **Fixed** on `fix/engine-audit-honesty`. The § 12 Abs. 3 flags are set before the branch, so a
> factor above the Höchstsatz reports `justification_required: true`. The *finding* stayed in the
> branch: one error per line, and "above the legal maximum" is the one that decides what happens.

---

## PART 2 — Rule coverage and safety

### 2.1 Exact counts

From the CSVs on disk (`data/rules/*.csv`, counting the `verified` column directly):

| File | Rows | verified | unverified | Source |
| --- | ---: | ---: | ---: | --- |
| `exclusions.csv` | 837 | **0** | **837** | auto-extracted from Anmerkungen prose |
| `exclusions.manual.csv` | 30 | **30** | 0 | `manual_verification` |
| `factor_caps.csv` | 22 | **0** | **22** | auto-extracted |
| `zielleistung.manual.csv` | 3 | **3** | 0 | `manual_verification` |
| `zielleistung.csv` | 0 | 0 | 0 | *(auto-extraction produced nothing)* |
| `specificity.csv` | 2 | **2** | 0 | `manual_verification` |
| `analog_candidates.csv` | 3 | 0 | 3 | `illustrative` |
| `factor_bands.csv` | 16 | **16** | 0 | *(not a constraint rule — catalog bands)* |
| **Total** | **913** | **51** | **862** | |

As `GET /api/v1/rules/coverage` reports it:

```json
{
  "policy_for_unverified_rules": "warn",
  "enforced_rule_count": 35,
  "advisory_rule_count": 862,
  "unverified_rule_count": 859,
  "analog_candidate_count": 3,
  "suppressed_unverified_rule_count": 859,
  "review_verified_rule_count": 0,
  "rejected_rule_count": 0,
  "total_constraint_rule_count": 894,
  "rule_coverage": "partial",
  "verified_share": "30/30"
}
```

**The headline number: 35 of 894 constraint rules are enforced. That is 3.9 %.**

The 35 break down as 30 exclusions + 3 Zielleistung + 2 specificity + **0 factor caps**. The 859
unverified are 837 auto-extracted exclusions + 22 auto-extracted factor caps. The 3 analog
candidates are offers under § 6 Abs. 2, never constraints, and bypass the policy gate entirely
by construction.

> ⚠️ **`verified_share: "30/30"` is a misleading field.** It is computed as
> `verified exclusions / enforced exclusions` (`rule_store.py:552`). Under `warn` only verified
> rules are ever admitted, so this ratio is **1/1 by construction** and can never show a gap. It
> reads like "100 % verified" on a dashboard.
>
> ✅ **Fixed** on `fix/engine-audit-honesty`: it is now `enforced / total constraint rules` —
> **`"35/894"`**. The review dashboard's meter, which parses the fraction, now draws at 3.9 %.

Two other display inconsistencies, same underlying data: `engine_cli.py check` printed
"30 enforced, 859 unverified" while the coverage line beneath printed "35 enforced / 862 advisory";
the `rule_coverage_incomplete` warning on a solve said "30 Ausschlussregeln" while the
`advisory_rules_present` warning said "35 Regeln". All were arithmetically explicable, none agreed
on a denominator.

> ✅ **Fixed** on `fix/engine-audit-honesty`. `RuleStore.enforced_rule_count()` is now the single
> definition of "enforced" and every one of these call sites reads it, phrased as
> "35 verifizierte Regeln von 894". The batch export README's hardcoded "837 der 869
> Ausschlussregeln" — stale, and the wrong denominator — is derived from the store too.

### 2.2 Isolation of unverified rules — proven, not assumed

**Architecturally:** `RuleStore._admit` (`rule_store.py:226`) is the single gate. Under `warn` an
unverified rule is appended to `store.suppressed` and never enters `exclusions` / `zielleistung` /
`specificity` / `factor_caps` — the only four lists the solver, the validator and the audit consume
for enforcement. `suppressed` is read in exactly one place: `_constraint_rules` in `audit.py:349`,
which populates the display-only `advisory_rule_ids` field.

**Empirically.** GOÄ 4 + GOÄ 30 are covered by `excl_auto_30_4` — auto-extracted, `verified=false` —
and by no manual rule. A two-position invoice charging both, run under all three policies:

| `UNVERIFIED_RULE_POLICY` | GOÄ 4 verdict | Findings | `confirmed_wrong_eur` | exit |
| --- | --- | --- | ---: | ---: |
| `warn` (default, and the shipped default) | `chargeable` | none | 0.00 | 0 |
| `ignore` | `chargeable` | none | 0.00 | 0 |
| `block` | **`blocked`** | 1 error | 0.00 | 0 |

Under the default the unverified rule **suppressed nothing, blocked nothing, and produced no
finding**. It only bites when an operator explicitly sets `block`.

**Second proof, wider.** All 9 golden cases were solved under `warn` and again under `block`:

```
case_001 … case_009 : identical status, solver_status, line count and total under both policies
```

No 500, no crash, no changed money, under either policy, on any golden case.

**Two honest qualifications:**

1. **Under `block`, an unverified rule *can* hard-block a position** — that is what the policy is
   for, and the isolation claim holds only because `warn` is the default. It is the default in
   `config.py:162`, `Dockerfile:75`, `apps/engine/.env.example`, `infra/docker/.env.example` and
   both compose files. It is nonetheless a single environment variable away from being off.
2. **Even under `block`, the money buckets stay honest**: the blocked GOÄ 4 stayed in
   `unconfirmed`, not `confirmed_wrong`. An unverified rule cannot manufacture a confirmed finding
   against a practice under any policy. That part is structurally safe.

**Conclusion for Part 2.2: the isolation requirement is met.** An unverified rule under the shipped
configuration cannot hard-block a valid position, cannot produce a 500, and cannot enter the
`confirmed_wrong` bucket. The corollary is the real cost, and it is stated in the next section:
**it cannot catch anything either.**

### 2.3 The corollary — zero factor caps are enforced

`factor_caps_enforced: 0`. All 22 are unverified. Probe:

```
GOÄ 52 billed at factor 2.3 — the Anmerkung says "nur mit dem einfachen Gebührensatz" (1.0)

   1  GOÄ 52  2.3  13.41  ?? unconfirmed  chargeable
   nachweislich falsch    0.00 EUR
   davon belegbar        13.41 EUR  (1 Positionen regelkonform)
```

A 2.3× overcharge on a position the fee schedule caps at 1.0 produces **no finding**. The bucket
(`unconfirmed`) is honest. The CLI's `davon belegbar … regelkonform` line is not — it calls that
position rule-conformant. (This wording is CLI-only; `defensible_total_eur` is not surfaced in the
web UI at all.)

---

## PART 3 — Edge-case stress tests

### 3.1 Analog billing, § 6 Abs. 2 — ✅ passes both halves

`engine_cli.py solve logic/tests/cases/case_009_analog_exclusion/input.json`

**Schwellenwert fallback when justification is absent** — confirmed:

```
  750  f=2.3  basis=schwellenwert  just_req=False  just_present=False  analog=True
       analog_for=optische_kohaerenztomographie  amt=16.09
```

The analog position sits on its Schwellenwert 2.3, not the Höchstsatz, with no justification in
the record — and it emits a `missing_documentation` entry naming 3.5 as reachable *with* a written
reason. Same treatment as any non-analog line. No 500, `status=DRAFT`, `solver_status=SAT`.

**Hard exclusion still blocks the analog candidate** — confirmed:

```json
{"ziffer": "5", "reason": "exclusion", "detail": "analog_candidate_blocked_by:7",
 "blocked_by": "7", "rule_id": "excl_man_5_7",
 "legal_basis": "GOÄ Anmerkungen zu den Nummern 5, 6, 7, 8 (Abschnitt B I)"}
```

The § 6 Abs. 2 ladder (750 → 410 → 5) reached rung 3, hit the **verified** rule `excl_man_5_7`
against the billed GOÄ 7, was blocked with a proof atom, and the ladder fell back to 750 with an
`analog_collision` warning for human review. Total €64.35 / 480 points — exactly the golden
`expected.json`. Warnings present: `analog_collision`, `analogansatz_requires_human_review`,
`rule_coverage_incomplete`. The F-1 regression (500 on analog-meets-exclusion) is gated.

The property suite backs this with two generated properties —
`test_analog_positions_obey_the_same_hard_rules` and
`test_the_analog_ladder_respects_exclusions_against_the_final_invoice`.

### 3.2 GOZ / out-of-scope — ✅ passes

GOZ 2020 in the 9-error file: `verdict: out_of_scope`, `severity: info`, no solver involvement, no
crash. **The GOÄ totals are not corrupted:**

- `recomputed_total_eur` 140.55 excludes the GOZ line entirely
- the €12.00 sits in `unpriceable_claimed_eur` (111.99, with the €99.99 unknown Ziffer)
- `comparable_claimed_eur` (139.55) + `unpriceable_claimed_eur` (111.99) = `claimed_total_eur` (251.54)
- `arithmetic_delta_eur` −1.00 reflects only the one real arithmetic error, not the GOZ line

It is reported, not silently dropped, and it is excluded from every GOÄ arithmetic aggregate.
`_refuse_if_no_position_is_in_the_catalog` additionally refuses a delivery in which *no* position
is known, rather than reporting a whole foreign invoice as 100 % wrong.

### 3.3 § 6a Minderung — ✅ mathematically exact

All 14 lines of case_008 (stationär, 25 %) recomputed independently in `Decimal`, from
`punkte × faktor × 5.82873 ct`, `× 0.75`, `ROUND_HALF_UP` to the cent:

| Ziffer | Punkte | Faktor | engine gross | engine net | independent gross | independent net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 150 | 2.3 | 20.11 | 15.08 | 20.11 | 15.08 |
| 301 | 160 | 2.6 | 24.25 | 18.19 | 24.25 | 18.19 |
| 302 | 250 | 2.3 | 33.52 | 25.14 | 33.52 | 25.14 |
| 3511 | 50 | 1.15 | 3.35 | 2.51 | 3.35 | 2.51 |
| 3550 | 60 | 1.15 | 4.02 | 3.02 | 4.02 | 3.02 |
| 3560 | 40 | 1.15 | 2.68 | 2.01 | 2.68 | 2.01 |
| 3741 | 200 | 1.15 | 13.41 | 10.05 | 13.41 | 10.05 |
| 410 | 200 | 2.3 | 26.81 | 20.11 | 26.81 | 20.11 |
| 424 | 700 | 2.3 | 93.84 | 70.38 | 93.84 | 70.38 |
| 5030 | 360 | 1.8 | 37.77 | 28.33 | 37.77 | 28.33 |
| 5135 | 280 | 1.8 | 29.38 | 22.03 | 29.38 | 22.03 |
| 651 | 253 | 2.3 | 33.92 | 25.44 | 33.92 | 25.44 |
| 659 | 400 | 2.3 | 53.62 | 40.22 | 53.62 | 40.22 |
| 8 | 260 | 3.5 | 53.04 | 39.78 | 53.04 | 39.78 |
| **total** | **3363** | | **429.72** | **322.29** | **429.72** | **322.29** |

- **14/14 lines match to the cent.** Zero divergence.
- `total == sum(rounded lines)` — and `validator.py` check 11 raises `total_mismatch` if it ever
  does not.
- **Matches `logic/tests/golden/case_008_complex_polytrauma.golden.normalized.json` exactly**,
  every line and both totals.
- `rounding_policy: ROUND_HALF_UP`, `rounding_legal_basis: "§ 5 Abs. 1 Satz 4 GOÄ"`,
  `minderung_rate: 0.25`, `punktwert_cent: 5.82873` — all carried in the response.
- Rates: `ambulant 0`, `stationaer 0.25`, `belegarzt 0.15`, legal basis § 6a Abs. 1 GOÄ. Exemption
  list is `['J']` — the Zuschlag nach Buchstabe J, which is the correct and only statutory exemption.
- Rounding *order* was probed three ways on this case — per-line (what the engine does),
  round-the-total-once, and Minderung-on-the-rounded-gross-total. All three give 322.29 here, so
  this case does not discriminate between them. The per-line policy is the legally right one
  (§ 5 Abs. 1 Satz 4 rounds the Gebühr per Leistung), but **no test pins the order**, and a case
  that discriminates would be worth adding.
- Minderung also works in the **audit** path, not just the solve path: the 9-error file rerun with
  `behandlungsart=1` reduced every recomputed line by exactly 25 % (16.32 → 12.24, 24.25 → 18.19,
  6.03 → 4.52), computed from unrounded cents.

---

## PART 4 — The honest truth

### ✅ What is production-ready

- **Money arithmetic.** `punkte × faktor × punktwert`, `ROUND_HALF_UP` to the cent, `Decimal`
  throughout, no float anywhere in the money path. Verified line-by-line against independent
  arithmetic on 14 lines of case_008 and 7 lines of the 9-error file. Zero divergence.
- **§ 6a Minderung.** Exact, correct rates, correct statutory exemption (Buchstabe J), correct
  legal basis strings, works in both the solve and audit paths, matches the golden snapshot.
- **§ 5 Abs. 1, 2 factor bands.** All 16 chapter bands (A–P) verified, plus the § 5 Abs. 4 special
  band for Nr. 437. Both directions caught: above the Höchstsatz (§ 5) and above the Schwellenwert
  without a written reason (§ 12 Abs. 3) — and the engine distinguishes them correctly, which is
  the distinction the synthetic file was built to test.
- **The three-bucket honesty model.** `confirmed_wrong + confirmed_fine + unconfirmed` sums to
  `claimed_total` to the cent, `coverage_ratio` is a share of money not of line count, and
  "we have no rule for this" is structurally separated from "this is wrong". This is the single
  best design decision in the engine and it is what makes the 3.9 % rule coverage survivable.
- **Unverified-rule isolation.** Proven by policy probe and by all 9 golden cases under both
  policies. One admission gate, one code path, no leakage into the enforcement lists, and no
  unverified rule can reach `confirmed_wrong` under any policy.
- **Graceful degradation on unknown input.** Unknown Ziffer, foreign fee schedule, duplicate
  Ziffer, `anzahl > 1` — all handled without a crash, all reported, all excluded from the
  arithmetic aggregates they cannot participate in. The duplicate-Ziffer case explicitly warns
  *"Mengenregeln sind nicht modelliert."*
- **Provenance and reproducibility.** Every response carries `catalog_version` + `catalog_sha256`,
  `rules_version` + `rules_hash` (SHA-256 over the CSVs themselves, so an uncommitted cell edit
  moves it), `logic_version`, solver versions, and a receipt hash. `data/rules/import_report.json`
  and `unparsed_rows.json` record what the importer *could not* parse and why — 256 rows and 187
  rules, each with a reason. Nothing was silently dropped.
- **The § 6 Abs. 2 analog path.** Schwellenwert fallback, exclusion-aware ladder, collision
  reporting, mandatory human-review warning, and a property test over generated inputs.
- **Test discipline.** 1075 tests, 1068 green. Property suite with 5 universally-quantified
  financial invariants at 100 examples each, plus a meta-test that fails if the generated space
  collapses. 9 golden cases with normalized snapshots.
- **The web display layer.** Exactly one function converts a money string to a number, it is
  confined and documented, and it produces CSS widths only. Every euro figure on screen is the
  engine's exact decimal string. The `unconfirmed` disclaimer is centralized so it cannot be
  reworded per screen.
- **Performance.** 73 ms mean per solve, 40 ms for a 9-position audit, on this machine, cold cache.

### ⚠️ What is fragile or needs work

Ordered by what a billing expert will hit first.

1. ~~**Mutual exclusions triple-count the money.**~~ ✅ **Fixed** on `fix/engine-audit-honesty`.
   A clean GOÄ 5 + GOÄ 7 pair reported €32.17 `confirmed_wrong` against a true overcharge of
   €10.72. `mutual_exclusion_survivors` now unions the conflict pairs into clusters, keeps the
   dearest member of each and charges the rest, so the figure is a stated lower bound. The finding
   still lands on every member.
2. **3.9 % rule enforcement, over 0.7 % of the catalog.** 35 of 894 rules, touching 16 of 2192
   Ziffern. The engine's real coverage on the 9-error file was **44.8 %** of claimed money, and
   that file was built out of the Ziffern the rules happen to cover. On an arbitrary invoice it
   will be lower.
3. **Zero factor caps enforced.** All 22 are unverified. GOÄ 52 at 2.3 (statutory cap 1.0) yields
   no finding. These 22 are the cheapest verification win available — each is a single sentence with
   an unambiguous quote.
4. ~~**`verified_share: "30/30"` is structurally incapable of showing a gap.**~~ ✅ **Fixed** on
   `fix/engine-audit-honesty`: now `"35/894"`, and every message quoting an enforced-rule count
   reads it from one `RuleStore.enforced_rule_count()`.
5. **`punktzahl` mismatch is a warning in the `unconfirmed` bucket.** A control field provably
   wrong against the versioned catalog is reported as "no statement possible".
6. ~~**`justification_required` is `false` when the factor exceeds the Höchstsatz.**~~ ✅ **Fixed**
   on `fix/engine-audit-honesty`: the § 12 Abs. 3 flags are set before the § 5 cap branch, so they
   can no longer be short-circuited by it.
7. **CLI wording: `davon belegbar … regelkonform`.** Calls a position rule-conformant when the only
   rule bearing on it is unenforced. Not surfaced in the web UI.
8. **Temporal catalog routing is a mechanism without data.** It works — an edition resolves to its
   own directory, the solver is told the right thing, receipts differ per edition, an unknown
   edition is refused and never falls back. But the four non-current editions
   (`goae_1996`, `goae_2012`, `goae_2026_current`, `goae_neu_draft`) are **synthetic fixtures of
   40–42 Ziffern each, all sharing the same Punktwert 5.82873**. No real historical catalog exists
   in this repo.
9. **Nothing routes by treatment date.** `POST /padnext/audit` uses the process-singleton
   `Pipeline()` (`api/deps.py:33`) with no `catalog_version` parameter. The `<datum>` in the invoice
   is never consulted. An invoice from 2019 is audited against the 2026-07-25 snapshot. Routing is
   reachable only via the `Pipeline(catalog_version=…)` constructor, which no HTTP endpoint calls.
10. **The property suite explores 27 of 2192 Ziffern (1.2 %).** The invariants it proves are strong
    (financial sum, uniqueness, proof presence, factor bounds, determinism) but the reachable space
    is the 33-row bridge table, not the catalog.
11. **The golden corpus does not exercise the unverified rule set at all.** All 9 cases produce
    byte-identical results under `warn` and `block`. That is good evidence for isolation and no
    evidence at all about whether the 859 auto-extracted rules are correct.
12. **No wall-clock regression gate.** The three benchmarks record timings and assert only that the
    work happened (`len(catalog.ziffern) > 2000`, `solver_status == "SAT"`). Nothing fails if a
    solve becomes 10× slower.
13. **Postgres dialect untested in the standard run.** 4 tests skip without `POSTGRES_TEST_URL`.
    Production is Postgres; the green suite is SQLite.
14. **187 extracted rules are parked as "needs review"**, in two categories that the engine cannot
    currently express: 121 `unrecognised_billing_restriction` and 66
    `quantity_or_time_restriction_not_modelled`.
15. **The bundled PADnext XSD is a subset**, not the licensed official schema
    (`padx_adl_v2.12.subset.xsd`). It compiles and validates the fixture, but conformance to the
    real PADneXt 2.12 interface is not established.
16. **The 9-error benchmark file is hand-written**, not produced by a PVS. It is a "hand-written
    subset for exercising the audit, not a schema-validated conforming document" by its own comment.
17. **The 3 analog candidates are marked `source: illustrative`.** They are demonstration data, not
    a curated § 6 Abs. 2 mapping.

### 🚫 What is missing entirely

- **Real PVS data.** Zero invoices from a real practice management system have passed through this
  engine. Everything above was measured on synthetic files we wrote. The delivery-level refusal
  (`PADNEXT_ALLOW_REAL_DATA`, `auftrag/@echtdaten`) is deliberate and correct, but it means the
  parser has never met a real PADneXt container, its `.auf` companion file, real `zusatztext`
  conventions, real Analogziffer notation, or a real PVS's idea of an optional field.
- **Any quantity or time dimension.** 66 extracted rules are parked as
  `quantity_or_time_restriction_not_modelled`. "Im Behandlungsfall nur einmal berechnungsfähig"
  (Nr. 4), "nur einmal im Kalenderjahr" (Nr. 15) — the engine has no `Behandlungsfall`, no calendar,
  and considers a Ziffer at most once per invoice regardless of `anzahl` or how many times it
  appears. It says so in a warning; it cannot check it.
- **Zuschläge (Abschnitt B V, Buchstaben A–J).** Their Anmerkungen appear in
  `rules_needing_review` as `unrecognised_billing_restriction` ("Der Zuschlag nach Buchstabe A ist
  neben den Zuschlägen nach B, C und/oder D nicht berechnungsfähig", "für Krankenhausärzte nicht
  berechnungsfähig"). None of these are modelled. Buchstabe J appears only as a Minderung exemption.
- **Auto-extracted Zielleistung rules: zero.** `zielleistung_rules_auto: 0`. The whole of
  § 4 Abs. 2a — the most litigated provision in the GOÄ — is carried by **3 hand-written rules**,
  all of which say the same thing about the same child Ziffer: `ziel_man_2000_200`,
  `ziel_man_301_200`, `ziel_man_300_200` — the dressing Nr. 200 as a component of Nr. 2000, Nr. 301
  and Nr. 300. **The Zielleistungsprinzip is implemented for exactly one child position.**
- **The 35 enforced rules touch 16 distinct Ziffern out of 2192 — 0.7 %.** In full:
  5, 6, 7, 8, 200, 300, 301, 302, 422, 423, 424, 650, 651, 652, 653, 2000. That is the Nrn. 5–8
  examination cluster (Abschnitt B I), the echo cluster 422–424, the ECG cluster 650–653, the joint
  punctures 300/301/302 with the dressing Nr. 200, and a single surgical position (Nr. 2000). Every
  Ziffer outside that list of 16 can only ever return `unconfirmed`. Radiology (Abschnitt O),
  laboratory (M), anaesthesia and all of surgery except Nr. 2000 have **no verified rule at all**.
- **§ 6 Abs. 1 (Gebührenverzeichnis-fremde Leistungen), § 10 (Auslagen), § 11 (Wegegeld),
  § 12 Abs. 2 (invoice formal requirements beyond the factor justification).** Not implemented.
- **256 unparsed catalog rows.** 153 "row starts with a Ziffer but has no Punktzahl" (Zuschläge and
  multi-line legends), 78 "row too short to classify", 25 orphan annotations. Recorded with reasons,
  not recovered.
- **1 known catalog duplicate**: Ziffer 4114 resolves to both "Renin-Aldosteron-Suppressionstest"
  and "Lithium". One of them is wrong and we do not know which.
- **GOZ.** Out of scope by design and reported as such. Any practice with a dental component gets a
  partial audit.
- **A billing expert's signature on anything.** `review_verified_rule_count: 0`,
  `rejected_rule_count: 0`. The review workflow exists, is tested (23 tests), merges into the
  running engine, and **has never been used**. Every one of the 35 enforced rules was verified by
  us, not by a Sachverständiger. **This is the gap that the meeting this report is preparing for
  exists to close.**

---

## Bottom line

The engine does what it says on its 9-error benchmark: **9 detected, 7 exactly, 0 missed, 0
crashes**, with money that reconciles to the cent and a receipt that pins catalog, rules and logic.
The arithmetic — § 5 pricing, § 6a Minderung, the factor bands — is the strongest part and is
genuinely production-grade. The three-bucket model is what makes the whole thing honest rather than
dangerous.

What it is *not* is a GOÄ rule engine. It is a **GOÄ arithmetic and provenance engine with 35
hand-verified rules bolted on**, which is a different and much smaller claim. 3.9 % rule
enforcement, zero factor caps, zero auto-extracted Zielleistung rules, no quantity dimension, and
no Zuschläge.

Two things had to be fixed before the expert saw it, because both were things they would spot in
the first five minutes and both undermined trust in everything else. **Both are now fixed** on
`fix/engine-audit-honesty`, along with the `justification_required` short-circuit:

1. ✅ **The mutual-exclusion double-count** — €32.17 reported where €10.72 is true. Clusters now
   keep their dearest member; the figure is a lower bound on the overcharge and says so.
2. ✅ **`verified_share: "30/30"`**, which read as 100 % coverage on a 3.9 % engine. Now `"35/894"`,
   from the one definition of "enforced" that every call site shares.
3. ✅ **`justification_required: false` above the Höchstsatz** — an `if/elif` short-circuit.

No money moved anywhere else: the nine frozen golden snapshots changed on exactly two facts — the
`verified_share` string and the `rule_coverage_incomplete` wording — and on no Ziffer, factor,
amount or proof. Everything else in the ⚠️ and 🚫 lists is a known, documented, honestly-reported
gap — which is exactly the shape a proof of concept should have when it walks into that meeting.

---

## Appendix A — full JSON output of the 9-error file

<details>
<summary><code>engine_cli.py padnext 00004711_20260726_ADL_000001_padx.xml --json</code> (exit 1) — regenerated after the three fixes</summary>

```json
{
  "source_name": "00004711_20260726_ADL_000001_padx.xml",
  "nachrichtentyp": "ADL",
  "echtdaten": null,
  "setting": "ambulant",
  "setting_source": "behandlungsart=0 (ambulante Behandlung)",
  "positions": [
    {
      "positionsnr": "1",
      "ziffer": "1",
      "go": "GOÄ",
      "is_analog": false,
      "in_catalog": true,
      "official_text": "Beratung - auch mittels Fernsprecher -",
      "verdict": "chargeable",
      "accepted_as_claimed": false,
      "reason": "",
      "blocked_by": null,
      "proof": [
        "catalog_match",
        "derived_from_act",
        "justification_required",
        "most_specific_candidate",
        "no_unresolved_conflict",
        "not_excluded",
        "not_zielleistung_component"
      ],
      "claimed_faktor": "3.5",
      "claimed_amount_eur": "16.32",
      "recomputed_amount_eur": "16.32",
      "amount_delta_eur": "0.00",
      "punkte": 80,
      "factor_within_band": true,
      "justification_required": true,
      "justification_present": false,
      "legal_basis": "§ 5 Abs. 1, 2 GOÄ",
      "bucket": "confirmed_wrong",
      "bucket_reason": "Verifizierte Prüfung fehlgeschlagen: padnext_justification_missing.",
      "verified_rule_ids": [],
      "advisory_rule_ids": []
    },
    {
      "positionsnr": "2",
      "ziffer": "301",
      "go": "GOÄ",
      "is_analog": false,
      "in_catalog": true,
      "official_text": "Punktion eines Ellenbogen-, Knie- oder Wirbelgelenks",
      "verdict": "chargeable",
      "accepted_as_claimed": true,
      "reason": "",
      "blocked_by": null,
      "proof": [
        "catalog_match",
        "derived_from_act",
        "justification_required",
        "most_specific_candidate",
        "no_unresolved_conflict",
        "not_excluded",
        "not_zielleistung_component"
      ],
      "claimed_faktor": "2.6",
      "claimed_amount_eur": "24.25",
      "recomputed_amount_eur": "24.25",
      "amount_delta_eur": "0.00",
      "punkte": 160,
      "factor_within_band": true,
      "justification_required": true,
      "justification_present": true,
      "legal_basis": "§ 5 Abs. 1, 2 GOÄ",
      "bucket": "confirmed_fine",
      "bucket_reason": "Alle anwendbaren Prüfungen bestanden; geprüft gegen verifizierte Regel(n) ziel_man_301_200.",
      "verified_rule_ids": [
        "ziel_man_301_200"
      ],
      "advisory_rule_ids": []
    },
    {
      "positionsnr": "3",
      "ziffer": "200",
      "go": "GOÄ",
      "is_analog": false,
      "in_catalog": true,
      "official_text": "Verband - ausgenommen Schnell- und Sprühverbände, Augen-, Ohrenklappen oder Dreiecktücher -",
      "verdict": "blocked",
      "accepted_as_claimed": false,
      "reason": "GOÄ 200 ist methodisch notwendiger Bestandteil der Zielleistung GOÄ 301 und daher nicht gesondert berechnungsfähig (§ 4 Abs. 2a GOÄ).",
      "blocked_by": "301",
      "proof": [],
      "claimed_faktor": "2.3",
      "claimed_amount_eur": "6.03",
      "recomputed_amount_eur": "6.03",
      "amount_delta_eur": "0.00",
      "punkte": 45,
      "factor_within_band": true,
      "justification_required": false,
      "justification_present": false,
      "legal_basis": "§ 4 Abs. 2a GOÄ i.V.m. Allgemeine Bestimmung zu Abschnitt C VIII",
      "bucket": "confirmed_wrong",
      "bucket_reason": "Durch die verifizierte Regel '301' nicht berechnungsfähig.",
      "verified_rule_ids": [
        "ziel_man_301_200"
      ],
      "advisory_rule_ids": []
    },
    {
      "positionsnr": "4",
      "ziffer": "5",
      "go": "GOÄ",
      "is_analog": false,
      "in_catalog": true,
      "official_text": "Symptombezogene Untersuchung",
      "verdict": "blocked",
      "accepted_as_claimed": false,
      "reason": "GOÄ 5 und GOÄ 7 schließen sich gegenseitig aus. Die Rechnung enthält beide; nur eine davon ist berechnungsfähig.",
      "blocked_by": "7",
      "proof": [],
      "claimed_faktor": "2.3",
      "claimed_amount_eur": "10.72",
      "recomputed_amount_eur": "10.72",
      "amount_delta_eur": "0.00",
      "punkte": 80,
      "factor_within_band": true,
      "justification_required": false,
      "justification_present": false,
      "legal_basis": "§ 5 Abs. 1, 2 GOÄ",
      "bucket": "confirmed_wrong",
      "bucket_reason": "Durch die verifizierte Regel '7' nicht berechnungsfähig.",
      "verified_rule_ids": [
        "excl_man_5_7",
        "excl_man_7_5"
      ],
      "advisory_rule_ids": [
        "excl_auto_5_7",
        "excl_auto_7_5"
      ]
    },
    {
      "positionsnr": "5",
      "ziffer": "7",
      "go": "GOÄ",
      "is_analog": false,
      "in_catalog": true,
      "official_text": "Vollständige körperliche Untersuchung mindestens eines der folgenden Organsysteme: das gesamte Hautorgan, die Stütz- und Bewegungsorgane, alle Brustorgane, alle Bauchorgane, der gesamte weibliche Genitaltrakt (gegebenenfalls einschließlich Nieren und ableitende Harnwege) - gegebenenfalls einschließlich Dokumentation -",
      "verdict": "blocked",
      "accepted_as_claimed": false,
      "reason": "GOÄ 7 und GOÄ 5 schließen sich gegenseitig aus. Die Rechnung enthält beide; nur eine davon ist berechnungsfähig.",
      "blocked_by": "5",
      "proof": [],
      "claimed_faktor": "2.3",
      "claimed_amount_eur": "20.45",
      "recomputed_amount_eur": "21.45",
      "amount_delta_eur": "-1.00",
      "punkte": 160,
      "factor_within_band": true,
      "justification_required": false,
      "justification_present": false,
      "legal_basis": "§ 5 Abs. 1, 2 GOÄ",
      "bucket": "confirmed_wrong",
      "bucket_reason": "Verifizierte Prüfung fehlgeschlagen: padnext_amount_mismatch.",
      "verified_rule_ids": [
        "excl_man_5_7",
        "excl_man_7_5"
      ],
      "advisory_rule_ids": [
        "excl_auto_5_7",
        "excl_auto_7_5"
      ]
    },
    {
      "positionsnr": "6",
      "ziffer": "410",
      "go": "GOÄ",
      "is_analog": false,
      "in_catalog": true,
      "official_text": "Ultraschalluntersuchung eines Organs",
      "verdict": "chargeable",
      "accepted_as_claimed": true,
      "reason": "",
      "blocked_by": null,
      "proof": [
        "catalog_match",
        "derived_from_act",
        "most_specific_candidate",
        "no_unresolved_conflict",
        "not_excluded",
        "not_zielleistung_component"
      ],
      "claimed_faktor": "2.3",
      "claimed_amount_eur": "26.81",
      "recomputed_amount_eur": "26.81",
      "amount_delta_eur": "0.00",
      "punkte": 200,
      "factor_within_band": true,
      "justification_required": false,
      "justification_present": false,
      "legal_basis": "§ 5 Abs. 1, 2 GOÄ",
      "bucket": "unconfirmed",
      "bucket_reason": "Keine verifizierte Regel bildet diese Ziffer ab. Die Position ist unauffällig, aber unbestätigt — das ist keine Freigabe.",
      "verified_rule_ids": [],
      "advisory_rule_ids": []
    },
    {
      "positionsnr": "7",
      "ziffer": "99999",
      "go": "GOÄ",
      "is_analog": false,
      "in_catalog": false,
      "official_text": "",
      "verdict": "unknown_ziffer",
      "accepted_as_claimed": false,
      "reason": "GOÄ 99999 ist im Katalog goae_official_snapshot_2026-07-25 nicht enthalten.",
      "blocked_by": null,
      "proof": [],
      "claimed_faktor": "1.0",
      "claimed_amount_eur": "99.99",
      "recomputed_amount_eur": null,
      "amount_delta_eur": null,
      "punkte": null,
      "factor_within_band": null,
      "justification_required": false,
      "justification_present": false,
      "legal_basis": "",
      "bucket": "unconfirmed",
      "bucket_reason": "Ziffer ist in unserem Katalog nicht enthalten. Nicht nachrechenbar und nicht beurteilbar — das ist eine Lücke in unseren Daten, kein Nachweis eines Fehlers.",
      "verified_rule_ids": [],
      "advisory_rule_ids": []
    },
    {
      "positionsnr": "8",
      "ziffer": "2020",
      "go": "GOZ",
      "is_analog": false,
      "in_catalog": false,
      "official_text": "",
      "verdict": "out_of_scope",
      "accepted_as_claimed": false,
      "reason": "Gebührenordnung 'GOZ' wird von diesem Proof of Concept nicht geprüft.",
      "blocked_by": null,
      "proof": [],
      "claimed_faktor": "2.3",
      "claimed_amount_eur": "12.00",
      "recomputed_amount_eur": null,
      "amount_delta_eur": null,
      "punkte": null,
      "factor_within_band": null,
      "justification_required": false,
      "justification_present": false,
      "legal_basis": "",
      "bucket": "unconfirmed",
      "bucket_reason": "Gebührenordnung 'GOZ' wird nicht geprüft — keine Aussage möglich, kein Befund.",
      "verified_rule_ids": [],
      "advisory_rule_ids": []
    },
    {
      "positionsnr": "9",
      "ziffer": "3",
      "go": "GOÄ",
      "is_analog": false,
      "in_catalog": true,
      "official_text": "Eingehende, das gewöhnliche Maß übersteigende Beratung - auch mittels Fernsprecher -",
      "verdict": "chargeable",
      "accepted_as_claimed": false,
      "reason": "",
      "blocked_by": null,
      "proof": [
        "catalog_match",
        "derived_from_act",
        "factor_above_hoechstsatz",
        "justification_required",
        "most_specific_candidate",
        "no_unresolved_conflict",
        "not_excluded",
        "not_zielleistung_component"
      ],
      "claimed_faktor": "4.0",
      "claimed_amount_eur": "34.97",
      "recomputed_amount_eur": "34.97",
      "amount_delta_eur": "0.00",
      "punkte": 150,
      "factor_within_band": false,
      "justification_required": true,
      "justification_present": true,
      "legal_basis": "§ 5 Abs. 1, 2 GOÄ",
      "bucket": "confirmed_wrong",
      "bucket_reason": "Verifizierte Prüfung fehlgeschlagen: padnext_factor_above_maximum.",
      "verified_rule_ids": [],
      "advisory_rule_ids": []
    }
  ],
  "findings": [
    {
      "type": "padnext_echtdaten_unknown",
      "severity": "info",
      "message": "Ohne Auftragsdatei ist nicht erkennbar, ob es sich um Echt- oder Testdaten handelt (auftrag/@echtdaten). Es wurde von Testdaten ausgegangen.",
      "positionsnr": null,
      "ziffer": null,
      "legal_basis": "",
      "rule_id": "",
      "claimed": null,
      "recomputed": null
    },
    {
      "type": "padnext_justification_missing",
      "severity": "error",
      "message": "Faktor 3.5 liegt über dem Schwellenwert 2.3. § 12 Abs. 3 GOÄ verlangt eine schriftliche Begründung; das Feld 'begruendung' ist leer.",
      "positionsnr": "1",
      "ziffer": "1",
      "legal_basis": "§ 12 Abs. 3 GOÄ",
      "rule_id": "",
      "claimed": "3.5",
      "recomputed": null
    },
    {
      "type": "padnext_blocked_zielleistung",
      "severity": "error",
      "message": "GOÄ 200 ist neben GOÄ 301 nicht berechnungsfähig: GOÄ 200 ist methodisch notwendiger Bestandteil der Zielleistung GOÄ 301 und daher nicht gesondert berechnungsfähig (§ 4 Abs. 2a GOÄ).",
      "positionsnr": "3",
      "ziffer": "200",
      "legal_basis": "§ 4 Abs. 2a GOÄ i.V.m. Allgemeine Bestimmung zu Abschnitt C VIII",
      "rule_id": "ziel_man_301_200",
      "claimed": null,
      "recomputed": null
    },
    {
      "type": "padnext_mutual_exclusion",
      "severity": "error",
      "message": "GOÄ 5 und GOÄ 7 schließen sich gegenseitig aus. Die Rechnung enthält beide; nur eine davon ist berechnungsfähig.",
      "positionsnr": "4",
      "ziffer": "5",
      "legal_basis": "GOÄ Anmerkungen zu den Nummern 5, 6, 7, 8 (Abschnitt B I)",
      "rule_id": "excl_man_5_7",
      "claimed": null,
      "recomputed": null
    },
    {
      "type": "padnext_mutual_exclusion",
      "severity": "error",
      "message": "GOÄ 7 und GOÄ 5 schließen sich gegenseitig aus. Die Rechnung enthält beide; nur eine davon ist berechnungsfähig.",
      "positionsnr": "5",
      "ziffer": "7",
      "legal_basis": "GOÄ Anmerkungen zu den Nummern 5, 6, 7, 8 (Abschnitt B I)",
      "rule_id": "excl_man_5_7",
      "claimed": null,
      "recomputed": null
    },
    {
      "type": "padnext_amount_mismatch",
      "severity": "error",
      "message": "gesamtbetrag 20.45 € weicht von der Nachrechnung 21.45 € ab (-1.00 €). Grundlage: 160 Punkte × Faktor 2.3 × 5.82873 ct.",
      "positionsnr": "5",
      "ziffer": "7",
      "legal_basis": "§ 5 Abs. 1 GOÄ",
      "rule_id": "",
      "claimed": "20.45 €",
      "recomputed": "21.45 €"
    },
    {
      "type": "padnext_punktzahl_mismatch",
      "severity": "warning",
      "message": "punktzahl 180 weicht von der Katalog-Punktzahl 200 für GOÄ 410 ab.",
      "positionsnr": "6",
      "ziffer": "410",
      "legal_basis": "",
      "rule_id": "",
      "claimed": "180",
      "recomputed": "200"
    },
    {
      "type": "padnext_unknown_ziffer",
      "severity": "error",
      "message": "GOÄ 99999 ist im Katalog goae_official_snapshot_2026-07-25 nicht enthalten.",
      "positionsnr": "7",
      "ziffer": "99999",
      "legal_basis": "",
      "rule_id": "",
      "claimed": null,
      "recomputed": null
    },
    {
      "type": "padnext_fee_schedule_out_of_scope",
      "severity": "info",
      "message": "Gebührenordnung 'GOZ' wird von diesem Proof of Concept nicht geprüft.",
      "positionsnr": "8",
      "ziffer": "2020",
      "legal_basis": "",
      "rule_id": "",
      "claimed": null,
      "recomputed": null
    },
    {
      "type": "padnext_factor_above_maximum",
      "severity": "error",
      "message": "Faktor 4.0 überschreitet den Höchstsatz 3.5 für GOÄ 3.",
      "positionsnr": "9",
      "ziffer": "3",
      "legal_basis": "§ 5 Abs. 1, 2 GOÄ",
      "rule_id": "",
      "claimed": "4.0",
      "recomputed": "max 3.5"
    },
    {
      "type": "advisory_rules_present",
      "severity": "warning",
      "message": "35 verifizierte Regeln von 894 werden durchgesetzt; 862 Regeln sind nur beratend: 859 nicht verifizierte Regeln, die unter Policy 'warn' NICHT blockieren, und 3 Analogkandidaten (§ 6 Abs. 2 GOÄ), die als Angebot und nie als Einschränkung wirken. Das Ergebnis darf nicht als vollständige Regelprüfung gelesen werden.",
      "positionsnr": null,
      "ziffer": null,
      "legal_basis": "",
      "rule_id": "",
      "claimed": null,
      "recomputed": null
    }
  ],
  "claimed_total_eur": "251.54",
  "recomputed_total_eur": "140.55",
  "comparable_claimed_eur": "139.55",
  "arithmetic_delta_eur": "-1.00",
  "defensible_total_eur": "51.06",
  "unpriceable_claimed_eur": "111.99",
  "confirmed_fine_eur": "24.25",
  "confirmed_wrong_eur": "88.49",
  "unconfirmed_eur": "138.80",
  "coverage_ratio": 0.4481990935835255,
  "catalog_version": "goae_official_snapshot_2026-07-25",
  "catalog_sha256": "244b403386d39052115ff5853e8b1e0b65714082241fdc03babdb283def9e845",
  "rules_version": "auto_extracted_2026-07-25",
  "logic_version": "b2255897148306c8790408a156f5e9e2ee558919ec2504e96d32401dd03c2eff",
  "enforced_rule_count": 35,
  "advisory_rule_count": 862,
  "suppressed_unverified_rule_count": 859,
  "rule_coverage_detail": {
    "policy_for_unverified_rules": "warn",
    "enforced_rule_count": 35,
    "advisory_rule_count": 862,
    "unverified_rule_count": 859,
    "analog_candidate_count": 3,
    "suppressed_unverified_rule_count": 859,
    "review_verified_rule_count": 0,
    "rejected_rule_count": 0,
    "total_constraint_rule_count": 894,
    "rule_coverage": "partial",
    "rules_version": "auto_extracted_2026-07-25",
    "verified_share": "35/894"
  },
  "solve_time_ms": 27.67,
  "total_time_ms": 38.79,
  "receipt_hash": "cb85fdeabb29ce25e4ccf68bd853dbf61b5329d355984802763b645f9de7d05f"
}
```

</details>
