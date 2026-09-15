# GOÄ coverage sprint — batch 3 report (Allgemeine Bestimmungen)

Internal engineering reference. Stand: 2026-09-15. Companion to
`docs/content/coverage-sprint-plan.md` (batch 1) and
`docs/content/coverage-sprint-report-batch2.md` (batch 2). Every number below is either read live
off `data/rules/*.csv` + `data/catalogs/goae_current/`, or printed by a script named in the
section that quotes it. Nothing here is typed from memory — §8 says how to regenerate each figure.

**Result: 383 → 516 Ziffern under an enforced rule (16.35 % → 22.02 %).** 543 new rule rows, all
generated from twenty-two cited GOÄ provisions by `apps/engine/scripts/build_batch3_rules.py`.
`enforced_rule_count` 940 → 1,342; `total_constraint_rule_count` 980 → 1,523. (The 940 baseline
is main after the F1 exclusion-direction fix, PR #87, which this batch is rebased on — see §8.)

---

## 1. What batch 1 could not see

Batch 1 scanned every uncovered Ziffer's `official_text` and `annotations` in
`data/catalogs/goae_current/goae.official.json`, found 114 with any mechanical-constraint wording,
and concluded that the remaining ~1,871 "have no annotation text that mechanically implies a rule
at all — they are uninstrumented, not incorrectly instrumented."

That conclusion was sound about the file and wrong about the fee schedule. The GOÄ states a large
part of its mechanical content in **Allgemeine Bestimmungen**: paragraphs printed under a chapter
or subsection heading, before that section's first Ziffer, governing every position beneath them.
`scripts/import_goae.py` keeps a Ziffer row and the Anmerkungen printed under it; a paragraph that
belongs to no single Ziffer has nowhere to go, so it kept none of them. All **50**.

Those 50 paragraphs hold 66 constraint sentences, including some of the most frequently applied
rules in the whole schedule — that the Zuschläge A–D and E–J may only ever be billed at the single
rate, that the arthroscopy positions swallow the joint puncture beside them, that the sonography
positions 410–418 are mutually exclusive. Not one of them was in the catalog, so neither the
deterministic extractor nor batch 1's regex sweep could ever have seen them:

```
$ python3 -c "
import json; from pathlib import Path
cat = json.loads(Path('data/catalogs/goae_current/goae.official.json').read_text())
needle = 'Die Zuschläge nach den Nummern 440 bis 449'
print([z['ziffer'] for z in cat['ziffern']
       if needle in (z.get('official_text') or '')
       or any(needle in a for a in (z.get('annotations') or []))])"
[]
```

`apps/engine/scripts/extract_allgemeine_bestimmungen.py` recovers them, verbatim, into
`data/catalogs/goae_current/allgemeine_bestimmungen.json`. It does **not** touch
`goae.official.json`: that file's identity is pinned (`tests/test_catalog_snapshot_identity.py`)
and a per-Ziffer row is the wrong home for a paragraph governing 180 positions at once.

A second sweep found the other half of the gap: **29 Ziffer annotations** that *are* in the
catalog, carry an exclusion in plain numbered form, and had never been turned into a rule in
either direction — GOÄ 435's intensive-care list among them, which batch 1 held back for want of
range-expansion tooling (plan §4).

---

## 2. Prioritisation, and an honest word about "frequency"

The brief asks for ranking by billing frequency. **There is no per-Ziffer GOÄ frequency statistic
in this repository, and none was reachable while this batch was written.** The KV statistics that
exist publicly count EBM positions for statutory insurance; GOÄ is the private schedule, its
volumes are held by the PVS houses and the PKV, and mapping one to the other is a modelling
exercise, not a lookup. Printing a "frequency" column sourced from an EBM table would be the same
class of claim this whole sprint exists to avoid.

So the ranking below uses two things that *are* measurable here, and one that is openly a
judgement:

* **Kanten** — how many other Ziffern this batch relates this one to. A position that 182 rules
  touch is entangled in the fee schedule in a way a position with one cap is not, and entanglement
  is where a billing office loses time.
* **2,3× €** — the position's own fee at the Regelhöchstsatz (`punkte × 5.82873 ct × 2.3`), which
  is what a rejection of it costs per occurrence. Rank is `Kanten × €`: what one wrong invoice
  line is worth, times how many ways this position can be got wrong.
* **The chapters chosen.** Abschnitt B (Beratung, Untersuchung, Zuschläge) and Abschnitt C
  (Injektionen, Infusionen, Sonographie, ambulante OP-Zuschläge) are on nearly every private
  invoice; L III is arthroscopy, which is orthopaedics' highest-volume operative block; O I/O II
  are radiology and nuclear medicine. That is a stated judgement about what appears on an invoice,
  not a measurement, and it is marked as such rather than dressed up as data.

What the ranking then answers is the brief's real question — *"which would a billing office say
YES, I need this checked?"* — for the top of the list without much argument: GOÄ 1 beside a
psychotherapy session, a Zuschlag at 2,3× that may only ever be billed at 1,0×, two ultrasound
positions on one day, a joint puncture beside the arthroscopy that contains it. Every one of those
is a rejection a human currently catches by hand, or does not catch.

### Top 50 of the 254 Ziffern batch 3 names

Regenerate with the snippet in §8. `Kanten` counts rule rows naming the Ziffer on either side;
`neu` marks the ones that were under no enforced rule before this batch; `Klassifikation` is §5.

| # | Ziffer | Kap. | Punkte | 2,3× € | Kanten | neu | Klassifikation | Leistung |
|---|---|---|---|---|---|---|---|---|
| 1 | 435 | C | 900 | 120.65 | 182 | ja | FULLY_VERIFIED | Stationäre intensivmedizinische Überwachung und Behandlung eines P |
| 2 | 101 | B | 2844 | 381.27 | 7 | – | PARTIAL | Eingehende Untersuchung eines Toten und Ausstellung einer Todesbes |
| 3 | 30 | B | 900 | 120.65 | 17 | – | PARTIAL | Erhebung der homöopathischen Erstanamnese mit einer Mindestdauer v |
| 4 | 100 | B | 1896 | 254.18 | 7 | – | PARTIAL | Untersuchung eines Toten und Ausstellung einer vorläufigen Todesbe |
| 5 | 449 | C | 900 | 120.65 | 12 | – | PARTIAL | Beobachtung und Betreuung eines Kranken über mehr als vier Stunden |
| 6 | 2191 | L | 2000 | 268.12 | 4 | ja | PARTIAL | Arthroskopische Operation mit primärer Naht, Reinsertion, Rekonstr |
| 7 | 5050 | O | 950 | 127.36 | 8 | – | MECHANICAL_ONLY | Kontrastuntersuchung eines Hüftgelenks, Kniegelenks oder Schulterg |
| 8 | 448 | C | 600 | 80.44 | 12 | – | PARTIAL | Beobachtung und Betreuung eines Kranken über mehr als zwei Stunden |
| 9 | 2190 | L | 1800 | 241.31 | 4 | ja | PARTIAL | Arthroskopische erhaltende Operation an einem Meniskus (z.B. Menis |
| 10 | 2193 | L | 1800 | 241.31 | 4 | ja | PARTIAL | Arthroskopische Operation mit Synovektomie an einem Knie- oder Hüf |
| 11 | 2189 | L | 1500 | 201.09 | 4 | ja | PARTIAL | Arthroskopische Operation mit Entfernung oder Teilresektion eines  |
| 12 | 276 | C | 540 | 72.39 | 11 | – | PARTIAL | Dauertropfinfusion von Zytostatika, von mehr als 6 Stunden Dauer |
| 13 | 22 | B | 300 | 40.22 | 17 | – | MECHANICAL_ONLY | Eingehende Beratung einer Schwangeren im Konfliktfall über die Erh |
| 14 | 34 | B | 300 | 40.22 | 17 | – | PARTIAL | Erörterung (Dauer mindestens 20 Minuten) der Auswirkungen einer Kr |
| 15 | G | B | 450 | 60.33 | 11 | – | PARTIAL | Zuschlag für in der Zeit zwischen 22 und 6 Uhr erbrachte Leistunge |
| 16 | C | B | 320 | 42.90 | 13 | – | PARTIAL | Zuschlag für in der Zeit zwischen 22 und 6 Uhr erbrachte Leistunge |
| 17 | 5060 | O | 500 | 67.03 | 8 | – | MECHANICAL_ONLY | Kontrastuntersuchung eines Kiefergelenks, einschließlich Punktion, |
| 18 | 275 | C | 360 | 48.26 | 11 | – | PARTIAL | Dauertropfinfusion von Zytostatika, von mehr als 90 Minuten Dauer |
| 19 | 870 | G | 750 | 100.55 | 5 | – | MECHANICAL_ONLY | Verhaltenstherapie, Einzelbehandlung, Dauer mindestens 50 Minuten  |
| 20 | H | B | 340 | 45.58 | 11 | – | PARTIAL | Zuschlag für an Samstagen, Sonn- oder Feiertagen erbrachte Leistun |
| 21 | 274 | C | 320 | 42.90 | 11 | – | PARTIAL | Dauertropfinfusion, intravenös, von mehr als 6 Stunden Dauer - geg |
| 22 | 3300 | L | 500 | 67.03 | 7 | ja | FULLY_VERIFIED | Arthroskopie - gegebenenfalls mit Probeexzision - ................ |
| 23 | 886 | G | 700 | 93.84 | 5 | – | MECHANICAL_ONLY | Psychiatrische Behandlung bei Kindern und/oder Jugendlichen unter  |
| 24 | 424 | C | 700 | 93.84 | 5 | – | PARTIAL | Zweidimensionale doppler-echokardiographische Untersuchung mit Bil |
| 25 | 861 | G | 690 | 92.50 | 5 | – | MECHANICAL_ONLY | Tiefenpsychologisch fundierte Psychotherapie, Einzelbehandlung, Da |
| 26 | 863 | G | 690 | 92.50 | 5 | – | MECHANICAL_ONLY | Analytische Psychotherapie, Einzelbehandlung, Dauer mindestens 50  |
| 27 | 415 | C | 300 | 40.22 | 11 | ja | PARTIAL | Ultraschalluntersuchung im Rahmen der Mutterschaftsvorsorge - gege |
| 28 | 5070 | O | 400 | 53.62 | 8 | – | MECHANICAL_ONLY | Kontrastuntersuchung der übrigen Gelenke, einschließlich Punktion, |
| 29 | 8 | B | 260 | 34.86 | 12 | – | PARTIAL | Untersuchung zur Erhebung des Ganzkörperstatus, gegebenenfalls ein |
| 30 | 412 | C | 280 | 37.54 | 11 | ja | PARTIAL | Ultraschalluntersuchung des Schädels bei einem Säugling oder Klein |
| 31 | 413 | C | 280 | 37.54 | 11 | ja | PARTIAL | Ultraschalluntersuchung der Hüftgelenke bei einem Säugling oder Kl |
| 32 | F | B | 260 | 34.86 | 11 | – | PARTIAL | Zuschlag für in der Zeit von 20 bis 22 Uhr oder 6 bis 8 Uhr erbrac |
| 33 | D | B | 220 | 29.49 | 13 | – | PARTIAL | Zuschlag für an Samstagen, Sonn- oder Feiertagen erbrachte Leistun |
| 34 | 3 | B | 150 | 20.11 | 19 | – | MECHANICAL_ONLY | Eingehende, das gewöhnliche Maß übersteigende Beratung - auch mitt |
| 35 | 3894 | M | 900 | 120.65 | 3 | ja | MECHANICAL_ONLY | Bestimmung von allergenspezifischem Immunglobulin (z.B. IgE), Einz |
| 36 | 302 | C | 250 | 33.52 | 10 | – | MECHANICAL_ONLY | Punktion eines Schulter- oder Hüftgelenks |
| 37 | 812 | G | 500 | 67.03 | 5 | – | MECHANICAL_ONLY | Psychiatrische Notfallbehandlung bei Suizidversuch und anderer psy |
| 38 | 423 | C | 500 | 67.03 | 5 | – | PARTIAL | Zweidimensionale echokardiographische Untersuchung mittels Real-Ti |
| 39 | B | B | 180 | 24.13 | 13 | – | PARTIAL | Zuschlag für in der Zeit zwischen 20 und 22 Uhr oder 6 und 8 Uhr a |
| 40 | 417 | C | 210 | 28.15 | 11 | ja | PARTIAL | Ultraschalluntersuchung der Schilddrüse |
| 41 | 418 | C | 210 | 28.15 | 11 | ja | PARTIAL | Ultraschalluntersuchung einer Brustdrüse - gegebenenfalls einschli |
| 42 | 410 | C | 200 | 26.81 | 11 | ja | PARTIAL | Ultraschalluntersuchung eines Organs |
| 43 | 5481 | O | 680 | 91.16 | 3 | – | PARTIAL | Sequenzszintigraphie - mindestens sechs Bilder in schneller Folge  |
| 44 | 2192 | L | 500 | 67.03 | 4 | ja | PARTIAL | Zuschlag zu der Leistung nach Nummer 2191 für die primäre Naht, Re |
| 45 | 807 | G | 400 | 53.62 | 5 | – | MECHANICAL_ONLY | Erhebung einer biographischen psychiatrischen Anamnese bei Kindern |
| 46 | 808 | G | 400 | 53.62 | 5 | – | MECHANICAL_ONLY | Einleitung oder Verlängerung der tiefenpsychologisch fundierten od |
| 47 | 272 | C | 180 | 24.13 | 11 | – | PARTIAL | Infusion, intravenös, von mehr als 30 Minuten Dauer |
| 48 | 273 | C | 180 | 24.13 | 11 | – | PARTIAL | Infusion, intravenös - gegebenenfalls mittels Nabelvenenkatheter o |
| 49 | 7 | B | 160 | 21.45 | 12 | – | PARTIAL | Vollständige körperliche Untersuchung mindestens eines der folgend |
| 50 | 656 | F | 1820 | 243.99 | 1 | ja | MECHANICAL_ONLY | Elektrokardiographische Untersuchung mittels intrakavitärer Ableit |

The 204 Ziffern below the cut are the far side of the same provisions — the 182 positions GOÄ 435
absorbs, the nine psychiatric codes, the Röntgen and Labor positions. They are covered by the same
rules and the same tests; the cut is where the ranking stops being interesting, not where the work
stops.

---

## 3. What was encoded — 22 provisions, 543 rows

Every row is generated. `PROVISIONS` in `apps/engine/scripts/build_batch3_rules.py` is the only
place a human judgement was made: each entry carries the sentence verbatim and the Ziffer tokens
**in the order the sentence writes them**, so review means checking a token list against a quote,
not reading 543 CSV lines. Re-running the script reproduces the files byte for byte (`--check` in
`tests/test_batch3_citations.py`).

All rows ship `verified: true`, `verified_at: 2026-09-15`, `source:
manual_verification:coverage_sprint_batch3`.

| Rows | Kind | Legal basis | What it says |
|---|---|---|---|
| 182 | Ausschluss | GOÄ Anmerkung zu Nummer 435 | intensive care absorbs 181 positions across 21 numeric ranges |
| 80 | Ausschluss | Allg. Best. Abschnitt B, Nr. 4 | Beratung/Erörterung (1, 3, 22, 30, 34) not chargeable beside a psychiatric or psychotherapeutic session (804–812, 817, 835, 849, 861–864, 870, 871, 886, 887) |
| 36 | Ausschluss | Allg. Best. Abschnitt B, Nr. 8 | the general examination (5–8) contains 600, 601, 1203, 1204, 1228, 1240, 1400, 1401, 1414 |
| 30 + 30 | Ausschluss (mutual) | Allg. Best. Abschnitt B V, both provisions | Zuschläge A–D/K 1 and E–J/K 2 exclude each other; each direction cites the sentence that states it |
| 30 | Ausschluss (mutual) | Allg. Best. Abschnitt C II | infusions 271–276 not billable side by side |
| 30 | Ausschluss (mutual) | Allg. Best. Abschnitt C VI, Nr. 3 | sonography 410–418 not billable side by side |
| 28 | Ausschluss | Allg. Best. Abschnitt L III | arthroscopy 2189–2196 contains the joint puncture 300–302 and 3300 |
| 24 | Ausschluss | Allg. Best. Abschnitt O I 1 | arthrography 5050/5060/5070 contains 300–302, 372, 373, 490, 491, 5295 |
| 18 | Ausschluss | Anmerkungen zu 448 / 449 | post-operative observation not chargeable beside a consultation or examination (1–8); 448 ↔ 449 mutual |
| 9 | Ausschluss | Allg. Best. Abschnitt M III 9 | allergen-specific IgE 3892–3894 excludes 3572, 3890, 3891 |
| 8 | Ausschluss | Allg. Best. Abschnitt B VII, Nr. 3 | Leichenschau 100/101 excludes the Besuch positions 48–52 |
| 6 | Ausschluss | Allg. Best. Abschnitt C V | vaccination 376–378 contains the Beratung 1 and 2 |
| 6 | Ausschluss (mutual) | Allg. Best. Abschnitt C VI, Nr. 4 | echocardiography 422–424 not billable side by side |
| 4 | Ausschluss (mutual) | Allg. Best. Abschnitt C VIII Nr. 4 + Anm. 448/449 | 448/449 ↔ 56 — mutual because the two official sentences contradict each other, see §6 |
| 2 | Ausschluss (mutual) | Allg. Best. Abschnitt B VII, Nr. 4 | 100 ↔ 101 |
| 2 | Ausschluss (mutual) | Allg. Best. Abschnitt O II, Nr. 2 | 5473 ↔ 5481 |
| 6 | Steigerungssatz | Allg. Best. Abschnitt B V (E–J, K 2) | E, F, G, H, J, K 2 capped at 1,0× |
| 5 | Steigerungssatz | Allg. Best. Abschnitt B V (A–D, K 1) | A, B, C, D, K 1 capped at 1,0× |
| 5 | Steigerungssatz | Allg. Best. Abschnitt O II (Ergänzungsleistungen) | 5480–5485 capped at 1,0× |
| 2 | Steigerungssatz | Allg. Best. Abschnitt B VII, Nr. 5 | 100, 101 capped at 1,0× |

**GOÄ 102 ceded.** The B VII Nr. 5 sentence also caps 102, and `cap_auto_102` already does, from
the identical wording in 102's own Anmerkung. `app/solvers/souffle_facts.py` emits one fact per
row, so two rows capping one Ziffer would leave it to fact ordering which `rule_id` a finding
cites. The generator yields to whatever is already there and prints what it ceded. The same is
true, and printed the same way, for the Abschnitt C VI and C VIII factor sentences: 401, 404–406
and 440–449 are capped at 1,0× already.

**Why `enforced_rule_count` rose by less than the row count.** 543 rows in, `enforced` up 402. The
difference is `RuleStore.redundant`: a batch-3 row asserting an edge an auto-extracted rule
already asserts is deduped out of the enforcement list (the manual citation wins) and stays in the
denominator. That is the designed behaviour, and the delta is itself a signal — 171 redundant
rules means 171 edges where a hand-read provision and a machine-read Anmerkung independently
agree.

---

## 4. Held out, and why (no guessing)

Of the 66 constraint sentences in the 50 Allgemeine Bestimmungen and the 29 unencoded Ziffer
annotations, **40 were held out in full and 2 in part**. All 42 are transcribed as data, with a
verbatim fragment of each, in `apps/engine/tests/test_batch3_quarantine.py`, which asserts three
things: no shipped rule cites one of them, the pairs they would have produced draw no batch-3
block from the real engine, and every fragment is verbatim in the official source (so a typo here
cannot turn a check into a no-op that passes forever).

**Scope is an Abschnitt, not a list of numbers** (4 sentences, one of them a limb of an encoded
one) — GOÄ 435's "Leistungen nach den Abschnitten C III und M" limb, GOÄ 437's "Abschnitt M mit
Ausnahme von M III 13 und M IV", GOÄ 793, and Abschnitt B's "neben Leistungen nach den Abschnitten
C bis O". This repo has no subsection boundary table, and expanding one wrong would touch hundreds
of positions. Unchanged from batch 1's open question §6.2.

**Conditioned on something an invoice does not carry** (13 sentences) — who rendered the service
(Zuschläge B–D for Krankenhausärzte; Besuchsgebühren 48/50/51 for Beleg- and Krankenhausärzte),
which joint (Abschnitt L III's 2102/2104/… sentence), where the analysis ran (3500–3532), which
specimen (GOÄ 4851, held by batch 1 too), what was injected (GOÄ 261), why a catheter was placed
(GOÄ 1730), a later admission (Zuschläge 442–449).

**A window this engine cannot evaluate** (9 sentences) — `QuantityLimitRule.window` only ever
evaluates `behandlungsfall`, so "je Sitzung" (sonography 401–424, angiography, CT 5369–5375, MRI
5700–5735, interventional 5345–5356), "je Behandlungstag" (infusions 270–287), "je Basisleistung"
(Ergänzungsleistungen 5480–5485) and "insgesamt" (radiology 5011/5021/…) are all held. This is
batch 2 §4's line, redrawn rather than relitigated.

**The other side is described, not numbered** (9 sentences, plus the Impfpaß limb of an encoded
one) — "eine operative Leistung" (the Verband provision; the four pairs that *are* named live in
`zielleistung.manual.csv`), "Gefäßpunktionen", the contrast-medium acts, the Impfpaß entry,
Befundmitteilung, "anderen Leistungen" (GOÄ 61, held by batch 1 too), Prostaglandin-Gel
(likewise), and the qualitative/quantitative immunofluorescence provisions, which relate two
*methods* across a whole Katalog with no Ziffer named.

**Real, unconditional, numbered — and not an exclusion** (6 sentences). A fee *reduction* ("um den
Vergütungssatz nach Nummer 2990 oder 3135 zu kürzen"), a keep-the-dearest selection over a set
(Anästhesie: "nur die jeweils höchstbewertete"), a keep-the-cheaper one (equivalent lab methods),
the Zielleistungsprinzip stated in general rather than as pairs, and a cumulative cap across six
codes (4666–4671 — the shape batch 2 quarantined GOÄ 391 for). Each needs a
rule table this engine does not have. This is the same schema question batch 1 §6.1 and ADR-002
opened, now with five more shapes on it.

**Letter-suffixed siblings inside plainly-numbered ranges.** GOÄ 250a, 265a and 605a sit
numerically inside GOÄ 435's ranges ("250 bis 268", "600 bis 609") and are written nowhere in the
sentence. Reading them in is an interpretation, and the same sentence shows the GOÄ naming one
explicitly where it means to — "270 bis 286a", whose endpoint **is** encoded. Under-blocking is
the safe direction; both halves are pinned by tests so a later batch changes this deliberately.

---

## 5. Coverage classification — what "covered" means, per Ziffer

"516 Ziffern under rule" is one number covering three different situations, and the brief is right
that they should not be reported as one. `apps/engine/scripts/classify_batch3_coverage.py`
computes the split for all 254 Ziffern batch 3 names, into
`docs/content/batch3-coverage-classification.json`:

| Classification | Ziffern | What it means |
|---|---|---|
| `FULLY_VERIFIED` | 10 | every constraint sentence naming it is encoded, **and** a golden test in `tests/test_coverage_sprint_batch3.py` claims it against the real engine |
| `MECHANICAL_ONLY` | 148 | every constraint sentence naming it is encoded; no golden test names it. Simple exclusion edges and factor caps, no complex logic, resting on the citation and the regression suite |
| `PARTIAL` | 96 | at least one constraint sentence naming it was held out (§4). Under rule *and* under-checked — the only one of the three where taking "covered" at face value misleads |

The label is computed, not asserted: for each Ziffer it compares every constraint sentence in the
official source that names it against the quotes of every enforced rule that names it, and
`PARTIAL` carries the specific leftover sentences rather than a hedge. A Ziffer whose *only*
constraint is one this engine cannot express never reaches the script at all — nothing was encoded
for it, so it is in neither this table nor the coverage figure. That is the honest outcome, and
the reason `PARTIAL` is about leftovers rather than absence.

**The classifier is deliberately strict**, and its errors run one way. It counts a sentence as
encoded only when a rule naming that Ziffer quotes it, so a provision the GOÄ prints twice in
slightly different words can be enforced through one copy and still counted against the other.
That inflates `PARTIAL` and understates coverage — the safe direction for an honesty metric, and
the artefact names every sentence it considers missing, so any individual case is checkable.

---

## 6. Two findings on the existing corpus

Neither is a batch-3 defect. Both were turned up by cross-checking batch 3's own rows and are
recorded here because they bear on rules that are enforced today.

### 6.1 · F1 — 35 hand-curated exclusions from batch 1 point the wrong way

`scripts/deterministic_rule_parser.py` names the hazard in its own docstring:

> A and D put the forbidden Ziffer first; B and E put it last. Getting that backwards is precisely
> the mistake the extractor can make and a reader can miss.

In a **form A** sentence — "Die Leistung nach Nummer 260 ist neben Leistungen nach den Nummern 355
bis 361 … nicht berechnungsfähig" — the *subject* is the position that may not be charged. The
extractor gets this right (`excl_auto_626_355`, from the identical shape, stores 626 → 355). Batch
1 entered 35 such rows as if they were form B, and the corpus now disagrees with itself about
which way this shape points.

Two distinct harms, both reproduced against the real engine:

* **The wrong position is suppressed.** GOÄ 260 beside 355 drops 355 and keeps 260; the sentence
  says the opposite. Same for `excl_man_A_B`, `excl_man_F_45`, `excl_man_H_52` and their
  siblings — 31 rows.
* **A correct rule is silenced.** For `excl_man_48_1`, `_48_50`, `_48_51`, `_48_52` a correct
  reverse rule already exists (`excl_auto_50_48`, …), and LAYER 3 of `logic/datalog/goae_rules.dl`
  only decides a one-way edge when the opposite edge is absent (`!exclusion(_, B, A, _)`). With
  both present neither fires: **GOÄ 48 beside GOÄ 50 is currently caught by nothing at all.**

`apps/engine/tests/test_batch3_direction.py` records the finding as executable data, split by what
proves it — 17 rows the parser reads and contradicts, 18 whose blocked side is named by Buchstabe
so the parser returns no verdict and the evidence is a person reading German. It also asserts that
**no other** hand-curated rule is inverted, which is what makes the finding's completeness
falsifiable, and that every readable batch-3 row points the way its own sentence does.

**Fixed in PR #87 — merged, and this batch is rebased on it.** Flipping an enforced exclusion
changes which position a real invoice loses, so it went in as its own change rather than inside a
543-row data commit. `docs/content/f1-exclusion-direction.md` carries the 35 ids, the euro deltas,
the golden-suite and deployed-invoice analysis, and a corpus-wide regression test
(`tests/test_exclusion_direction.py`) that checks all one-way exclusions rather than the 35.

**What the rebase did to this batch's own tests.** `tests/test_batch3_direction.py` recorded the
finding as executable data — the corpus *before* the fix — which is what made it falsifiable and
also what made it fail the moment the fix landed, by design. The three entries that described the
defect (`INVERTED_CONFIRMED_BY_PARSER`, `INVERTED_READ_BY_HAND` and the tests over them) are gone:
the finding is closed and `test_exclusion_direction.py` supersedes them over the whole corpus. What
remains guards *this* batch's generator, which that test knows nothing about.

The traffic goes the other way too. Batch 3's rules brought two sentence shapes into the
corpus-wide check that did not exist when it was written — the Anmerkung to GOÄ 435 and the
Abschnitt M III 9 provision — so both are added to its `HAND_READ` with the reading that justifies
them. GOÄ 435 also forced a better guard there: it states **182 exclusions in one sentence**, and a
row-weighted "how much is machine-confirmed" ratio fell from 94 % to 80 % without a single extra
sentence going unchecked. That ratio was measuring fan-out, not coverage, so it now counts
**distinct sentences** (110 of 123, 89 %) and is paired with a hard cap on how many sentences may
rest on a written reading at all — thirteen is a list a reviewer works through, a hundred is a
formality.

### 6.2 · F2 — the GOÄ contradicts itself about GOÄ 448/449 beside GOÄ 56

Allgemeine Bestimmungen zu Abschnitt C VIII, Nr. 4: *"Neben den Leistungen nach Nummer 448 oder
449 darf die Leistung nach Nummer 56 nicht berechnet werden."* — GOÄ 56 loses.

Anmerkung zu Nummer 448: *"Der Zuschlag nach Nummer 448 ist neben den Leistungen nach den Nummern
1 bis 8 und 56 sowie dem Zuschlag nach Nummer 449 nicht berechnungsfähig."* — GOÄ 448 loses.

Both are the official text. They agree the two positions may not stand together and differ on
which is dropped. Encoding either as one-way picks a winner the GOÄ does not pick; encoding both
leaves LAYER 3 firing neither, for the reason F1 just described. So the pair ships as `direction:
mutual`, which says exactly what is certain — that this is a conflict — and hands the choice to
the ASP arbitrator, where it surfaces on the report instead of being resolved silently in the
data. The rest of each Anmerkung (448/449 against 1–8, and 448 ↔ 449) is unambiguous and is
encoded as written.

---

## 7. Tests, and what they are for

* `tests/test_coverage_sprint_batch3.py` (30) — the golden tests, against the **real** corpus
  through the `souffle` fixture. Positive, negative and boundary for each major provision. The
  boundary cases are the ones that earn their keep: "410 bis 418" and "410 bis 420" produce
  identical-looking CSV and pass every citation check, and differ only in whether GOÄ 420 is
  silently unbillable beside every single-organ ultrasound.
* `tests/test_batch3_citations.py` (13) — re-derives `allgemeine_bestimmungen.json` from
  `data/raw/goae_source.xml` **in-process** and compares, re-checks the raw file against its
  manifest SHA-256, then asserts every quote is verbatim in the artefact or the catalog. Without
  the re-derivation, "the quote is in the JSON file" would only say two files in this repo agree
  with each other. Also runs both generators' `--check`.
* `tests/test_batch3_direction.py` (6) — §6's cross-check.
* `tests/test_batch3_quarantine.py` (26) — §4, enforced.

Full `apps/engine` suite (run from `apps/engine`, not the monorepo root): **2,382 passed, 7
skipped, 0 failed** — the count includes the 36 tests PR #87 added to `main`. `python scripts/engine_cli.py check`: `1342 of 1523 enforced`, **0 dangling**
references — every Ziffer named by a new rule, including `286a`, `K1` and `3055`, resolves in the
loaded catalog.

**Golden snapshots.** `scripts/refreeze_rule_coverage.py` reported **METADATA ONLY for all nine**:
543 new exclusion and factor-cap rules moved no Ziffer, factor, amount or proof on any frozen
case. 60 leaves updated, all of them rule counts or the warning sentence that quotes them.

While doing it, two leaves the script's `ALLOWED` list did not cover —
`total_constraint_rule_count` and `total_constraint_rules` — were added to it. Batch 1 and batch 2
each patched those same six snapshots by hand because the guard refused them, which is the one
habit the script exists to remove, and doing it beside a guard that had refused the edit is worse
than either: the guard looked like it had passed. They are counts of rules loaded, in the same
sense as every other entry in that list.

`rules_hash()` moved (525 + 18 rows across two CSVs), so `CASE_A_RECEIPT_PREFIX`
(`tests/golden/oracle.py`) and `receipt_hash_prefix`
(`tests/golden/case_a_known_answer/expected.json`) were re-pinned, following the batch-1 and
batch-2 precedent: confirmed stable across two separate processes before either value was touched.
`logic_version` (`83fae8e7f0369c25`) is unchanged — nothing under `logic/` was edited, and batch 3
adds no new rule family, no new predicate and no DSL.

---

## 8. Numbers, and how to regenerate them

Baseline is `main` **after** the F1 exclusion-direction fix (PR #87), which this batch is rebased
on. F1 moved `enforced_rule_count` 944 → 940 and `redundant` 30 → 34 without touching coverage; the
"before" column is that state, not the pre-F1 one.

| | Before batch 3 (main @ F1) | After |
|---|---|---|
| Ziffern named by ≥ 1 enforced rule | 383 / 2,343 (16.35 %) | **516 / 2,343 (22.02 %)** |
| `enforced_rule_count` | 940 | **1,342** |
| `total_constraint_rule_count` | 980 | **1,523** |
| Enforced exclusions | 908 | 1,292 |
| Enforced mutual pairs | 54 | 117 |
| Enforced factor caps | 27 | 45 |
| Redundant (verified, edge already covered) | 34 | 175 |

Unchanged on purpose: the **definition**. A Ziffer is "under rule" when an *enforced* exclusion,
Zielleistung, specificity or factor-cap rule names it — exactly what
`tests/test_published_numbers.py` computes and what batches 1 and 2 used. The four ADR-002
families (quantity, age, sex, time) are still outside the denominator; folding them in would add
23 more Ziffern and remains the product decision nobody has made (batch 2 §5).

```
# the rules and the artefacts, regenerated; all three are byte-stable
cd apps/engine
python scripts/extract_allgemeine_bestimmungen.py     # 50 provisions out of the raw XML
python scripts/build_batch3_rules.py                  # 525 exclusion + 18 cap rows, coverage delta
python scripts/classify_batch3_coverage.py            # §5's per-Ziffer split

# the engine's own view
python scripts/engine_cli.py check

# §2's ranking table
python3 - <<'PY'
import json, csv, collections
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
cat = json.loads(Path("data/catalogs/goae_current/goae.official.json").read_text())
Z = {r["ziffer"]: r for r in cat["ziffern"]}
punktwert = Decimal(str(cat["punktwert_cent"])) / 100
degree = collections.Counter()
for name, cols in (("exclusions.manual.csv", ("from_ziffer", "to_ziffer")),
                   ("factor_caps.csv", ("ziffer",))):
    for row in csv.DictReader(Path("data/rules", name).open(encoding="utf-8")):
        if "_b3_" in row["rule_id"]:
            for col in cols:
                degree[row[col]] += 1
scored = []
for ziffer, edges in degree.items():
    punkte = Z[ziffer].get("punkte") or 0
    eur = (Decimal(punkte) * punktwert * Decimal("2.3")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    scored.append((edges * float(eur), ziffer, Z[ziffer]["category"], punkte, eur, edges))
for rank, row in enumerate(sorted(scored, reverse=True)[:50], 1):
    print(rank, *row[1:])
PY
```

---

## 9. Open questions for a human (not guessed)

1. **F1's 35 inverted rules** (§6.1) — **closed.** Fixed in PR #87
   (`docs/content/f1-exclusion-direction.md`), merged, and this batch is rebased on it. §6.1
   records what the rebase changed in both directions.
2. **F2's contradictory pair, GOÄ 448/449 beside GOÄ 56 (§6.2) — still open, and a decision only a
   human should make.** Two sentences of the official text disagree about which position loses,
   and this batch ships `direction: mutual`, which asserts only what both sentences agree on —
   that the two may not stand together — and hands the choice to the ASP arbitrator, where it
   surfaces on the report as a conflict.

   That is deliberately *not* a resolution. A reviewer with the standard commentaries may
   conclude that one of the two sentences governs (the Allgemeine Bestimmung is the later and more
   specific provision; the Anmerkung is printed under the Ziffer it restricts), in which case the
   pair becomes a one-way exclusion and the mutual rows are replaced. Until somebody decides that
   on the law rather than on the data, the engine says "these two conflict" instead of picking a
   winner the GOÄ does not pick. The two sentences are quoted in full in §6.2, and
   `tests/test_coverage_sprint_batch3.py` pins the current mutual behaviour, so a change of mind
   is a visible edit rather than a drift.
3. **Should `import_goae.py` carry the Allgemeine Bestimmungen into the catalog**, rather than a
   sibling artefact? It would put the batch-3 citations under the same `citation_verbatim` check
   as everything else, at the cost of a schema for "text that governs a range of Ziffern" and a
   re-pin of the catalog snapshot identity. Deliberately not decided inside a data batch.
4. **The five constraint shapes with no rule table** (§4: fee reduction, keep-the-dearest,
   keep-the-cheaper, general Zielleistung, cross-code cumulative cap). Together with batch 1 §6.1
   and ADR-002, this is now a list, not an exception — worth deciding as a group.
5. **Abschnitt boundaries** (§4, batch 1 §6.2) — unchanged, and now blocking four provisions
   instead of two.
