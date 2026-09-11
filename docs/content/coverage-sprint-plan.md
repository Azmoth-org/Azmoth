# GOÄ coverage sprint — plan and batch 1 report

Internal engineering reference. Stand: 2026-09-12. Every number below is either read live off
`data/rules/*.csv` + `data/catalogs/goae_current/goae.official.json`, or printed by
`apps/engine/scripts/engine_cli.py check`. Nothing here is typed from memory — regenerate with the
script named in each section if in doubt.

**Definition of "covered."** A Ziffer is "under rule" if it is named as `from_ziffer`/`to_ziffer`
in an enforced (verified) row of `exclusions.csv`/`exclusions.manual.csv`, as `parent_ziffer`/
`child_ziffer` in `zielleistung.csv`/`zielleistung.manual.csv`, as `specific_ziffer`/
`general_ziffer` in `specificity.csv`, or as `ziffer` in `factor_caps.csv`. This is exactly what
`test_the_marketing_site_quotes_the_engine_and_not_a_memory` (in
`apps/engine/tests/test_published_numbers.py`) computes, so the marketing figure and this document
can never silently disagree.

---

## 1. Inventory: Ziffern with zero enforced rules

Before this sprint: **358 / 2,343** Ziffern (15.28%) were named by at least one enforced rule.
Everything else — 1,985 positions — carried no exclusion, Zielleistung, specificity or factor-cap
rule at all.

Scanning every uncovered Ziffer's `official_text` and `annotations` for six mechanical-constraint
vocabularies (regexes in the appendix) found **114** with at least one hit. The other ~1,871
uncovered Ziffern have no annotation text that mechanically implies a rule at all — they are
uninstrumented, not incorrectly instrumented, and adding a rule to any of them without a supporting
sentence would be exactly the kind of guess this sprint is not allowed to make.

By chapter (uncovered Ziffern / total Ziffern in that chapter, before this sprint):

| Chapter | Uncovered / Total | Title |
|---|---|---|
| L | 675 / 676 | Chirurgie, Orthopädie |
| M | 412 / 422 | Laboratoriumsuntersuchungen |
| J | 140 / 153 | Hals-, Nasen-, Ohrenheilkunde |
| C | 128 / 173 | Nichtgebietsbezogene Sonderleistungen (Ultraschall lives here — see note) |
| I | 121 / 132 | Augenheilkunde |
| K | 114 / 133 | Urologie |
| O | 107 / 206 | Strahlendiagnostik, Nuklearmedizin, MRT, Strahlentherapie |
| H | 95 / 103 | Geburtshilfe und Gynäkologie |
| F | 85 / 137 | Innere Medizin, Kinderheilkunde, Dermatologie |
| D | 31 / 33 | Anästhesieleistungen |
| B | 30 / 64 | Grundleistungen und allgemeine Leistungen |
| N | 14 / 15 | Histologie, Zytologie und Zytogenetik |
| G | 13 / 44 | Neurologie, Psychiatrie und Psychotherapie |
| E | 11 / 43 | Physikalisch-medizinische Leistungen |
| P | 9 / 9 | Sektionsleistungen |

**Note on "C, M, O, E, U".** The task brief names five chapters a billing office touches daily.
This catalog snapshot's own chapter letters are B–P (no "U"); GOÄ's Ultraschalldiagnostik Ziffern
(401–424) are filed inside chapter **C** (Nichtgebietsbezogene Sonderleistungen), not as their own
letter. Read "C, M, O, E, U" below as "C (Ultraschall included), M, O, E" — a scoping note, not a
guess about legal content.

Of the 114 flagged Ziffern, by constraint category (a Ziffer can carry more than one):

| Category | Count | What it means |
|---|---|---|
| Mengenbegrenzung | 62 | a quantity/frequency ceiling ("je Sitzung", "höchstens X-mal", banded test counts) |
| Ausschluss | 27 | "nicht neben" / "nicht berechnungsfähig" naming another position |
| Alter | 19 | age-gated wording ("Lebensjahr", "Neugeborene", "Säugling", "Kind") |
| Geschlecht | 9 | sex-specific wording ("männlich", "weiblich", "Frau", "Mann") |
| Steigerung/Begründung | 3 | factor-ceiling or justification-duty wording |
| Zeitbeziehung | 0 | "am selben Tag" / "innerhalb von …" — none of the 114 hits used this phrasing |

By chapter, before this sprint:

`C: 29 · F: 16 · B: 13 · L: 12 · K: 11 · O: 8 · E: 6 · M: 6 · I: 4 · J: 4 · H: 3 · G: 1 · N: 1`

---

## 2. Prioritization

Ranked by mechanical-constraint density first (a Ziffer flagged for two categories outranks one
flagged for one), chapters C/M/O/E prioritized on ties, per the brief. Only 114 Ziffern were
flagged at all (§1), so "top 100" is effectively all of them minus the 14 lowest-ranked; the full
114 are listed so the ranking is checkable rather than asserted. "Batch 1?" marks the rows this
sprint actually drafted (§3) — most of the top of the list is Mengenbegrenzung/Alter/Geschlecht,
which the current schema cannot express at all (§2a, §6), so batch 1 skips down the ranking to the
highest-ranked rows the schema *can* express.

| Rank | Ziffer | Kap. | Constraints | Text | Batch 1? |
|---|---|---|---|---|---|
| 1 | 382 | C | Mengenbegrenzung, Ausschluss | Epikutantest, je Test (51. bis 100. Test je Behandlungs |  |
| 2 | 387 | C | Mengenbegrenzung, Ausschluss | Pricktest, je Test (41. bis 80. Test je Behandlungsfall |  |
| 3 | 391 | C | Mengenbegrenzung, Ausschluss | Intrakutantest, jeder weitere Test |  |
| 4 | 5442 | O | Mengenbegrenzung, Ausschluss | Statische Nierenszintigraphie | yes |
| 5 | 27 | B | Geschlecht, Ausschluss | Untersuchung einer Frau zur Früherkennung von Krebserkr | yes |
| 6 | 4851 | N | Geschlecht, Ausschluss | Zytologische Untersuchung zur Krebsdiagnostik als Durch |  |
| 7 | 209 | C | Mengenbegrenzung | Großflächiges Auftragen von Externa (z.B. Salben, Creme |  |
| 8 | 260 | C | Ausschluss | Legen eines arteriellen Katheters oder eines zentralen  | yes |
| 9 | 261 | C | Ausschluss | Einbringung von Arzneimitteln in einen parenteralen Kat |  |
| 10 | 263 | C | Mengenbegrenzung | Subkutane Hyposensibilisierungsbehandlung (Desensibilis |  |
| 11 | 264 | C | Mengenbegrenzung | Injektions- und/oder Infiltrationsbehandlung der Prosta |  |
| 12 | 265 | C | Mengenbegrenzung | Auffüllung eines subkutanen Medikamentenreservoirs oder |  |
| 13 | 266 | C | Mengenbegrenzung | Intrakutane Reiztherapie (Quaddelbehandlung), je Sitzun |  |
| 14 | 267 | C | Mengenbegrenzung | Medikamentöse Infiltrationsbehandlung im Bereich einer  |  |
| 15 | 268 | C | Mengenbegrenzung | Medikamentöse Infiltrationsbehandlung im Bereich mehrer |  |
| 16 | 281 | C | Alter | Transfusion der ersten Blutkonserve (auch Frischblut) o |  |
| 17 | 283 | C | Alter | Infusion in die Aorta bei einem Neugeborenen mittels tr |  |
| 18 | 380 | C | Mengenbegrenzung | Epikutantest, je Test (1. bis 30. Test je Behandlungsfa |  |
| 19 | 381 | C | Mengenbegrenzung | Epikutantest, je Test (31. bis 50. Test je Behandlungsf |  |
| 20 | 385 | C | Mengenbegrenzung | Pricktest, je Test (1. bis 20. Test je Behandlungsfall) |  |
| 21 | 386 | C | Mengenbegrenzung | Pricktest, je Test (21. bis 40. Test je Behandlungsfall |  |
| 22 | 388 | C | Mengenbegrenzung | Reib-, Scratch- oder Skarifikationstest, je Test (bis z |  |
| 23 | 390 | C | Mengenbegrenzung | Intrakutantest, je Test (1. bis 20. Test je Behandlungs |  |
| 24 | 408 | C | Mengenbegrenzung | Transluminale Sonographie von einem oder mehreren Blutg |  |
| 25 | 412 | C | Alter | Ultraschalluntersuchung des Schädels bei einem Säugling |  |
| 26 | 413 | C | Alter | Ultraschalluntersuchung der Hüftgelenke bei einem Säugl |  |
| 27 | 420 | C | Mengenbegrenzung | Ultraschalluntersuchung von bis zu drei weiteren Organe |  |
| 28 | 430 | C | Mengenbegrenzung | Extra- oder intrathorakale Elektro-Defibrillation und/o |  |
| 29 | 435 | C | Ausschluss | Stationäre intensivmedizinische Überwachung und Behandl |  |
| 30 | 437 | C | Ausschluss | Laboratoriumsuntersuchungen im Rahmen einer Intensivbeh |  |
| 31 | 250a | C | Alter | Kapillarblutentnahme bei Kindern bis zum vollendeten 8. |  |
| 32 | 265a | C | Mengenbegrenzung | Auffüllung eines Hautexpanders, je Sitzung |  |
| 33 | 4572 | M | Mengenbegrenzung | Beta-hämolysierende Streptokokken |  |
| 34 | 4573 | M | Mengenbegrenzung | Escherichia coli |  |
| 35 | 4574 | M | Mengenbegrenzung | Salmonellen |  |
| 36 | 4575 | M | Mengenbegrenzung | Shigellen |  |
| 37 | 4576 | M | Mengenbegrenzung | Untersuchungen mit ähnlichem methodischem Aufwand Die u |  |
| 38 | 4601 | M | Ausschluss | Untersuchung zum Nachweis von Bakterientoxinen durch In |  |
| 39 | 5135 | O | Mengenbegrenzung | Brustorgane-Übersicht, in einer Ebene |  |
| 40 | 5190 | O | Mengenbegrenzung | Bauchübersicht, in einer Ebene oder Projektion |  |
| 41 | 5260 | O | Ausschluss | Röntgenuntersuchung natürlicher, künstlicher oder krank |  |
| 42 | 5265 | O | Mengenbegrenzung | Mammographie einer Seite, in einer Ebene |  |
| 43 | 5378 | O | Ausschluss | Computergesteuerte Tomographie zur Bestrahlungsplanung  | yes |
| 44 | 5851 | O | Mengenbegrenzung | Ganzkörperstrahlenbehandlung vor Knochenmarktransplanta |  |
| 45 | 5854 | O | Steigerung/Begründung | Tiefen-Hyperthermie, je Fraktion | yes |
| 46 | 530 | E | Mengenbegrenzung | Kalt- oder Heißpackung(en) oder heiße Rolle, je Sitzung |  |
| 47 | 558 | E | Mengenbegrenzung | Apparative isokinetische Muskelfunktionstherapie, je Si |  |
| 48 | 565 | E | Mengenbegrenzung | Photochemotherapie, je Sitzung |  |
| 49 | 566 | E | Alter | Phototherapie eines Neugeborenen, je Tag |  |
| 50 | 567 | E | Mengenbegrenzung | Phototherapie mit selektivem UV-Spektrum, je Sitzung |  |
| 51 | 569 | E | Mengenbegrenzung | Photo-Patch-Test (belichteter Läppchentest), bis zu dre |  |
| 52 | 61 | B | Ausschluss | Beistand bei der ärztlichen Leistung eines anderen Arzt |  |
| 53 | 77 | B | Mengenbegrenzung | Schriftliche, individuelle Planung und Leitung einer Ku |  |
| 54 | 96 | B | Steigerung/Begründung | Schreibgebühr, je Kopie | yes |
| 55 | A | B | Ausschluss | Zuschlag für außerhalb der Sprechstunde erbrachte Leist | yes |
| 56 | C | B | Ausschluss | Zuschlag für in der Zeit zwischen 22 und 6 Uhr erbracht | yes |
| 57 | D | B | Ausschluss | Zuschlag für an Samstagen, Sonn- oder Feiertagen erbrac | yes |
| 58 | E | B | Ausschluss | Zuschlag für dringend angeforderte und unverzüglich erf | yes |
| 59 | F | B | Ausschluss | Zuschlag für in der Zeit von 20 bis 22 Uhr oder 6 bis 8 | yes |
| 60 | G | B | Ausschluss | Zuschlag für in der Zeit zwischen 22 und 6 Uhr erbracht | yes |
| 61 | H | B | Ausschluss | Zuschlag für an Samstagen, Sonn- oder Feiertagen erbrac | yes |
| 62 | K1 | B | Alter | Zuschlag zu Untersuchungen nach Nummer 5, 6, 7 oder 8 b |  |
| 63 | K2 | B | Alter | Zuschlag zu den Leistungen nach Nummer 45, 46, 48, 50,  |  |
| 64 | 699 | F | Mengenbegrenzung | Infrarotkoagulation im Enddarmbereich, je Sitzung |  |
| 65 | 706 | F | Mengenbegrenzung | Licht- oder Laserkoagulation(en) zur Beseitigung von St |  |
| 66 | 740 | F | Mengenbegrenzung | Kryotherapie der Haut, je Sitzung |  |
| 67 | 741 | F | Mengenbegrenzung | Verschorfung mit heißer Luft oder heißen Dämpfen, je Si |  |
| 68 | 742 | F | Mengenbegrenzung | Epilation von Haaren im Gesicht durch Elektrokoagulatio |  |
| 69 | 743 | F | Mengenbegrenzung | Schleifen und Schmirgeln und/oder Fräsen von Bezirken d |  |
| 70 | 744 | F | Mengenbegrenzung | Stanzen der Haut, je Sitzung |  |
| 71 | 747 | F | Mengenbegrenzung | Setzen von Schröpfköpfen, Blutegeln oder Anwendung von  |  |
| 72 | 750 | F | Mengenbegrenzung | Auflichtmikroskopie der Haut (Dermatoskopie), je Sitzun |  |
| 73 | 755 | F | Mengenbegrenzung | Hochtouriges Schleifen von Bezirken der Haut bei schwer |  |
| 74 | 758 | F | Mengenbegrenzung | Sticheln oder Öffnen und Ausquetschen von Aknepusteln,  |  |
| 75 | 761 | F | Steigerung/Begründung | UV-Erythemschwellenwertbestimmung - einschließlich Nach |  |
| 76 | 764 | F | Mengenbegrenzung | Verödung (Sklerosierung) von Krampfadern oder Hämorrhoi |  |
| 77 | 766 | F | Mengenbegrenzung | Ligaturbehandlung von Hämorrhoiden einschließlich Prokt |  |
| 78 | 781 | F | Mengenbegrenzung | Bougierung der Speiseröhre, je Sitzung |  |
| 79 | 793 | F | Ausschluss | Ärztliche Betreuung eines Patienten bei kontinuierliche |  |
| 80 | 842 | G | Mengenbegrenzung | Apparative isokinetische Muskelfunktionsdiagnostik |  |
| 81 | 1040 | H | Alter | Reanimation eines asphyktischen Neugeborenen durch appa |  |
| 82 | 1056 | H | Ausschluss | Abbruch einer Schwangerschaft ab der 13. Schwangerschaf |  |
| 83 | 1063 | H | Alter | Vaginoskopie bei einem Kind bis zum vollendeten 10. Leb |  |
| 84 | 1215 | I | Mengenbegrenzung | Bestimmung von Fernrohrbrillen oder Lupenbrillen, je Si |  |
| 85 | 1294 | I | Alter | Sondierung des Tränennasengangs bei Säuglingen und Klei |  |
| 86 | 1323 | I | Mengenbegrenzung | Elektrolytische Epilation von Wimpernhaaren, je Sitzung |  |
| 87 | 1365 | I | Mengenbegrenzung | Lichtkoagulation zur Verhinderung einer Netzhautablösun |  |
| 88 | 1429 | J | Mengenbegrenzung | Kauterisation im Naseninnern, je Sitzung |  |
| 89 | 1473 | J | Ausschluss | Plastische Rekonstruktion der Stirnhöhlenvorderwand, au | yes |
| 90 | 1532 | J | Ausschluss | Endobronchiale Behandlung mit weichem Rohr |  |
| 91 | 1558 | J | Mengenbegrenzung | Stimmtherapie bei Kehlkopflosen (Speiseröhrenersatzstim |  |
| 92 | 1702 | K | Geschlecht | Dehnung der männlichen Harnröhre mit filiformen Bougies |  |
| 93 | 1703 | K | Geschlecht | Unblutige Fremdkörperentfernung aus der männlichen Harn |  |
| 94 | 1704 | K | Geschlecht | Operative Fremdkörperentfernung aus der männlichen Harn |  |
| 95 | 1708 | K | Geschlecht | Kalibrierung der männlichen Harnröhre |  |
| 96 | 1709 | K | Geschlecht | Kalibrierung der weiblichen Harnröhre |  |
| 97 | 1711 | K | Geschlecht | Unblutige Fremdkörperentfernung aus der weiblichen Harn |  |
| 98 | 1724 | K | Mengenbegrenzung | Plastische Operation zur Beseitigung einer Striktur der |  |
| 99 | 1782 | K | Geschlecht | Transurethrale Resektion des Harnblasenhalses bei der F |  |
| 100 | 1800 | K | Mengenbegrenzung | Zertrümmerung und Entfernung von Blasensteinen unter en |  |
| 101 | 1815 | K | Ausschluss | Schlingenextraktion oder Versuch der Extraktion von Har |  |
| 102 | 1860 | K | Mengenbegrenzung | Extrakorporale Stoßwellenlithotripsie - einschließlich  |  |
| 103 | 2005 | L | Ausschluss | Versorgung einer großen und/oder stark verunreinigten W |  |
| 104 | 2065 | L | Mengenbegrenzung | Abtragung ausgedehnter Nekrosen im Hand- oder Fußbereic |  |
| 105 | 2090 | L | Mengenbegrenzung | Spülung bei eröffnetem Sehnenscheidenpanaritium, je Sit |  |
| 106 | 2429 | L | Alter | Eröffnungen disseminierter Abszeßbildungen der Haut (z. |  |
| 107 | 2440 | L | Mengenbegrenzung | Operative Entfernung eines Naevus flammeus, je Sitzung |  |
| 108 | 2505 | L | Alter | Operation des akuten subduralen Hygroms oder Hämatoms b |  |
| 109 | 2525 | L | Alter | Operation der prämaturen Schädelnahtsynostose (Kraniost |  |
| 110 | 2571 | L | Alter | Operation einer Mißbildung am Rückenmark oder an der Ca |  |
| 111 | 3127 | L | Alter | Extrapleurale Operation der Ösophagusatresie beim Klein |  |
| 112 | 3171 | L | Alter | Operative Beseitigung von Lageanomalien innerhalb des M |  |
| 113 | 3189 | L | Alter | Operative Beseitigung von Atresien und/oder Stenosen de |  |
| 114 | 3287 | L | Alter | Operation der Omphalozele (Nabelschnurhernie) oder der  |  |

### 2a. Why batch 1's picks aren't the top of this list

Ranks 1–3, 6–7, 9–22 and most of the rest are Mengenbegrenzung/Alter/Geschlecht — real, citable
constraints with no table to put them in yet (§6). Batch 1 (marked "yes" above) is every rank in
this list whose constraint is Ausschluss, Zielleistung, specificity or factor-cap *and* whose
target Ziffern are named explicitly enough to encode without guessing (§4 lists what got skipped
even within that narrower set, and why).

Concretely: `exclusions` and `zielleistung` are from-Ziffer/to-Ziffer pairs, `specificity` is a
general/specific pair, `factor_caps` is a single-Ziffer ceiling. There is **no rule table for
Mengenbegrenzung (a quantity cap on repeating the same Ziffer), Alter, Geschlecht, or
Zeitbeziehung** — the four categories the brief calls out by name are, structurally, not something
this sprint could add without first extending `logic/datalog/goae_rules.dl`,
`app/rules/rule_store.py` and the ASP program. That is a schema decision, not a data-entry one, and
is listed as an open question in §6 rather than guessed into an ad hoc shape.

---

## 3. Batch 1 — 25 Ziffern

Every row cites the exact catalog sentence it encodes (`official_text`/`annotations` in
`data/catalogs/goae_current/goae.official.json`, unedited). All are added `verified: true`,
`source: manual_verification:coverage_sprint_batch1`, `verified_at: 2026-09-12` — hand-read this
sprint, not machine-extracted.

**Result: 358 → 383 Ziffern under rule (15.28% → 16.35%).** 86 new enforced rule rows (81
exclusion + 5 factor-cap); `total_constraint_rule_count` 894 → 980; `enforced_rule_count` 858 → 944.

| Source Ziffer | New rule(s) | Citation (`legal_basis`) |
|---|---|---|
| A (Zuschlag außerhalb Sprechstunde) | excludes B, C, D | "Der Zuschlag nach Buchstabe A ist neben den Zuschlägen nach den Buchstaben B, C und/oder D nicht berechnungsfähig." |
| C (Zuschlag 22–6 Uhr) | excludes B | "Neben dem Zuschlag nach Buchstabe C ist der Zuschlag nach Buchstabe B nicht berechnungsfähig." |
| E (Zuschlag dringend) | excludes F, G, H | "Der Zuschlag nach Buchstabe E ist neben Zuschlägen nach den Buchstaben F, G und/oder H nicht berechnungsfähig." (the same annotation's earlier clause excluding Nr. 45/46 carries an exception, "es sei denn … Belegarzt" — skipped, see §4) |
| F (Zuschlag 20–22/6–8 Uhr) | excludes 45, 46, 48, 52 | "Der Zuschlag nach Buchstabe F ist neben den Leistungen nach den Nummern 45, 46, 48 und 52 nicht berechnungsfähig." |
| G (Zuschlag 22–6 Uhr, Besuch) | excludes 45, 46, 48, 52, F | two annotation sentences, both unconditional |
| H (Zuschlag Sa/So/Feiertag, Besuch) | excludes 45, 46, 48, 52 | "Der Zuschlag nach Buchstabe H ist neben den Leistungen nach den Nummern 45, 46, 48 und 52 nicht berechnungsfähig." |
| 27 (Krebsfrüherkennung Frau) | excludes 1, 3, 5, 6, 7, 8, 297, 3500, 3511, 3650, 3652 | "Neben der Leistung nach Nummer 27 sind die Leistungen nach den Nummern 1, 3, 5, 6, 7, 8 297, 3500, 3511, 3650 und/oder 3652 nicht berechnungsfähig." |
| 96 (Schreibgebühr je Kopie) | factor cap 1.0 (also 95) | "Die Schreibgebühren nach den Nummern 95 und 96 sind … nur mit dem einfachen Gebührensatz berechnungsfähig." (the "nur neben 80/85/90" clause is a blanket allow-list, not a pairwise fact — skipped, see §4) |
| 260 (art./zentr. Katheter) | excludes 355–357, 360, 361, 626–632, 648 | "Die Leistung nach Nummer 260 ist neben Leistungen nach den Nummern 355 bis 361, 626 bis 632 und/oder 648 nicht berechnungsfähig." (358, 359 do not exist in this catalog snapshot and were not invented) |
| 1473 (Rekonstruktion Stirnhöhlenvorderwand) | excludes 1485 | "Neben der Leistung nach Nummer 1473 ist die Nummer 1485 nicht berechnungsfähig." |
| 5378 (CT Bestrahlungsplanung) | excludes 5370–5376 | "Neben oder anstelle der computergesteuerten Tomographie … sind die Leistungen nach den Nummern 5370 bis 5376 nicht berechnungsfähig." |
| 5440/5441/5442 (Nierenszintigraphie) | mutual exclusion, all 3 pairs | "Die Leistungen nach den Nummern 5440 bis 5442 sind je Sitzung nur einmal und nicht nebeneinander berechnungsfähig." (the "nur einmal" self-cap is Mengenbegrenzung — not encoded, see §4) |
| 5852/5853/5854 (Tiefen-Hyperthermie) | factor cap 1.0 | "Die Leistungen nach den Nummern 5852 bis 5854 sind … nur mit dem einfachen Gebührensatz berechnungsfähig." |

New rows: `data/rules/exclusions.manual.csv` (81 rows, `excl_man_*`), `data/rules/factor_caps.csv`
(5 rows, `cap_man_*`, appended rather than a new `factor_caps.manual.csv` — see the file-ordering
note in the commit).

**Golden test.** `apps/engine/tests/golden/case_j_coverage_sprint_batch1/` is a new, ninth
regression case (`tests/golden/oracle.py::REGRESSION_CASES`): GOÄ 1473 beside GOÄ 1485 on one
delivery, asserting `excl_man_1473_1485` fires and blocks 1485 —
`test_case_j_a_coverage_sprint_batch1_rule_actually_suppresses_its_ziffer` in
`apps/engine/tests/test_golden_cases.py`. Chosen because it is the simplest, single-edge new rule
in the batch (no mutual pair, no letter-Ziffer, no factor cap), so the test proves the mechanism
without also having to explain a cluster. Fixed a real gap while building it: `oracle.py`'s
`load_rules()` only read `exclusions.csv`, never `exclusions.manual.csv` — so no golden case in
this second corpus had ever exercised a hand-curated exclusion rule. Fixed alongside this batch
(see the commit) since without it the new case could not demonstrate anything.

The nine pre-existing frozen snapshots in `logic/tests/golden/` were re-verified with
`apps/engine/scripts/refreeze_rule_coverage.py --write` (metadata-only: rule counts and
`rules_hash` moved because 86 new rows were added; no Ziffer, factor, amount or proof moved on any
of the nine — `test_the_engine_still_reproduces_the_frozen_snapshot` passes on all nine). Two
fields the script's `ALLOWED` list does not cover — `total_constraint_rule_count` /
`total_constraint_rules`, on the six cases that carry that field — were investigated by hand
(the exact delta, 894 → 980, equals the 86 new rows) and patched directly rather than bypassing the
guard. `CASE_A_RECEIPT_PREFIX` in `apps/engine/tests/golden/oracle.py` moved for the same reason
(`rules_hash` is inside the hashed response) and was re-pinned after confirming it is stable across
two runs.

---

## 4. Held out this batch, and why (no guessing)

- **61** — "ist neben anderen Leistungen nicht berechnungsfähig": a blanket "only chargeable alone"
  rule, not a from/to pair. The exclusion schema has no way to say "excludes everything else."
- **96/95** — "nur neben den Leistungen nach den Nummern 80, 85 und 90 … berechnungsfähig": same
  blanket-allow-list shape as 61. Only the factor-cap half of the sentence was encoded.
- **D, H (first clauses)** — permissive sentences ("… ist … berechnungsfähig" / "darf … berechnet
  werden"), the opposite of an exclusion. Not encoded as exclusions under any reading.
- **D (Krankenhausärzte clause), E (Belegarzt exception)** — conditional on who performed the
  service ("es sei denn, die Visite wird durch einen Belegarzt durchgeführt";
  "für Krankenhausärzte … nicht berechnungsfähig"). The engine has no actor-type fact to decide
  this from a plain invoice; encoding it would be a guess about data the pipeline does not have.
- **2005 → 2033** — "… nicht berechnungsfähig, wenn die Extraktion des Nagels Bestandteil der
  Wundversorgung ist": already correctly triaged by the existing deterministic parser into
  `data/rules/exclusions.residue.csv` as `NEEDS_HUMAN_REVIEW` / `conditional:wenn`. Left alone,
  not re-litigated.
- **4851 → 4850** — "… nicht berechnungsfähig, bei Untersuchungen aus demselben Material": the same
  conditional shape as 2005/2033 above (a fact about how the specimen was handled, not visible on
  an invoice line). Held to the same bar the residue file already applies elsewhere in this table,
  rather than a one-off exception.
- **1056 → "Applikation von Prostaglandin-Gel"**, **1532 → "Intubationsnarkose"** — the excluded
  service is named descriptively, not by Ziffer. Mapping it to a specific number would be a guess.
- **435, 437** — each excludes hundreds of Ziffern across whole Abschnitte ("Abschnitt C III und
  M", "Abschnitt M mit Ausnahme von …") plus long numeric ranges with gaps (e.g. `286a`). Expanding
  this correctly needs subsection boundary data this sprint did not build, and getting a range
  wrong here risks a dangling or over-broad exclusion touching hundreds of positions. Flagged for
  a follow-up batch with dedicated tooling, not attempted by hand.
- **382, 387, 391, 4601, and the whole Mengenbegrenzung/Alter/Geschlecht/Zeitbeziehung class (100
  Ziffern remaining, §5)** — see §2: no rule table exists for a same-Ziffer frequency cap, an age
  gate, a sex gate, or a same-day/within-N-days relationship. This is the open architecture
  question in §6, not a per-Ziffer judgment call.

---

## 5. What's left, and why it's unverified

- **100 flagged Ziffern remain** after batch 1 (114 minus the 14 that batch 1 also happened to
  cover). Of these, **~88 carry only Mengenbegrenzung/Alter/Geschlecht** (no Ausschluss/
  Steigerungssatz hit at all) — blocked on the
  schema question in §6, not on citation quality; the sentences are just as unambiguous as batch
  1's, there is simply nowhere in the rule tables to put them yet.
- **435, 437** (§4) need range-expansion tooling that cross-references Abschnitt sub-boundaries
  (`C III`, `M` minus named exceptions) before they can be encoded without risking a wrong or
  dangling Ziffer reference.
- **~1,871 uncovered Ziffern carry no flagged text at all.** This is the honest bulk of the gap:
  most of the catalog simply has no annotation implying a mechanical rule in this snapshot. Closing
  it further is a research question (are there constraint patterns the six regexes miss?), not a
  batch-drafting one, and is out of scope for a citation-only sprint.
- **2005/2033, and by the same logic 4851/4850** (§4): correctly unencodable without clinical
  judgment the engine cannot derive from an invoice. Not a gap in this sprint's effort; a
  boundary the whole rule-verification pipeline already respects (`exclusions.residue.csv`,
  `UNVERIFIED_RULE_POLICY=warn`).

## 6. Open questions for a human (not guessed)

1. **Should the engine gain rule tables for Mengenbegrenzung (same-Ziffer frequency cap), Alter,
   Geschlecht and Zeitbeziehung?** This is the single biggest lever left (~85 of the 100 remaining
   flagged Ziffern, and likely a meaningful slice of the un-flagged 1,871 once a fifth regex pass
   is written). It needs a Datalog/ASP design decision — a new predicate per category, at minimum
   — and legal sign-off on what "engine cannot verify age/sex from a PADnext delivery today" means
   for the `warn`/`block`/`ignore` policy, before any data entry starts.
2. **435 and 437's whole-Abschnitt exclusions**: is there an authoritative subsection boundary list
   (which Ziffern are in "Abschnitt C III", "Abschnitt M" minus the two named M-subsections) this
   engine can read from `data/catalogs/`, or does that need a separate import?
3. **Actor-type conditions** (D's Krankenhausarzt clause, E's Belegarzt exception): does the intake
   pipeline capture who rendered a service in a way a future rule could read, or are these
   permanently out of scope for automatic enforcement?

---

## Appendix: regenerating these numbers

```
# coverage before/after, and the flagged-Ziffer inventory
python3 <<'PY'
import json, csv, re, collections
from pathlib import Path
cat = json.loads(Path("data/catalogs/goae_current/goae.official.json").read_text())
ziffern = {r["ziffer"]: r for r in cat["ziffern"]}
def load_csv(name):
    p = Path("data/rules")/name
    return list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []
def truthy(v): return str(v or "").strip().lower() in {"true","1","yes","y"}
excl = load_csv("exclusions.csv") + load_csv("exclusions.manual.csv")
ziel = load_csv("zielleistung.csv") + load_csv("zielleistung.manual.csv")
spec = load_csv("specificity.csv")
fcap = load_csv("factor_caps.csv")
under = set()
for r in excl:
    if truthy(r["verified"]): under.update([r["from_ziffer"], r["to_ziffer"]])
for r in ziel:
    if truthy(r["verified"]): under.update([r["parent_ziffer"], r["child_ziffer"]])
for r in spec:
    if truthy(r["verified"]): under.update([r["specific_ziffer"], r["general_ziffer"]])
for r in fcap:
    if truthy(r["verified"]): under.add(r["ziffer"])
under.discard("")
print(len(under), "/", len(ziffern))
PY

# engine's own view (enforced_rule_count, total_constraint_rule_count, dangling-reference check)
cd apps/engine && source .venv/bin/activate && python scripts/engine_cli.py check
```

Or authoritatively, from the engine itself: `Pipeline().rule_coverage()`
(`apps/engine/app/services/rule_coverage.py`) — the same call
`apps/engine/tests/test_published_numbers.py` and `apps/marketing/src/lib/engine-facts.ts` are
pinned against.
