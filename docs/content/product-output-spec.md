# Product output spec: O1 / O2 / O3

Target schema for the three customer-facing outputs Azmoth promises. This is a **target for future
UI/API work only** — nothing here is implemented by this spec, and it changes no engine semantics.
It exists so that UI work has one schema to build against instead of three ad-hoc ones, and so that
"we promised X" has a single place to check X against.

Everything below is a *view* over data the engine (`apps/engine/app/schemas/padnext.py`,
`PadnextAuditReport` / `PadnextAuditedPosition` / `PadnextFinding`) already computes. Nothing here
asks the rules engine, the catalog, or the solver to decide anything new. Where a field does not
exist today, that is called out explicitly rather than implied.

## The one invariant

**Every flag carries its citation.** Any element of a report that tells a reader "this line is a
problem" — a verdict other than clean, a severity above `info`, a red or yellow traffic-light state
— must carry, on the same object, a non-empty `legal_basis` (the GOÄ paragraph or Anmerkung text)
and a `rule_id` identifying which rule produced it, or must say explicitly that no verified rule
exists and the position is therefore unconfirmed rather than defective. A flag with an empty
citation is a defect in the report, not a defect in the invoice.

The engine already mostly honors this — see the Gap Table for where it does and does not — but no
schema today *enforces* it, and no UI validates it before rendering. The target schemas below make
citation a required field precisely so a future implementation cannot regress it silently.

---

## O1 — Pre-submission correction report (Abrechnungsstelle / billing office)

**Input:** a batch of invoices (already supported: `POST /padnext/batch`, `POST /audit/bulk`).
**Output today:** `BatchAuditJob` → per-file `PadnextAuditReport`, aggregated by
`BatchAggregateSummary`.
**What's missing:** a structured, per-violation **recommended action** field. Today the closest
thing is `bucket_reason` / `PadnextFinding.message` — free-text prose, not an imperative a billing
clerk can act on without reading German legal prose line by line.

### Target schema — `CorrectionItem`

```jsonc
{
  "ziffer": "5",                          // present today: PadnextAuditedPosition.ziffer
  "rechnungs_id": "SYNTH-AUDIT-0001",     // present today: PadnextFinding.rechnungs_id
  "verdict_code": "MUTUAL_EXCLUSION",     // NEW — a stable machine code, one per finding "type"
  "rule_id": "excl_man_5_7",              // present today: PadnextFinding.rule_id
  "citation": {                            // present today, split across two string fields;
    "legal_basis": "GOÄ Anmerkungen zu den Nummern 5, 6, 7, 8 (Abschnitt B I)",
    "quote": "Die Leistung nach Nummer 7 ist neben den Leistungen nach den Nummern 5, 6 und/oder 8 nicht berechnungsfähig."
                                            // present today only in data/rules/exclusions.csv,
                                            // NOT echoed onto PadnextFinding/PadnextAuditedPosition
  },
  "recommended_action": {                  // NEW — does not exist on any audit-path model today
    "code": "REMOVE_LINE",                 // closed union: REMOVE_LINE | REDUCE_FACTOR | ADD_JUSTIFICATION | MANUAL_REVIEW
    "text_de": "Nummer 5 oder Nummer 7 entfernen — beide sind nicht gemeinsam berechnungsfähig.",
    "target_value": null                   // e.g. "3.5" for a REDUCE_FACTOR action
  },
  "severity": "error",                     // present today: PadnextFinding.severity
  "verified": true                         // present today, implicitly: rule_id in verified_rule_ids
}
```

**Worked example** (from the live run captured in the audit, position 4 / GOÄ 3):

```jsonc
{
  "ziffer": "3",
  "rechnungs_id": "SYNTH-AUDIT-0001",
  "verdict_code": "FACTOR_ABOVE_CAP",
  "rule_id": "",                           // gap today: the factor-cap finding carries no rule_id
  "citation": { "legal_basis": "§ 5 Abs. 1, 2 GOÄ", "quote": "" },
  "recommended_action": {
    "code": "REDUCE_FACTOR",
    "text_de": "Faktor auf höchstens 3.5 reduzieren.",
    "target_value": "3.5"
  },
  "severity": "error",
  "verified": true
}
```

---

## O2 — Audit / rejection report (PKV / Beihilfe)

**Input:** one invoice (supported today: `POST /audit/single`, `POST /padnext/audit`).
**Output today:** `PadnextAuditReport` — verdict, bucket, citation, all present per position.
**What's missing:** (1) a single explicit `UNKNOWN` state a client can check without combining two
fields, and (2) an `evidence` block naming what patient facts the verdict depended on, and whether
they were present or `"missing"`.

### Target schema — `AuditedLine`

```jsonc
{
  "ziffer": "412",
  "verdict": "UNKNOWN",                    // NEW closed union: CONFIRMED_FINE | CONFIRMED_WRONG | UNKNOWN
                                            // — collapses today's two-field verdict/bucket split
                                            //   (PadnextAuditedPosition.verdict + .bucket) into one
  "citation": {
    "legal_basis": "GOÄ Leistungslegende Nr. 412",
    "rule_id": "age_man_412"
  },
  "evidence": [                            // NEW — does not exist on the audit path at all today
    {
      "field": "patient_age_years",
      "required_by_rule": "age_man_412",   // this Ziffer IS age-restricted (max_age=1) —
                                            // data/rules/age_restrictions.manual.csv
      "value": null,
      "status": "missing"                  // PADnext carries no patient identity; see note below
    }
  ],
  "reason": "Keine verifizierte Regel bildet diese Ziffer ab.",
  "amount_claimed_eur": "16.32",
  "amount_recomputed_eur": "16.32"
}
```

**Why `evidence` matters and is not cosmetic.** The live run (see the audit's captured JSON)
billed GOÄ 412 — "Ultraschalluntersuchung des Schädels bei einem Säugling ... bis zum vollendeten 2.
Lebensjahr" — an age-restricted service. The engine holds a real, verified rule for it
(`age_man_412`, `data/rules/age_restrictions.manual.csv:5`) and evaluates that exact rule family
elsewhere (the `/solve` clinical pipeline, `apps/engine/app/rules/rule_store.py:229`). But the
PADnext audit path (`apps/engine/app/padnext/audit.py`) never reads patient age or sex at all — by
design, since a PADnext delivery carries no patient identity — so this line came back
`verdict: "chargeable"`, `bucket: "unconfirmed"`, with **zero mention that an age restriction
applies to this Ziffer or that the age needed to check it is absent.** A payer auditing this claim
for a genuinely underage patient gets no signal either way; a payer auditing it for an adult patient
also gets no signal. O2 promises evidence "or missing" precisely to make this distinction visible;
today it is invisible on both sides.

---

## O3 — Traffic-light view (physician / PVS)

**Input:** one invoice, already audited by O1 or O2.
**Output today:** none as a dedicated construct — see Gap Table. The three-bucket color mapping
(`apps/web/lib/padnext/format.ts:71-121`: `confirmed_wrong`→red, `confirmed_fine`→green,
`unconfirmed`→amber) is real and consistently used, but it lives embedded inside the full audit
report UI, not as a standalone simplified view, and no API field computes it directly.

### Target schema — `TrafficLightSummary`

```jsonc
{
  "invoice_id": "SYNTH-AUDIT-0001",
  "overall": "red",                        // worst light across all lines, closed union: green | yellow | red
  "lines": [
    { "ziffer": "5",   "light": "red",    "reason_short": "Schließt sich mit Nummer 7 aus" },
    { "ziffer": "7",   "light": "yellow", "reason_short": "Wechselseitiger Ausschluss, unklar welche Leistung" },
    { "ziffer": "301", "light": "yellow", "reason_short": "Keine verifizierte Regel — unbestätigt" },
    { "ziffer": "3",   "light": "red",    "reason_short": "Faktor über Höchstsatz" },
    { "ziffer": "412", "light": "yellow", "reason_short": "Keine verifizierte Regel — unbestätigt" }
  ],
  "send_recommendation": "hold"            // NEW: send | hold, derived as green-only → send, else hold
}
```

**A finding worth stating plainly, from the live run:** of five lines, **zero** landed on green.
Two were genuinely clean-ish (`301` justified correctly, `412` unremarkable) and both still surface
as yellow, because "no verified rule objected" and "a verified rule confirmed this" are different
statements and the engine is honest about which one it can make. A traffic-light view built
directly on today's bucket semantics would show a physician mostly yellow on an ordinary invoice,
which is correct but needs framing (see the Honest Sales Sheet) or it reads as the tool having no
opinion.

---

## Field glossary (target ↔ what exists today)

| Target field | Backing field today | File:line |
|---|---|---|
| `verdict_code` / `verdict` (O1/O2 unified) | `PadnextAuditedPosition.verdict` + `.bucket` (two fields) | `apps/engine/app/schemas/padnext.py:222,254` |
| `citation.legal_basis` | `PadnextAuditedPosition.legal_basis`, `PadnextFinding.legal_basis` | `padnext.py:247,184` |
| `citation.quote` (verbatim statute text) | Present only in `data/rules/exclusions.csv` / `*.manual.csv`; not echoed onto the response | `data/rules/exclusions.csv:16` |
| `recommended_action` | Does not exist on the audit path; nearest analogue is `bucket_reason` (free text) | `padnext.py:256` |
| `evidence[]` | Does not exist; `Patient.age`/`.sex` exist only on the `/solve` `ClinicalExtraction`, never on the PADnext audit path | `apps/engine/app/schemas/case.py:41-46` |
| `TrafficLightSummary` | Does not exist as a field/endpoint; color mapping exists client-side only | `apps/web/lib/padnext/format.ts:38,71-121` |

## Non-goals

This spec does not change: which rules are enforced vs. advisory, how buckets are computed, the
receipt-hash mechanism, or the three-way financial split (`confirmed_fine_eur` /
`confirmed_wrong_eur` / `unconfirmed_eur`). It is a presentation and API-surface target layered on
top of the existing engine output.
