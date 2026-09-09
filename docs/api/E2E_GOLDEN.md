# The golden suite and the partner-API end-to-end

Two things have to be true before anybody pays for this: the **API lifecycle** works — sign in, mint
a key, audit with it, be refused without it, be metered, revoke — and the **engine is right** about
invoices whose answers are known independently. This page is how both are checked, and what to do
when one of them stops holding.

| | Where | What it proves | How to run it |
|---|---|---|---|
| Golden cases | [`apps/engine/tests/golden/`](../../apps/engine/tests/golden/) | the engine's arithmetic and rule citations, against expectations computed from the fee schedule | `pytest tests/test_golden_cases.py` |
| Partner e2e | [`scripts/e2e_partner_api.py`](../../scripts/e2e_partner_api.py) | the paid path, over real HTTP, with a real key | `.venv/bin/python scripts/e2e_partner_api.py` |

They share one file each way round: the script reads the same `expected.json` the tests do, and both
compare through `oracle.compare_report`. Two implementations of "does this match" would eventually
disagree, and the one that ran in CI would win by accident rather than on the merits.

---

## 1. Running it

### The golden cases, in process

```bash
cd apps/engine
.venv/bin/python -m pytest tests/test_golden_cases.py -q
```

No stack, no database, no network: `conftest.py` forces in-memory SQLite and the tests drive the
real app through `TestClient`.

### The partner end-to-end, against the live stack

Start a stack. Either compose file works; the dev one is what the run below used:

```bash
docker compose -f infra/docker/docker-compose.dev.yml up --build -d
```

Then, from the repository root:

```bash
.venv/bin/python scripts/e2e_partner_api.py                    # 37 checks, exits non-zero on FAIL
.venv/bin/python scripts/e2e_partner_api.py --detect           # print which stack answered, exit
.venv/bin/python scripts/e2e_partner_api.py --keep-practices   # recommended for repeated local runs
.venv/bin/python scripts/e2e_partner_api.py --skip-tenancy     # skip step 10
```

`.venv` at the root is a symlink to `apps/engine/.venv`; it is not committed, because it points
inside a gitignored directory. Make it once, or use the long form:

```bash
ln -s apps/engine/.venv .venv
# or, equivalently, with no symlink at all:
apps/engine/.venv/bin/python scripts/e2e_partner_api.py
```

The script is standard-library-only — `urllib`, `http.cookiejar`, `zipfile` — so **any** Python 3.9+
interpreter runs it, including one that has never installed the engine's requirements. `python3
scripts/e2e_partner_api.py` works too. The venv is named above only because it is the interpreter a
developer in this repository already has.

Two environment variables move the targets, and nothing else is configuration:

```bash
E2E_WEB_BASE_URL=http://localhost:3000     # the Next.js tier — auth and the key-minting proxy
E2E_ENGINE_BASE_URL=http://localhost:8000  # the engine — the partner API itself
E2E_PASSWORD=…                             # the test accounts' password, if not the derived default
```

### What it creates, and what it removes

Two deterministic practices, `e2e-partner-a@e2e.azmoth.test` and `…-b@…`, created through
`POST /api/auth/sign-up/email` and named through `POST /api/onboarding` — the product's own routes.
Nothing is inserted into the database by hand, which is what makes step 2's assertion mean anything.

At exit, whatever the outcome:

* **every key the run minted is revoked**, through `DELETE /api/engine/settings/api-keys/{key_id}`;
* **an organisation is deleted only if this run created it**, through Better Auth's own
  `organization/delete`. A reused one is left alone: deleting somebody's practice because a test
  borrowed it would be worse than leaving a row behind.

What is deliberately kept, and printed on the closing line:

* the two `user` rows — Better Auth exposes no self-delete on this deployment, and the next run
  signs into them;
* the revoked `api_keys` rows — kept by design, because "this key was live from March to July" is a
  question a billing dispute asks
  ([`models.py:ApiKeyRecord`](../../apps/engine/app/db/models.py)).

**Prefer `--keep-practices` for repeated local runs.** Deleting the organisation makes the next run
re-onboard, and `practices` rows are keyed on the organisation id, so a new one is written each time
and no endpoint can remove it. The default (delete what this run created) is there because the brief
asked for it; the flag is there because the default litters.

If the deployment sets `SIGNUP_ALLOWLIST`, add `@e2e.azmoth.test` to it. An unset list is permissive
in development and shut in production — [`auth-allowlist.ts`](../../apps/web/lib/auth-allowlist.ts)
explains why that asymmetry is the design and not an oversight.

---

## 2. Where the expected numbers come from

**Never from the engine.** An expectation produced by running the engine and writing down what came
out cannot fail when the engine is wrong; it can only fail when the engine *changes*. So
[`tests/golden/oracle.py`](../../apps/engine/tests/golden/oracle.py) imports nothing from `app` —
a test asserts that, in a subprocess — and re-derives every figure from:

* `data/catalogs/goae_current/goae.official.json` — `punkte`, `punktwert_cent` (5.82873 ct),
  `factor_bands`, `category`, `status`;
* `data/rules/exclusions.csv`, `factor_caps.csv`, `specificity.csv`, `zielleistung*.csv` — rule ids
  and legal bases, **`verified=true` rows only**;
* § 5 Abs. 1 GOÄ's own arithmetic, in `Decimal`:

```
Betrag = ROUND_HALF_UP(punkte × faktor × punktwert_cent ÷ 100, cent)
```

There is no `float` anywhere in the money path. `coverage_ratio` is the single exception and the
contract already says why: it is a display ratio, never money, never an input to an arithmetic check.

`test_expectations_are_not_stale` re-runs the oracle on every pytest invocation and fails if a
committed `expected.json` no longer matches the data. That is what keeps "computed independently" a
maintained property rather than a claim about one afternoon: a catalog bump that moves a `punkte`
value, or a rule review that flips a `verified` column, fails there with the instruction to
regenerate —

```bash
apps/engine/.venv/bin/python apps/engine/tests/golden/oracle.py --write   # rewrite
apps/engine/.venv/bin/python apps/engine/tests/golden/oracle.py           # check only
```

— rather than leaving a golden file that describes a fee schedule nobody bills under any more. Read
that diff. **A changed euro figure is a changed fee schedule, not a formatting nit.**

---

## 3. The five cases

Each directory holds `delivery_padx.xml` and `expected.json`. Every delivery declares
`echtdaten="0"`; case E is the one that declares nothing, on purpose.

### Case A — the known answer

[`case_a_known_answer/`](../../apps/engine/tests/golden/case_a_known_answer/) · byte-identical to
`padnext_example/00123456_20240315_ADL_000001_padx.xml`, which a test asserts so the two cannot
drift. Five positions, one invoice `2024-0847`:

| Pos | Ziffer | Punkte | Faktor | Betrag |
|---:|---:|---:|---:|---:|
| 1 | 1 | 80 | 2.3 | 10.72 € |
| 2 | 5 | 80 | 2.3 | 10.72 € |
| 3 | 651 | 253 | 1.8 | 26.54 € |
| 4 | 3550 | 60 | 1.15 | 4.02 € |
| 5 | 410 | 200 | 2.3 | 26.81 € |
| | | | **claimed** | **78.81 €** |

Expected: nachgerechnet **78.81 €**, Rechendifferenz **0.00 €**, and the three buckets
**0.00 / 0.00 / 78.81 €** — nachweislich falsch, bestätigt korrekt, unbestätigt. Findings: exactly
`[advisory_rules_present]`. Every position `chargeable` with *"Keine verifizierte Regel bildet diese
Ziffer ab"*, because no `verified=true` rule in `exclusions.csv` names two of `{1, 5, 651, 3550, 410}`
— checked in the oracle, not assumed.

This is the case the amber bucket exists to be able to state: **nothing is wrong with this invoice,
and the engine still cannot call it correct.** `coverage_ratio` is `0.0` and that is the honest
answer, not a bug.

`receipt_hash` is asserted twice over: equality of two runs is the property, and the prefix
`f7edf9fc95d95429` is a canary that says *which* engine the 78.81 € belongs to. If the prefix moves,
something in the catalog, the rule tables, the logic, the solver, the policy or the response shape
changed — [`services/receipt.py`](../../apps/engine/app/services/receipt.py) is explicit that a
receipt is comparable within an engine version and not across one. Read that file before editing the
expectation.

### Case B — a verified exclusion fires

[`case_b_verified_exclusion/`](../../apps/engine/tests/golden/case_b_verified_exclusion/) ·
`excl_auto_34_4`, `verified=true`, `direction=one_way`, basis *GOÄ Anmerkung zu Nummer 4*: charging
GOÄ 34 makes GOÄ 4 not chargeable beside it. The pair was chosen because **no row in the table names
the reverse direction** — `logic/datalog/goae_rules.dl` LAYER 3 requires `!exclusion(_, B, A, _)`
with no `verified` filter before it will decide a direction, so a pair that is one-way only among the
*verified* rows would not fire.

| Ziffer | Punkte | Faktor | Betrag | Verdict | Bucket |
|---:|---:|---:|---:|---|---|
| 34 | 300 | 2.3 | 40.22 € | `chargeable` | `confirmed_fine` |
| 4 | 220 | 2.3 | 29.49 € | `blocked` by 34 | `confirmed_wrong` |

Expected: nachweislich falsch **29.49 €**, bestätigt korrekt **40.22 €**, unbestätigt **0.00 €**, and
a `padnext_blocked_exclusion` finding on position 2 carrying `rule_id: "excl_auto_34_4"`. The line
that did the excluding is **untouched** — asserted, because a rule that convicted both sides would be
the overclaim the buckets exist to prevent.

GOÄ 34 lands in `confirmed_fine` and not `unconfirmed` because a verified rule is credited to *both*
of its endpoints: the solver evaluated it against both and each side got an answer.

### Case C — a verified factor cap fires, and the boundary holds

[`case_c_verified_factor_cap/`](../../apps/engine/tests/golden/case_c_verified_factor_cap/) ·
`cap_auto_440`, `verified=true`, `max_factor` **1.0**, basis *GOÄ Allgemeine Bestimmung*. Two invoices
in one delivery, both charging GOÄ 440 (400 Punkte):

| Invoice | Pos | Faktor | Betrag | Bucket |
|---|---:|---:|---:|---|
| `GOLDEN-C-0001` | 1 | 2.3 | 53.62 € | `confirmed_wrong` — `padnext_factor_above_maximum`, `rule_id: cap_auto_440` |
| `GOLDEN-C-0002` | 2 | 1.0 | 23.31 € | `confirmed_fine` |

2.3 is deliberate on three counts: above the 1.0 cap; *at* rather than above the Abschnitt C
Schwellenwert of 2.3, so § 12 Abs. 3 GOÄ does not additionally demand a `begruendung` and the line
carries exactly one defect; and below the § 5 Höchstsatz of 3.5, so the **cap** is the ceiling that
was broken and `cap_auto_440` is the rule the finding must cite. (When both are broken the band
wins, and the message names 3.5 — which would be a true sentence about a different rule.)

Two things about this fixture are load-bearing and would silently break the case if edited:

* **The at-cap invoice is second.** `audit.py` folds a repeated Ziffer with *last one wins* before
  grounding, so the Ziffer-keyed solver relation sees 1.0 and the per-position cap check is what
  convicts position 1 alone. Reverse the order and the solver's own `invalid_factor_cap` marks GOÄ
  440 wholesale.
* **The at-cap line is numbered `2`, not `1`.** See §5.

A `padnext_duplicate_ziffer` warning is expected and correct: the rule evaluation is Ziffer-keyed, so
it cannot see the second line, and a reader is entitled to know the check was coarser than the
invoice. It is a `warning`, so it moves no euro into `confirmed_wrong`.

### Case D — arithmetic mismatch

[`case_d_arithmetic_mismatch/`](../../apps/engine/tests/golden/case_d_arithmetic_mismatch/) · case A
with position 1's `gesamtbetrag` inflated from 10.72 € to 20.72 €, and nothing else touched.

Expected: a `padnext_amount_mismatch` finding **naming position 1** (GOÄ 1), claimed **88.81 €**,
nachgerechnet **78.81 €**, Rechendifferenz **10.00 €**, and buckets **20.72 / 0.00 / 68.09 €**. The
whole claimed amount of the bad line goes to `confirmed_wrong`, not the 10.00 € delta: the line is
not chargeable *as claimed*, and the engine will not invent a corrected invoice.

There is no tolerance on this comparison. § 5 Abs. 1 Satz 4 GOÄ rounds half-up to the cent, and a
cent is a cent.

> **One reading in the brief does not survive contact with the contract.** "nicht nachrechenbar
> reflects it" does not hold, and should not: the report's *nicht nachrechenbar* is
> `unpriceable_claimed_eur` ([`report-provenance.tsx`](../../apps/web/components/padnext/report-provenance.tsx)),
> which counts euros on positions that could not be priced **at all** — an unknown Ziffer, another
> fee schedule. GOÄ 1 *was* priced; its claimed figure simply disagrees with the price. Those are
> different statements and the contract keeps them apart deliberately, so the expectation asserts
> `unpriceable_claimed_eur == 0.00` and reads the mismatch off `arithmetic_delta_eur` and the
> `confirmed_wrong` bucket, which is where it belongs. Not an engine defect — a field-name collision
> between the brief and the report.

### Case E — the gate

[`case_e_echtdaten_gate/`](../../apps/engine/tests/golden/case_e_echtdaten_gate/) · case A with
`@echtdaten` removed from the `<rechnungen>` start tag. Absent is **unknown**, and
[`schemas/padnext.py`](../../apps/engine/app/schemas/padnext.py) is explicit that unknown must never
be read as "probably test data".

Expected: **HTTP 422**, `error_code` **`ECHTDATEN_UNDECLARED`**, with the batched list present under
`details.errors` — at least one entry with `code: "echtdaten_undeclared"`, `blocking: true`, and a
copyable `command` naming `anonymize_padnext.py`. Then the real
[`scripts/anonymize_padnext.py`](../../scripts/anonymize_padnext.py) is run on it as a **subprocess**,
exactly as a practice would on its own machine, and the output re-submitted: **200**, and case A's
report field for field.

> **A second reading in the brief is off by one envelope field.** The brief expects
> `422 echtdaten_undeclared`; the envelope's `error_code` is `ECHTDATEN_UNDECLARED` — its own code,
> not `PADNEXT_SCHEMA_VIOLATION`. Both are 422 and both carry `echtdaten_undeclared` in
> `details.errors`; the difference matters only to a client switching on `error_code`, which the
> contract says is the stable field. The expectation asserts the code the engine actually publishes,
> and `details.violations` is absent for this refusal because no *schema* rule was broken — the
> framing is fine, the declaration is missing.

Note also that `anonymize_padnext.py` stamps `echtdaten="false"`, not `"0"`. Both parse as "test
data", the receipt is unchanged, and case A's report comes back identical.

---

## 4. The e2e run, step by step

| Step | What it does | Asserted |
|---:|---|---|
| 1 | `POST /api/auth/sign-in/email`, or sign-up + `POST /api/onboarding` | a session with an `activeOrganizationId` |
| 2 | `POST /api/engine/settings/api-keys` | `201`, `azm_live_…`, the org from the session; the listing carries no secret; `api_keys.key_hash == sha256(token)` |
| 3 | case A with the key | `200`, the known answer, all five berechnungsfähig, the three `X-Quota-*` headers |
| 4 | the same request with no key, then a well-formed unknown one | `401 API_KEY_REQUIRED`, `401 API_KEY_INVALID` |
| 5 | case A again | an identical `receipt_hash`, and the canary prefix |
| 6 | cases B and C | the buckets above, and a finding citing `excl_auto_34_4` / `cap_auto_440` |
| 6b | the `positionsnr` collision reproducer | **not a numbered step** — re-checks the fix described in §5. `PASS` since the fix landed; would report a `BUG` row again if the attribution regressed |
| 7 | case E raw, then anonymised | `422 ECHTDATEN_UNDECLARED` with batched errors; `200` and case A's report |
| 8 | three audits and four refused-auth calls | `by_endpoint["/api/v1/audit/single"]` **+3**; `failed_requests` unchanged; `invoices_processed` **+3**; `api_usage_logs` **+3** rows |
| 9 | `DELETE /api/engine/settings/api-keys/{key_id}` | `200`; the same key immediately `401`; the row survives with `revoked_at` |
| 10 | a second practice, a real bulk job, org A asking for it | `404 AUDIT_JOB_NOT_FOUND` — and absent from org A's listing |

**The plaintext key is printed nowhere after step 2's own assertion.** Step 2 prints the `key_id` —
the public half, which is what a log line names — and every later step refers to the key by that. A
script that echoed a live credential into a terminal, a CI log or a scrollback buffer would be a
worse leak than the one it is testing for.

### Two notes on how the checks are built

**Step 8 counts per endpoint, not in total.** A total would have to account for the usage and billing
reads the step itself makes, which is arithmetic that passes for the wrong reason the moment one more
call is added above it. `by_endpoint["/api/v1/audit/single"]` moves only when an audit is attributed,
which is exactly the claim. The window's ends are both `GET /settings/usage` calls, which flush the
meter's buffer before reading, so there is no lag inside it. A refused-auth call adds nothing because
it resolves no key, so the row has no tenant to attribute and is
[never written](../../apps/engine/app/db/models.py).

**Step 10 needs a job, not a report.** `/audit/single` is synchronous and stores nothing a second
caller could ask for, so the tenancy assertion goes through `/audit/bulk`, which has a `job_id` in
it. The job is polled to `COMPLETED` before the cross-tenant read, so a `404` cannot be "not written
yet" wearing the costume of "not yours". A second organisation is two requests through the product,
so this is asserted rather than skipped — `--skip-tenancy` exists for a stack where sign-up is shut.

**A `BUG` row is not a `FAIL`.** Step 6b re-checks the defect §5 describes, so the one command that
proves the paid path also says whether that defect is still live. A `BUG` row does not change the
exit status — a reproducible regression here is worth a loud row, not a red build that looks
identical to every other kind of failure.

### Two optional database reads

Steps 2 and 8 additionally *read* Postgres through `docker compose exec -T postgres psql`, because no
endpoint can answer them and the alternative is to assert nothing: that `api_keys.key_hash` is
SHA-256 of the token that was handed out, and that `api_usage_logs` grew by exactly three rows. Both
degrade to a printed `SKIP` with a reason on a stack Docker cannot reach. **Neither is a write.**

---

## 5. FIXED — findings were attributed by `positionsnr`, which is not unique across a delivery

**Status:** fixed. `tests/golden/bug_positionsnr_collision/` is a regular case now; the reproducer
test carries no `xfail`.
**Reproducer:** [`tests/golden/bug_positionsnr_collision/`](../../apps/engine/tests/golden/bug_positionsnr_collision/) ·
`test_findings_are_attributed_per_delivery_and_not_per_positionsnr`
**Found by:** building case C. The first version of that fixture numbered both lines `1`.

`app/padnext/audit.py` used to build `errors_per_position` and `verified_defects_per_position` keyed
on `positionsnr` alone. PADnext scopes that number to an `<abrechnungsfall>`, not to a delivery, so
two invoices each numbering their line `"1"` — which is normal and valid — **shared one attribution
slot**.

The reproducer is case C's delivery with the second line renumbered back to `1`. Before the fix,
observed against the live stack:

```
GOLDEN-C-0001  pos 1  GOÄ 440 @ 2.3  53.62 €   confirmed_wrong  ← correct, breaks cap_auto_440
GOLDEN-C-0002  pos 1  GOÄ 440 @ 1.0  23.31 €   confirmed_wrong  ← WRONG, it is exactly at the cap
                                                bucket_reason: "Verifizierte Prüfung fehlgeschlagen:
                                                padnext_factor_above_maximum."
confirmed_fine 0.00 €   confirmed_wrong 76.93 €   unconfirmed 0.00 €
```

Expected, and what the fixed engine now reports, is `confirmed_fine 23.31 € / confirmed_wrong
53.62 €`. Before the fix, only **one** `padnext_factor_above_maximum` finding was emitted, for
`positionsnr "1"`, with no way for a reader to tell which of the two lines it convicted.

**Why it mattered rather than being a curiosity.** `confirmed_wrong_eur` is the one figure
[`PARTNER_API.md`](./PARTNER_API.md) §2 permits to be presented as exposure. The bug moved compliant
euros into it, in a shape that got *more* likely as deliveries got bigger: a billing centre's export
is many `<abrechnungsfall>` elements, and per-case numbering restarting at 1 is the norm, not an edge
case. The same map drove `accepted_as_claimed`, so `defensible_total_eur` was wrong with it.

**The fix:** a delivery-unique position key, exactly as anticipated below. `id(row)` is what
`blocking_rule_id` and `mutual_exclusion_survivors` already keyed on for this same reason, so the two
remaining maps (`errors_per_row`, `verified_defects_per_row` — renamed from the `*_per_position` pair
above) moved to it too, with **no contract change**: `PadnextFinding.positionsnr` is unchanged, and
so is the OpenAPI schema. Each position's findings are now folded into its row's counters inline, in
the same loop iteration that creates the row, rather than re-derived afterwards from a flat list
matched by the ambiguous string. See the comment above `errors_per_row` in
[`audit.py`](../../apps/engine/app/padnext/audit.py) for the mechanics.

The old `xfail` was **strict**, so the fix is what made
`test_findings_are_attributed_per_delivery_and_not_per_positionsnr` start passing — at which point,
per that test's own rule, the marker came off rather than the test starting to fail for passing
unexpectedly.

---

## 5b. FIXED — a suppression rule fired across a patient/invoice boundary, and across service dates

**Status:** fixed. `tests/golden/case_f_cross_patient_boundary/` and
`tests/golden/case_g_cross_date_same_patient/` are regular cases now.
**Reproducers:**
[`case_f_cross_patient_boundary/`](../../apps/engine/tests/golden/case_f_cross_patient_boundary/) ·
`test_case_f_an_exclusion_does_not_cross_a_patient_boundary`,
[`case_g_cross_date_same_patient/`](../../apps/engine/tests/golden/case_g_cross_date_same_patient/) ·
`test_case_g_an_exclusion_across_two_service_dates_is_advisory_not_confirmed_wrong`.
**Found by:** auditing a multi-invoice ADL delivery and noticing a verified exclusion convict a
Ziffer that never shared an `<abrechnungsfall>` with the Ziffer that supposedly excluded it.

`PadnextDelivery.positions()` flattens every invoice and every billing case into one list, and
`audit_delivery` used to ground that whole list in a single Soufflé run. `logic/datalog/goae_rules.dl`
has no dimension for patient, invoice or date — every relation is keyed by Ziffer alone — so a
verified exclusion fired the moment both of its Ziffern appeared *anywhere* in the delivery, whatever
invoice, case or date each was actually claimed on. Two distinct bugs came out of the one root cause:

* **Case F, the patient/invoice boundary.** Patient A's invoice charges GOÄ 34; patient B's, on a
  separate `<abrechnungsfall>`, charges GOÄ 4. `excl_auto_34_4` (GOÄ 4 not chargeable beside GOÄ 34)
  fired against patient B regardless, and GOÄ 4 was reported `blocked` → `confirmed_wrong` — a
  refund exposure invented from a service patient B never claimed. A real ADL delivery is many
  `<abrechnungsfall>` elements; the false positives scale with every pair of invoices, not with the
  delivery, so the error count grows quadratically with delivery size.
* **Case G, the service date.** One patient, one `<abrechnungsfall>`, GOÄ 34 and GOÄ 4 claimed 5.5
  months apart. "Neben" (alongside) in the GOÄ Anmerkung is a clinical term — the two services
  rendered at the same encounter — not an invoice-level one, and the rules engine matched on Ziffer
  alone with no notion of when either was claimed.

**The fix, in two parts:**

1. `audit_delivery` now runs Soufflé once per `<abrechnungsfall>` instead of once per delivery — see
   `_audit_group` and the comment above it in
   [`audit.py`](../../apps/engine/app/padnext/audit.py). Every Ziffer-keyed relation
   (`billable`, `rules_bearing_on`, `mutual_exclusion_survivors`, …) is now grounded per billing
   case, so a rule can no longer see two patients' claims at once. The `<abrechnungsfall>` was
   chosen over the `<rechnung>` it sits inside because it is PADnext's own unit for one patient's
   case, and this codebase never parses enough patient identity to know whether two
   `<abrechnungsfall>` elements in two different invoices are the same patient — grouping any wider
   than the case itself would have to guess.
2. `logic/datalog/goae_rules.dl` LAYER 3 now carries a `datum(Z, Date)` fact — fed from
   `ClinicalAct.service_date` via `app/solvers/souffle_facts.py`, empty for every caller that does
   not track service dates — and derives `blocked_exclusion_cross_date` instead of
   `blocked_exclusion` once it knows the two Ziffern were rendered on different dates.
   `app/padnext/audit.py` reads that off `BlockedCode.cross_date` and routes the match to
   `unconfirmed` rather than `confirmed_wrong`: the invoice alone does not prove the exclusion does
   NOT apply, only that this engine cannot say it does. This replaced an interim Python-side
   workaround in `classify_position` that inferred the same thing from `PadnextAuditedPosition.datum`
   after the fact — the solver states it directly now, so the workaround was removed.

Neither fix changes the three-bucket model or weakens the echtdaten gate; both only change which
positions a verified rule is credited against. Case F's two positions land in `unconfirmed` rather
than `confirmed_fine`, and that is not a loose end: `rules_bearing_on` credits a verified rule to an
invoice only when *every* Ziffer it names is claimed there (the same rule case A's positions are
`unconfirmed` under, and case B's are `confirmed_fine` under, once it is scoped correctly per case) —
a lone GOÄ 34 with no GOÄ 4 on its own `<abrechnungsfall>` was never actually tested against this
exclusion, so crediting it would overclaim coverage the same way the original bug overclaimed a
defect.

---

## 6. When something fails

| Symptom | Read this first |
|---|---|
| `test_expectations_are_not_stale` fails | the catalog or a rule CSV moved. Regenerate, then **read the diff** — §2. |
| the receipt canary moved, totals unchanged | [`services/receipt.py`](../../apps/engine/app/services/receipt.py): a response-shape change moves the hash without changing a billing decision. |
| a euro figure moved | recompute by hand from `punkte × faktor × 5.82873 ct`. If the oracle is right and the engine is not, that is a **BUG finding** — file it like §5, do not edit the expectation. |
| step 1 fails with sign-up refused | `SIGNUP_ALLOWLIST` on that deployment. Add `@e2e.azmoth.test`. |
| step 1 waits, then fails with `429` | Better Auth rate-limits its own auth routes. The script waits out the `retry_after` up to three times; a fourth consecutive run inside the window needs a minute. |
| step 2 fails `403 onboarding_required` | the practice rows exist but the cookie does not. The script calls `GET /api/onboarding/resume` for this and re-onboards if that is not enough; a persistent failure means the `doctor_profiles` / `practices` rows are gone. |
| step 3 fails `422 PADNEXT_SCHEMA_VIOLATION` | that deployment sets `PADNEXT_SCHEMA_POLICY` to something the fixtures were not built for. All five deliveries conform; `strict` is the expected setting. |
| steps 2 or 8 print `SKIP` | `docker compose exec postgres psql` could not run. Everything else still ran; only the two database-level assertions were unavailable. |

**Never make a failing expectation pass by editing it to match the engine.** That converts a golden
test into a snapshot of whatever the engine currently does, which is the one thing it must not be.
Either the data moved (regenerate, and read the diff) or the engine is wrong (report it).

---

## 7. If roll-forward fails

`E2E_LEGACY_PASSWORDS` (§1) recovers an account that is stale by *one* password change. If it is
stale in some other way — the password predates every name the script still knows, or the account
is simply broken — there is no endpoint left to reach for: no admin plugin exists on this
deployment, and `POST /api/auth/request-password-reset` is hard-disabled
(`RESET_PASSWORD_DISABLED`). The only way forward is to delete the two `user` rows by hand and let
the next run sign up fresh:

```bash
docker compose -f infra/docker/docker-compose.dev.yml exec postgres \
  psql -U azmoth -d azmoth -c "DELETE FROM \"user\" WHERE email LIKE '%@e2e.azmoth.test';"
```

There is deliberately no `--reset-users` flag that wraps this. The script's whole design is that it
writes to the database through **only** the product's own endpoints (§1, "No sideways access"), so a
change that broke sign-up or onboarding cannot be hidden by a flag that repairs the damage from
outside the API. This SQL is the one documented opt-in escape from that rule, and it is a human
running it, not the script.

**Before you run it, know what it does not clean up.** `doctor_profiles`, `organization`,
`practices` and `member` have no database-level foreign key back to `user` — deleting the user row
does not cascade to them, and Better Auth's own `organization/delete` (which does clean up `member`
and `organization`) never runs here because there is no session left to call it with. That leaves
`doctor_profiles` and `practices` rows behind, keyed to a `user_id` / `organization_id` that no
longer resolves to anyone — and since `doctor_profiles.lanr` and `practices.organization_id` are
**unique columns**, those orphaned rows permanently refuse the next onboarding attempt for the same
synthetic identity (`lanr_already_registered`, HTTP 409), no matter how many times the account
itself is deleted and recreated. This is not hypothetical: it is exactly what happened while
preparing this section, and step 1 alone was not enough to un-stick it.

If onboarding 409s on `lanr_already_registered` for `999000101` or `999000102` after a `user` delete,
also clear the rows it left behind — first confirm the `doctor_profiles` row's `user_id` no longer
matches a live `user` (so this cannot delete something another account still depends on), then:

```bash
docker compose -f infra/docker/docker-compose.dev.yml exec postgres psql -U azmoth -d azmoth -c "
DELETE FROM doctor_profiles WHERE lanr IN ('999000101','999000102');
DELETE FROM practices WHERE bsnr IN ('999000201','999000202');
DELETE FROM organization WHERE id NOT IN (SELECT \"organizationId\" FROM member);
"
```

The last line is deliberately scoped to organizations with zero members rather than to a name or id
literal — a membership-less organization cannot be signed into by anyone, e2e or otherwise, so it is
safe to treat as orphaned wherever this deployment's history left one.
