# The engine

How a clinical record becomes a defensible bill, and where each decision is made.

The GOÄ (Gebührenordnung für Ärzte, 1982) is the fee schedule German physicians bill private
patients under. Coding against it is not classification: it is the application of a written legal
text — which positions exclude each other, which are components of a target service, what
multiplier a documented difficulty supports, what must be justified in writing. So the reasoning is
**symbolic and auditable**, and every layer below is separable, inspectable and testable on its own.

```
              ┌──────────────────────────────────────────────────────────────┐
   OUTSIDE    │  free text, dictation, a form, a PVS export, a model         │
   THE        │  → produces STRUCTURED CLINICAL ENTITIES                     │
   BOUNDARY   └──────────────────────────────────────────────────────────────┘
                                      │
════════════════════ the input boundary ════════════════════════════════════════
                                      │  clinical entities only. no Ziffer,
                                      ▼  no factor, no money.
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ 1  BRIDGE            deterministic CSV lookup                            │
   │                      app/bridge/entity_to_ziffer.py                      │
   │                      → candidate GOÄ Ziffern, with provenance            │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 2  DATALOG           what is CERTAIN                    Soufflé 2.5      │
   │                      logic/datalog/goae_rules.dl                         │
   │                      → billable / blocked / needs_arbitration + proof     │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 3  ASP               what requires a CHOICE             Clingo 5.8.0     │
   │                      logic/asp/goae_optimize.lp                          │
   │                      → arbitration, Steigerungsfaktor, Analogansatz       │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 4  DATALOG again     independent re-check of the chosen factors           │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 5  VALIDATION        re-check, exact money, audit trail                   │
   │                      app/validation/validator.py                          │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 6  PROOF / RECEIPT   per-line proof tree + SHA-256 receipt hash           │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 7  PROPOSAL          status = DRAFT                                       │
   └──────────────────────────────────────────────────────────────────────────┘
                                      │
════════════════════ the approval boundary ══════════════════════════════════════
                                      ▼
                          a physician approves. only then is it a bill.
```

## The input boundary

**The engine takes structured clinical entities and nothing else.** `ClinicalExtraction` — patient
setting, consultation, examinations, procedures, lab tests, diagnoses, and *justification factors*
(clinical circumstances that made something unusually difficult) — is the entire input contract.

The contract is frozen in a specific way: it may not contain a Ziffer, a factor, a Punktzahl, a
Punktwert, an amount, or any other fee-schedule concept — not in a field name, not in a field
description, not in a docstring. Pydantic copies descriptions and docstrings into the JSON schema,
and that schema is exactly what would be handed to a model if extraction ever moved to structured
outputs. `tests/test_schema.py` enforces this on the models *and* on the published OpenAPI
components.

Why it matters: **a model that knows the fee schedule can be steered by it.** Ask it "what happened
clinically" and you get a clinical answer. Ask it anything downstream of a price list and its output
starts to correlate with revenue. So the model — if there is one at all — says what happened; the
mapping from clinical facts to fee-schedule positions is a CSV, and the legal reasoning is Datalog
and ASP.

`EXTRACTION_MODE=manual` is the only supported mode. The POC had an experimental free-text path
behind an OpenAI key; it was not migrated and no LLM SDK is a dependency of this service. What *was*
migrated is the contract that path was held to: `app/core/extraction_prompts.py` still carries the
system prompt and its `FORBIDDEN_PROMPT_TERMS`, and the tests still assert that no GOÄ vocabulary
and no catalog Ziffer appears in it. Whoever builds the upstream extractor inherits a specification
rather than a blank page.

## 1. The bridge — clinical vocabulary meets fee-schedule identifiers

One place, and it is a table lookup: `data/mappings/entity_to_ziffer.csv`, keyed on
`(entity_type, entity_subtype, organ)`. No model runs here, nothing is inferred, and a Ziffer the
loaded catalog does not contain can never be proposed.

One entity may legitimately produce **several** candidates — a knee puncture matches both the
generic Nr. 300 and the knee-specific Nr. 301. Both are proposed on purpose: choosing between them
is a *rule* (`data/rules/specificity.csv`) applied one layer down, where it appears in the proof
tree, rather than a dictionary-ordering accident hidden in Python.

An entity that maps to nothing has three honest outcomes, never an invented code: an analog request
(§ 6 Abs. 2 GOÄ), a warning that the service was **not** charged and needs manual review, or a
warning that the mapping table references a position the catalog does not have.

## 2. The Datalog derivation layer — what is certain

`logic/datalog/goae_rules.dl`, evaluated by Soufflé in interpreter mode over a temporary fact
directory. Everything in it is monotone, terminating and stratified, so it has a unique minimal
model.

Suppression in the GOÄ is layered, and a position that has already lost must not itself suppress a
third one. Hence the strata:

```
proposed → surviving_specific → surviving_zielleistung → surviving_exclusion → billable
              specificity          § 4 Abs. 2a              Leistungslegenden
```

Each layer negates only the layer above it. A single self-referential `blocked` relation — the
obvious first attempt — is not stratifiable and would either be rejected outright or quietly produce
a wrong model.

**What this layer refuses to decide.** Many GOÄ exclusions are mutual: Nr. 5, 6, 7 and 8 exclude one
another, and so do Nr. 422–424 and Nr. 650–653. Under negation-as-failure every member of such a
cluster blocks every other and the whole cluster vanishes — silently destroying a legitimate charge.
Those clusters are detected and exported as `conflict` for the next layer to arbitrate under an
explicit objective. **Datalog concludes what follows; it never guesses.**

The Zielleistungsprinzip (§ 4 Abs. 2a: a component is not chargeable beside its target service) is
resolved *here*, as a hard rule, and deliberately not in the optimiser — components are frequently
worth more in sum than the target service, so an optimiser told to maximise revenue would prefer to
split them, which is precisely the upcoding pattern that gets invoices rejected.

## 3. The Clingo planning layer — what requires a choice

`logic/asp/goae_optimize.lp` decides exactly three things Datalog left open:

1. which member of a mutually exclusive cluster is charged;
2. which Steigerungsfaktor each charged position carries (§ 5, § 12 Abs. 3 GOÄ);
3. which listed position an unlisted service is charged analogously to (§ 6 Abs. 2 GOÄ).

It cannot invent a Ziffer: `bill/1` is derivable only from `fixed/1` or `arbitrate/1`, both injected
facts.

**The objective ordering is the legal posture.** Lexicographic, and revenue is last:

```
@5  never charge an analog position that is already charged directly
@4  never leave a documented, chargeable service off the invoice entirely
@3  prefer the position with the stronger clinical evidence
@2  prefer the more specific position
@1  higher total points   ← tiebreaker ONLY
```

Evidence and specificity outrank money on purpose. An objective that maximised revenue would
systematically pick whichever of two competing positions pays more; `@1` only separates options that
are equally well evidenced and equally specific. The hard rules are **integrity constraints**, not
weighted terms — no objective can trade them away:

```prolog
:- bill(A), bill(B), excluded(A, B), A != B.
:- bill(C), bill(P), zielleistung(P, C).
```

The factor ladder never leaves the § 5 band: absent a documented reason the factor is the
Schwellenwert (which needs no written justification); a documented reason escalates within the band
by severity; the Höchstsatz caps it; and a Leistungslegende cap ("nur mit dem einfachen
Gebührensatz") overrides everything. Any factor above the Schwellenwert is marked
`justification_required` — **factor choice without documentation is not permitted.**

Solving is bounded by `SOLVER_TIMEOUT_SECONDS` (default 5 s, observed ~30 ms) using the
asynchronous solve handle: start, wait, cancel. A cancelled solve returns the best model found so
far, labelled `TIMEOUT_PARTIAL` with a warning that optimality is unproven — hard rules still hold.
A cancelled solve that found *nothing* is a `504`, never an empty invoice: "no answer" and "nothing
is chargeable" are different statements and must not be confused.

Everything non-integer is scaled by 100 in both logic programs, because ASP and Datalog numbers are
integers: factor 2.3 is 230, confidence 0.95 is 95. Conversion is `Decimal`-based, so 1.15 cannot
become 114.

## 4–5. The validation layer — the component that picks a number is not the one that approves it

Two things are load-bearing here.

**It does not trust the layers above it.** Every hard rule Datalog enforced is re-checked against
the final invoice through a separate code path, and the Steigerungsfaktoren the solver chose are fed
*back into* Datalog — over a synthetic bridge containing exactly the final invoice, so analog
positions, which were never candidates on the first pass, get ruled on too. If the two disagree, the
validator raises `ValidationFailed` and the API answers `500`. A disagreement is a bug, not something
to paper over: no invoice is returned.

**Money is exact.** `Decimal` throughout, with the rounding the law prescribes:

```
Gebühr = Punktzahl × Punktwert × Steigerungsfaktor       § 5 Abs. 1 Satz 1–3 GOÄ
fractions below 0.5 down, 0.5 and above up              § 5 Abs. 1 Satz 4 GOÄ
```

so `ROUND_HALF_UP` at cent granularity is statutory, not a house convention. Both the unrounded cent
amount and the rounded EUR amount are returned so a reviewer can audit the rounding, and the § 6a
Minderung (25 % stationär, 15 % belegärztlich, with the Abschnitt-J exemption) is applied per line.

The validator also reconciles *blocked* reasons with the final invoice. Nr. 5 can be suppressed
during rule evaluation by a position that then loses an arbitration — "blocked by GOÄ 7" would be a
true statement about an intermediate step and a misleading one about the bill. Pointing a
Rechnungsprüfer at a code that is not on the invoice is exactly the kind of audit trail that does not
survive contact with one. If *every* blocker of a position fell away, the suppression has lost its
basis and that is reported as a warning rather than silently reinstated.

## 6. The proof and receipt layer

**Every line carries a proof tree.** Each conclusion — positive and negative — is a row from the
Datalog program carrying the rule that produced it, the rule id, and the paragraph of the GOÄ it
rests on. That is the machine-checkable answer to "why is this on my bill?", and the reason the rule
ids travel with the conclusions: a proof step joins back to the exact CSV row and legal quote.

**Rule coverage is published, not implied.** The engine enforces a *subset* of the GOÄ. 837 of the
exclusion rules were extracted from the fee schedule's prose automatically and are unverified; under
the default `UNVERIFIED_RULE_POLICY=warn` they suppress nothing and only warn. Every response
carries `enforced_rule_count`, `advisory_rule_count` and `suppressed_unverified_rule_count`, plus a
warning whenever the advisory set is non-empty. The API must never let "no finding" read as "the
rules confirmed it".

**Missing documentation is surfaced, never acted on.** Where the record supports no more than the
Schwellenwert, `missing_documentation` names the position, the factor being charged, the ceiling
§ 5 Abs. 2 would permit, and what is absent. It is derived only from what the existing logic already
emits; the solver's objective is not consulted and not changed. What is billed is always
`current_factor`. Only a physician can write the justification that would change that.

**The receipt hash.** SHA-256 over: catalog version and catalog file hash, rules version and a hash
of every rule CSV, a hash of both logic programs, the Clingo and Soufflé versions, the policy
fingerprint, the canonical input facts, and the canonical output. Two responses with the same
receipt were produced by the same data, the same logic and the same policy. Nothing measured —
timings, timestamps, ids — is included, because a receipt that changed every run would identify
nothing.

The same identity, minus the output, is the **content-addressed cache key**. Editing one cell of one
rule CSV misses the cache: a cache that could serve a result computed under a different rule set is a
compliance defect, not a performance one.

## 7. The human approval boundary

**The engine produces a `DRAFT`. It never produces a bill.**

`ProposalStatus` is `DRAFT → APPROVED | REJECTED`, and `APPROVED → EXPORTED`. `REJECTED` and
`EXPORTED` are terminal — re-deciding one would mean the approval record no longer describes what was
billed. Approval requires `approved_by`: an approval nobody signed is not an approval. A cached
computation is still returned as a fresh `DRAFT` with a new id, because the *result* is reusable and
the *responsibility* for it is not.

The store is Postgres, and the decision is written down where it was made: the module used to
argue that a real approval record is a retention policy, an access-control model and an audit log
before it is a database schema. Two of those three are still open — but the audit log was never a
reason to postpone a database, it is what one is *for*, and an approval that died with the process
could not answer the only question that matters about it: who accepted this, and when.

So: `proposals` and an append-only `audit_events`, every decision and its event in one transaction,
the lifecycle enforced under a row lock, and a refusal to start in production on anything but
Postgres. Retention and access control remain open and are tracked as open in
[`../compliance/PRIVATE_DATA_WARNING.md`](../compliance/PRIVATE_DATA_WARNING.md) — above a durable
record now, rather than instead of one. Schema and migration commands:
[`DATABASE.md`](DATABASE.md).

## What the engine deliberately does not do

- **It does not decide medicine.** Analog positions (§ 6 Abs. 2) always carry
  `requires_human_review: true`: whether a service is genuinely equivalent to a listed one is a
  medical judgement.
- **It does not claim full rule coverage.** `rule_coverage` is `partial`, per position and overall,
  and says so in every response.
- **It does not trust a PADnext file's arithmetic.** The spec is explicit that `punktzahl`,
  `punktwert` and `gesamtbetrag` are carried *für Kontrollzwecke*, so the audit recomputes from our
  own catalog and reports the difference to the cent.
- **It does not read patient identity.** The PADnext models have no field that could hold a name, an
  address or a date of birth, and a test asserts it. A delivery flagged `echtdaten="1"` is refused.
- **It does not call a gap in its own rules a defect in someone's invoice.** A PADnext audit splits
  the claimed total into `confirmed_wrong_eur` (a verified rule, the versioned catalog or the § 5
  arithmetic shows the position is not chargeable), `confirmed_fine_eur` (every applicable check
  passed *and* at least one verified rule actually bore on it), and `unconfirmed_eur` (no verified
  rule maps to the Ziffer, or the only ones that do are advisory). The three sum to
  `claimed_total_eur` exactly, and `coverage_ratio` publishes the audited share.

  This replaced a single `at_risk_eur = claimed_total − defensible_total`. That subtraction merged
  proof with ignorance, and because 837 of the 869 exclusion rules are machine-extracted and
  unenforced under the default policy, ignorance was the larger part: on the bundled nine-line
  example it reported 200.48 € of 251.54 € as at risk, where only 88.49 € is demonstrable. A
  practice told that 80 % of its revenue is disputed — when most of that is our own missing rule
  coverage — stops believing the audit. `unconfirmed` is not a finding against the practice.
- **It does not maximise revenue.** See `@1`.

## Where things live

| Concern | Path |
| --- | --- |
| Datalog program | `logic/datalog/goae_rules.dl` |
| ASP program | `logic/asp/goae_optimize.lp` |
| GOÄ catalog (2192 positions, official, SHA-256 recorded) | `data/catalogs/goae_current/` |
| Rule tables, with `verified` / `legal_basis` / `quote` per row | `data/rules/*.csv` |
| Entity → Ziffer mapping | `data/mappings/entity_to_ziffer.csv` |
| Raw official XML + manifest | `data/raw/` |
| PADnext framing schema (ours, a strict subset — not the official XSD) | `data/schemas/padnext/` |
| Synthetic cases and frozen snapshots | `logic/tests/` |
| The service | `apps/engine/` |
| Generated API contract | `packages/contracts/` |
