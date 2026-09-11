# Fact base for social content

Internal reference. English notes, German quotes where the source is German. Every fact below is
either a value pinned by a test in this repo, or a direct quote/paraphrase of a repo document.
**Nothing here that isn't in the repo.** If a number isn't cited to a path, don't use it.

Two facts are load-bearing for how this whole bank must be written:

- `apps/engine/tests/test_published_numbers.py` fails the build if any shipped file — except
  `apps/marketing/src/lib/engine-facts.ts` and the one worked example in
  `docs/api/PARTNER_API.md` — prints a bare rule count. `docs/content/` isn't in its scanned globs,
  so nothing here trips it mechanically, but the discipline is the point, not the test: **every
  number below is dated and sourced**, so a post reads as "true as of this commit," never as a
  permanent claim. Treat "Stand: 2026-09-12" as part of the number, not a footnote.
- Two snapshots of the same engine disagree with each other, on purpose: `engine-facts.ts`
  (verified 2026-09-12) and `docs/performance_baseline.md` (measured 2026-08-23) quote different
  catalog sizes and rule counts because the rule set and catalog changed between the two dates.
  **Never mix figures from different snapshots in one post.** F01–F04 use the current
  (2026-09-12) snapshot; F33 is the older, dated one, kept only because F03's latency figure comes
  from that same measurement run.

---

## Engine numbers (current snapshot, verified 2026-09-12)

**F01 — Enforced rule count.** 944 rules may currently suppress a position; 980 constraint rules
are loaded in total (enforced + not-yet-enforced). Moved from 858/894 by the coverage-sprint batch
1 (`docs/content/coverage-sprint-plan.md`), which added 86 hand-verified rules.
Source: `apps/marketing/src/lib/engine-facts.ts:22-34` (`ENFORCED_RULE_COUNT`,
`CONSTRAINT_RULE_COUNT`), pinned against the live engine by
`test_the_marketing_site_quotes_the_engine_and_not_a_memory` (in
`apps/engine/tests/test_published_numbers.py`).

**F02 — Catalog coverage.** The loaded catalog snapshot holds 2,343 GOÄ Ziffern; 383 of them are
named by at least one enforced rule — about 16.3% (`383 / 2343`). This is the number the site
prints at the same size as its strongest figures, not in a footnote. Moved from 358 / ~15.3% by the
same coverage-sprint batch.
Source: `apps/marketing/src/lib/engine-facts.ts:36-56` (`CATALOG_ZIFFER_COUNT`,
`ZIFFERN_UNDER_RULE_COUNT`, `CATALOG_COVERAGE_SHARE`).

**F03 — Latency.** Median end-to-end latency for one full invoice through the pipeline: 80 ms
(rounded), from a measured median of 75.8 / 76.8 / 79.5 ms across the three golden cases, seven
cold runs each, on a 2020 laptop with a browser open. **Per invoice, not per position** — a
per-position figure would read ~8x smaller and is deliberately not the number used.
Source: `apps/marketing/src/lib/engine-facts.ts:42-53` (`LATENCY_MS_PER_INVOICE`); measurement
detail in `docs/performance_baseline.md` (measured 2026-08-23, see F33 caveat above).

**F04 — Catalog snapshot name.** The catalog in force for the numbers above is
`goae_official_snapshot_2026-07-25`.
Source: `apps/marketing/src/lib/engine-facts.ts:26`; also printed as `catalog_version` in every
golden-case report, e.g. `apps/engine/tests/golden/case_a_known_answer/expected.json:10`.

---

## Solvers and architecture

**F05 — Two solvers, two jobs.** Soufflé (stratified Datalog, `logic/datalog/goae_rules.dl`)
decides everything *certain* — what's chargeable, what's hard-blocked — and exports a `proof` row
for every conclusion. Clingo (ASP, `logic/asp/goae_optimize.lp`) only arbitrates what Soufflé left
open: which side of a mutually-exclusive conflict wins, which factor, which analog code.
Source: `docs/architecture/RULE_SYSTEM.md` §3–4 (data-flow diagram in §0).

**F06 — Solver versions.** Clingo 5.8.0 (Python bindings, read live from the installed library so
it can't drift from what's actually running); Soufflé 2.5, interpreted (no compiled C++ binary at
runtime).
Source: `apps/engine/requirements.txt:11` (`clingo==5.8.0`); `apps/engine/Dockerfile:26`
(`SOUFFLE_DEB=x86_64-ubuntu-2204-souffle-2.5-Linux.deb`); `apps/engine/app/config.py`
(`clingo_version` property); `docs/performance_baseline.md` §1.

**F07 — Revenue is not the objective.** Clingo's objective hierarchy is lexicographic, five
priority levels; the file's own comment: "Evidence and specificity outrank money on purpose. An
objective that maximised revenue would systematically pick whichever of two competing positions
pays more, which is upcoding." Higher total points (`@1`) is the lowest priority — a tiebreaker
only, after clinical evidence, specificity, never-drop-a-charge, and never-double-charge-an-analog.
Source: `docs/architecture/RULE_SYSTEM.md` §4, citing `logic/asp/goae_optimize.lp:14-26`.

**F08 — Why two solvers, not one.** A single self-referential "blocked" relation for mutual
exclusions (e.g. GOÄ Nr. 5/6/7/8) is not stratifiable in Datalog and would silently make a whole
cluster of legitimate charges vanish under negation-as-failure. Soufflé exports the conflict and
refuses to guess; Clingo is the only thing that resolves it.
Source: `docs/architecture/RULE_SYSTEM.md` §3, §4 item 5, citing `logic/datalog/goae_rules.dl:14-23`.

**F09 — PADnext audit path skips Clingo entirely.** An already-coded invoice has no arbitration
left to make — the engine's job is to check it, not re-decide it. All three PADnext callers build a
full pipeline (both solvers exist) but wire only Soufflé's `run` into the audit function; none
references the Clingo instance.
Source: `docs/architecture/RULE_SYSTEM.md` §4, citing `apps/engine/app/api/audit.py:264`,
`apps/engine/app/api/padnext.py:149`, `apps/engine/app/services/batch_audit.py:244`.

**F10 — The three-bucket verdict.** Every position lands in exactly one of `confirmed_fine`,
`confirmed_wrong`, or `unconfirmed` — there is no separate "FAIL" bucket beyond `confirmed_wrong`,
and "absence of a confirmed defect is explicitly not treated as proof of correctness." The
classifying function's own docstring: "The order of the tests is the argument. Proof that a
position is wrong comes first and is not softened by advisory noise."
Source: `docs/architecture/RULE_SYSTEM.md` §6, citing `apps/engine/app/padnext/audit.py:680-794`
(`classify_position`).

**F11 — Receipt hash, ten fields.** `receipt_hash()` is a SHA-256 over ten fields, in this order:
`catalog_version, catalog_sha256, rules_version, rules_hash, logic_version, solver_version,
rules_engine_version, policy, facts, output`. Same hash implies same
catalog/rules/logic/solver/policy/input; the converse does not hold across engine versions — a
receipt is comparable *within* one engine version, not guaranteed across one, by design.
Source: `docs/architecture/RULE_SYSTEM.md` §7, citing `apps/engine/app/services/receipt.py:50-76`.

**F12 — `<abrechnungsfall>` grouping, and the bug it fixed.** The audit groups strictly at
`<abrechnungsfall>` (one patient encounter), never at the wider `<rechnung>` or the whole delivery.
Before this fix, an exclusion rule fired "the moment GOÄ 34 and GOÄ 4 both appeared *anywhere* in
the batch" — a real, shipped defect that could convict one patient's charge because a *different*
patient billed the excluded code. Commit `7f917db` states it plainly and adds two permanent
regression fixtures.
Source: `docs/architecture/RULE_SYSTEM.md` §5, citing `apps/engine/app/padnext/audit.py:797-815,
1455-1473` and golden cases `case_f_cross_patient_boundary`, `case_g_cross_date_same_patient`.

**F13 — The stale-numbers incident.** This product "shipped, for weeks, a customer-facing PDF"
asserting most exclusion rules were still unconfirmed long after verification had promoted almost
all of them, plus "an OpenAPI description and a partner contract quoting counts that were wrong by
an order of magnitude in the *other* direction." Every number had been true when written; nothing
failed until a test was added that turns a stale figure in shipped text into a build failure.
Source: `apps/engine/tests/test_published_numbers.py` (module docstring, lines 1–36).

**F14 — Rule counts are banned from prose, everywhere except two places.** A test scans engine
source, the web app, the marketing site's pages/components/copy, both READMEs, and the
architecture docs for any sentence quoting a rule count and fails the build if it finds one. The
two exceptions: `apps/marketing/src/lib/engine-facts.ts` (the numbers behind this whole document)
and the one worked example in `docs/api/PARTNER_API.md` — both pinned against what the engine
actually computes.
Source: `apps/engine/tests/test_published_numbers.py`
(`test_no_shipped_file_quotes_a_rule_count`, `SCANNED_GLOBS`, `WORKED_EXAMPLE`).

---

## Rule extraction and verification

**F15 — Rules are re-derived by two independent parsers before being enforced.** `import_goae.py`
parses the official GOÄ XML into candidate rules; `deterministic_rule_parser.py` independently
re-reads the same source prose and either confirms a row or quarantines it. A model verification
pass and a human review queue sit on top of that. Live count of one such pass:
`data/rules/deterministic_parse_report.json` — 837 examined, 831 confirmed, 6 quarantined (all
"conditional").
Source: `docs/architecture/RULE_SYSTEM.md` §2, §8.

**F16 — `verified` gates enforcement, not extraction.** A rejected row is always suppressed; a
verified row is always enforced; an unreviewed row's fate depends on `UnverifiedRulePolicy`
(`WARN` is the shipped default — suppress with a warning; `BLOCK` would enforce anyway; `IGNORE`
would drop silently). Switching the default is explicitly called out as "a policy decision, not a
refactor."
Source: `docs/architecture/RULE_SYSTEM.md` §2, §10 item 12, citing
`apps/engine/app/config.py:124-127`, `apps/engine/app/rules/rule_store.py:246-263`.

---

## Named, current limitations (stated by the repo itself)

**F17 — No mutation testing.** Stated directly as a bottleneck: no `mutmut`/`cosmic-ray` config or
dependency exists anywhere. The golden-case suite is comprehensive but hand-curated, "not
systematically adversarial."
Source: `docs/architecture/RULE_SYSTEM.md` §9, "Current bottlenecks."

**F18 — `zielleistung.csv` is empty.** All four Zielleistung (component-service) rules currently in
force come from the manual file; the automated extraction path for this rule type is, in the
repo's own words, "unproven at scale."
Source: `docs/architecture/RULE_SYSTEM.md`, "Current bottlenecks."

**F19 — Analog-candidate rules are all unverified.** Every row in `analog_candidates.csv` is
`verified=false`/`illustrative` — the § 6 Abs. 2 analog ladder runs on unverified data by default,
subject to the same `UnverifiedRulePolicy`.
Source: `docs/architecture/RULE_SYSTEM.md`, "Current bottlenecks."

**F20 — Receipt hashes aren't stable across engine versions, by design.** A consumer wanting
long-term audit continuity across upgrades would need a narrower, explicitly-scoped hash that
doesn't exist yet — named as a possible future change, not yet built.
Source: `docs/architecture/RULE_SYSTEM.md`, "Current bottlenecks," citing
`apps/engine/app/services/receipt.py`.

**F21 — 6 of 837 exclusion rows are permanently quarantined.** These represent GOÄ provisions the
deterministic parser structurally cannot resolve (they need clinical context not present in an
invoice) — stated as "a ceiling on automatic coverage, not a bug to fix."
Source: `docs/architecture/RULE_SYSTEM.md`, "Current bottlenecks."

---

## Golden test cases (worked examples, hashes)

**F22 — Nine golden cases.** Five PADnext deliveries worked out by hand from the fee schedule
("oracle.py … recomputes every amount as `ROUND_HALF_UP(punkte × faktor × punktwert_cent ÷ 100,
cent)`"), plus four reproducers for fixed defects. Two independent runners (in-process test, real
HTTP against a running stack) must agree on every one.
Source: `apps/engine/tests/golden/README.md`.

**F23 — case_a_known_answer.** 5 positions, claimed and recomputed total both €78.81, nothing
wrong and nothing confirmed (all 5 positions bucket `unconfirmed`), `receipt_hash_stable_across_runs:
true`, example hash prefix `a11b95a38a06640c`.
Source: `apps/engine/tests/golden/case_a_known_answer/expected.json`.

**F24 — case_b_verified_exclusion.** `excl_auto_34_4` fires: GOÄ Ziffer 4 (€29.49) is blocked by
GOÄ 34 (€40.22, unaffected) — legal basis "GOÄ Anmerkung zu Nummer 4." Claimed total €69.71 = split
€40.22 `confirmed_fine` + €29.49 `confirmed_wrong`.
Source: `apps/engine/tests/golden/case_b_verified_exclusion/expected.json`.

**F25 — case_c_verified_factor_cap.** `cap_auto_440` fires on GOÄ 440 claimed at factor 2.3
(€53.62, `confirmed_wrong`, legal basis "GOÄ Allgemeine Bestimmung"); the identical Ziffer claimed
at factor 1.0 (€23.31) survives as `confirmed_fine`.
Source: `apps/engine/tests/golden/case_c_verified_factor_cap/expected.json`.

**F26 — case_g_cross_date_same_patient.** The same exclusion, 5.5 months apart for the same
patient, is classified `unconfirmed` (advisory), not `confirmed_wrong` — a hard Datalog conclusion
deliberately softened because "alongside" (`neben`) is a same-encounter clinical term, not a
bookkeeping one.
Source: `docs/architecture/RULE_SYSTEM.md` §6, §9; `apps/engine/tests/golden/README.md`.

---

## Data handling and the anonymisation/echtdaten gate

**F27 — The engine refuses undeclared or real data by default.** `PADNEXT_ALLOW_REAL_DATA=false`
in every shipped compose file. A delivery flagged `echtdaten="1"` (real data) is refused with `422
REAL_DATA_REFUSED`; a delivery that declares nothing or an undefined value (e.g. `echtdaten="ja"`)
is refused with `422 ECHTDATEN_UNDECLARED` — a missing declaration is never read as "test data."
Source: `legal/TOM.md` (Vorbemerkung); `docs/pilot/ANONYMIZATION_SPEC.md` §1;
`docs/DATA_HANDLING_POLICY.md`.

**F28 — The single-audit endpoint stores nothing.** `POST /api/v1/audit/single` parses the delivery
in memory, audits it, and returns the report — "No row, no file, nothing to delete afterwards."
Bulk-job archives are deleted on reaching `COMPLETED`/`FAILED` by default
(`RETAIN_BULK_UPLOADS=false`). Other audit data (JSON results) retained `DATA_RETENTION_DAYS` — 90
by default, 30 in the pilot.
Source: `docs/DATA_HANDLING_POLICY.md` §1, §4.

**F29 — No third-party processor sits in the request path.** No analytics service, no external
logging service, no AI provider — "the engine calls no external API while auditing"
(`EXTRACTION_MODE=manual` is the only supported mode; the engine holds no model).
Source: `docs/DATA_HANDLING_POLICY.md` §3.

**F30 — The anonymisation script needs nothing but stock Python 3.9+.** It "installs nothing, loads
nothing, makes no network connection," never modifies or overwrites its input, and (in `strict`
mode, the default) rebuilds the export containing *only* the elements/attributes the audit engine
actually reads.
Source: `docs/pilot/ANONYMIZATION_SPEC.md` §2–3.

---

## Forbidden claims — verified absent or explicitly qualified in the repo

**F31 — No "Made in Germany."** A fourth trust badge used to read "Made in Germany" with a 🇩🇪
glyph. It was removed because it was not true: Azmoth is operated from Tunisia, and the marketing
site is served by Vercel — the Impressum says both. The code comment: "Getting caught on it costs
more than the badge was ever worth."
Source: `apps/marketing/src/components/trust-badges.tsx` (comment).

**F32 — "DSGVO-konform" is always qualified.** Never asserted unqualified; qualified specifically
to processing synthetic test data, matching what `legal/AVV_Anlage.md` and the
Datenschutzerklärung actually say. Unqualified, the comment notes, it "claims a compliance posture
for processing that has not been contracted yet."
Source: `apps/marketing/src/components/trust-badges.tsx` (comment).

**F33 — No ISO 27001, no BSI, no SOC 2, no TÜV mark.** Stated directly, in the trust-row component
and in the legal documents: "Der Auftragnehmer verfügt über keine Zertifizierung nach ISO 27001,
ISO 27701, SOC 2 oder einem anderen Standard und behauptet keine." No penetration test has been
performed either.
Source: `apps/marketing/src/components/security-badges.tsx` (comment); `legal/TOM.md`;
`docs/DATA_HANDLING_POLICY.md:146`; `legal/COMPLIANCE_ROADMAP.md:173`.

**F34 — No AVV (Auftragsverarbeitungsvertrag) is in force.** `legal/AVV_Anlage.md` and
`legal/TOM.md` both exist and are drafts; neither is a signed contract. Production patient data
requires that contract, a documented lawful basis, and the controls in
`docs/compliance/PRIVATE_DATA_WARNING.md` — none of which exist yet.
Source: `apps/marketing/src/components/security-badges.tsx` (comment);
`docs/DATA_HANDLING_POLICY.md` (status banner, §5 reference).

**F35 — No outcome numbers, ever — a specific rejected brief, as evidence.** A marketing brief
asked for "Pilot-Ergebnisse (letzte 90 Tage): 47 Fehler gefunden, €12.340 gespart pro Monat, 15
Stunden pro Woche gespart," under a quote attributed to "Dr. med. [Name], Praxis für Orthopädie."
It was not written: "There is no pilot in this repository, no customer, and no measurement behind
any of those four figures." Named explicitly as a §5 UWG problem, not just a taste problem.
Source: `apps/marketing/src/components/metrics.tsx` (comment, "Why there is no testimonial here").

**F36 — No invented comparison numbers.** A separate brief asked for "4 Stunden/Woche → 5 Minuten",
"5–15% Fehlerquote → 99,3% geprüft", "€12k Regress-Risiko → €0 Risiko." None of those six numbers
exists in the repository, and three of them describe measurements nobody has taken (how long a
billing centre spends reviewing, their error rate, what a Regress costs them). Only the side of the
comparison sourced from `engineFacts` carries digits; the other side describes *properties*, not
measurements.
Source: `apps/marketing/src/components/comparison.tsx` (comment).

**F37 — Hosting is named honestly, not favorably.** The AVV names AWS `eu-central-1` (Frankfurt) as
the intended application-tier region — marked *intended* because the engine isn't publicly deployed
yet — and Neon Postgres on `aws-eu-central-1`, also Frankfurt. Vercel (serving the marketing site
today) is a US company; Neon, LLC is a Databricks subsidiary relying on the Data Privacy Framework
for transfers. The badge says "Frankfurt-hosted," which is true of data at rest, and deliberately
does not say "keine US-Berührung," which would not be true of the supply chain.
Source: `apps/marketing/src/components/security-badges.tsx` (comment); `legal/AVV_Anlage.md`.

---

## Company and pilot facts

**F38 — Legal entity and founder.** Azmoth operates from Bureau 5, Centre Aziza, 1. Etage, Av. de
l'Indépendance, Menzel Bourguiba 7050, Tunisia. Vertretungsberechtigt: Oussama Khadraoui. Contact:
contact@azmoth.com.
Source: `legal/TOM.md` (header table).

**F39 — Format scope.** Azmoth audits privately-billed medical invoices in the PADnext format (ADL
2.12) against the GOÄ (Gebührenordnung für Ärzte).
Source: `legal/TOM.md` (opening line).

**F40 — Pilot terms.** Free, non-binding, synthetic test data only, and — per the homepage —
"derzeit auf freigeschaltete Teilnehmer beschränkt" (allowlist-gated). The pilot agreement runs six
to eight weeks from signature; either side can end it.
Source: `legal/PILOT_VEREINBARUNG.md:42`; `apps/marketing/messages/de.json`
(`startseite.held.hinweis`).

**F41 — Catalog editions on disk.** `goae_1996`, `goae_2012`, `goae_current`, `goae_2026_current`,
`goae_neu_draft`. Only `goae_current` is a real official snapshot (publisher: "Bundesamt für
Justiz / Bundesministerium der Justiz"); the others are synthetic fixtures —
`goae_1996/goae.official.json` literally carries `"synthetic": true` and publisher "Azmoth engine
test fixtures — kein amtliches Werk."
Source: `docs/architecture/RULE_SYSTEM.md` §1.

---

## Older, dated snapshot (do not mix with F01–F04)

**F42 — 2026-08-23 measurement snapshot.** At the time `docs/performance_baseline.md` was measured:
catalog `goae_official_snapshot_2026-07-25` held 2,192 Ziffern; 30 enforced exclusions, 862
advisory/unverified. These figures are superseded by F01–F02 (2026-09-09) and must never be quoted
alongside them in the same post.
Source: `docs/performance_baseline.md` §1.
