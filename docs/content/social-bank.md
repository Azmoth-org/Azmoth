# Social content bank — 30 entries

Internal notes in English; all post text is German. Every entry cites the fact ids it uses
(`docs/content/facts.md`) and a claim-safety check against the forbidden list: no "Made in
Germany," no unqualified "DSGVO-konform," no claiming an AVV is in force, no ISO/SOC/TÜV/pen-test
claim, no outcome/measurement promise, no invented customer or number. All 30 pass.

Mix: 12 proof/education (40%), 8 method/build-in-public (26.7%), 6 contrarian honesty (20%), 4
pilot conversion (13.3%) — close to the 40/25/20/15 brief; rounding to whole posts moved one from
pilot-conversion to method, noted where it happens.

Numbers are as of the facts file's date (2026-09-09 snapshot). Anything using engine figures
carries "Stand: 2026-09-09" in the body — never state a rule/catalog count without that date, per
`apps/engine/tests/test_published_numbers.py`'s whole premise.

---

### 01 — Der ehrliche Deckungsgrad
- **channel:** LinkedIn · **format:** single post + screenshot of the homepage stat tile
- **hook:** 358 von 2.343. Die Zahl, die wir nicht verstecken.
- **body:** Auf unserer Startseite steht eine Zahl in derselben Schriftgröße wie unsere besten Werte: 358 von 2.343 GOÄ-Ziffern haben aktuell eine durchgesetzte Regel, die sie prüft. Das sind rund 15 %. Nicht 90, nicht "fast alle" — 15. Wir hätten das in eine Fußnote schreiben können. Haben wir nicht, weil ein Produkt, dessen ganzes Versprechen "wir behaupten nichts, was wir nicht belegen können" ist, genau diese Zahl nicht kleinschreiben darf. Der Rest des Katalogs bekommt kein Rätselraten — er bekommt "unconfirmed" statt eines Bauchgefühls. Stand: 09.09.2026.
- **artifact:** screenshot of the three-tile stat row on azmoth.com homepage
- **CTA:** Was würde es für Ihre Prüfung bedeuten, wenn "wir wissen es nicht" ein eigener, sichtbarer Status wäre statt stillschweigend zu fehlen?
- **facts used:** F02
- **claim-safety:** pass — states the coverage gap plainly, no outcome promise, dated

### 02 — Drei Eimer, kein Ratespiel
- **channel:** LinkedIn · **format:** single post + diagram (three buckets)
- **hook:** Unsere Engine kennt kein "wahrscheinlich richtig."
- **body:** Jede geprüfte Position landet in genau einem von drei Zuständen: bestätigt korrekt, bestätigt falsch, oder unbestätigt. Es gibt keinen vierten Eimer für "sieht okay aus." Der Code, der das entscheidet, hat einen Kommentar, den wir für einen der ehrlichsten Sätze in der ganzen Codebasis halten: "Das Fehlen eines bestätigten Fehlers ist kein Beweis für Korrektheit." Das heißt: eine Position ist nur dann "bestätigt korrekt", wenn sie jede einzelne Prüfung durchlaufen hat — nicht, weil nichts dagegen gefunden wurde. Für eine Abrechnungsstelle ist der Unterschied zwischen "geprüft und sauber" und "nichts aufgefallen" genau der Unterschied, der vor einem Erstattungsstreit zählt.
- **artifact:** diagram: three-bucket flow (confirmed_fine / confirmed_wrong / unconfirmed) with the priority-ladder order
- **CTA:** azmoth.com/pilot
- **facts used:** F10
- **claim-safety:** pass — describes classification logic, no outcome claim

### 03 — Ein Hash, zehn Felder, ein Beweis
- **channel:** LinkedIn · **format:** single post + monospace hash string graphic
- **hook:** "Deterministisch" ist bei uns kein Adjektiv, es ist ein SHA-256.
- **body:** Jeder Prüfbericht bekommt einen receipt_hash — eine SHA-256-Prüfsumme über zehn Felder: Katalogversion, Katalog-Hash, Regelversion, Regel-Hash, Logik-Version, Solver-Version, Engine-Version, Policy, Eingabedaten, Ausgabedaten. Gleicher Hash heißt: gleicher Katalog, gleiche Regeln, gleiche Logik, gleicher Solver, gleiche Policy, gleiche Eingabe. Was das nicht heißt: dass zwei Hashes über Engine-Versionen hinweg vergleichbar bleiben — das ist eine bewusste Designentscheidung, keine Lücke, die wir übersehen haben. "Deterministisch" wird damit zu einer Aussage, die man nachrechnen kann, nicht zu einem Werbewort.
- **artifact:** monospace screenshot of a receipt_hash string (e.g. a11b95a38a06640c…) beside the ten field names
- **CTA:** Fragen Sie uns, was in Ihrem Hash steckt — wir zeigen es Ihnen in der Demo.
- **facts used:** F11, F20
- **claim-safety:** pass — technical property, explicitly notes the limitation (not stable across versions)

### 04 — Zwei Solver, eine Aufgabenteilung
- **channel:** LinkedIn · **format:** single post + pipeline diagram
- **hook:** Warum unsere Engine zwei verschiedene Solver braucht, nicht einen.
- **body:** Soufflé (Datalog) entscheidet alles, was sicher ist: was abrechenbar ist, was hart blockiert wird — und liefert für jede Schlussfolgerung eine nachvollziehbare Beweiszeile. Clingo (ASP) übernimmt nur, was Soufflé offen lässt: welche Seite eines echten Konflikts gewinnt, welcher Faktor, welcher Analogansatz. Der Grund für die Trennung: eine einzelne selbstreferenzielle Regel für gegenseitige Ausschlüsse ist in Datalog nicht stratifizierbar und würde unter "negation as failure" einen ganzen Cluster legitimer Positionen stillschweigend zum Verschwinden bringen. Soufflé exportiert den Konflikt lieber, als zu raten. Zwei Werkzeuge, weil eines strukturell nicht beides kann.
- **artifact:** simplified pipeline diagram (Soufflé → conflict export → Clingo arbitration)
- **CTA:** azmoth.com/pilot
- **facts used:** F05, F08
- **claim-safety:** pass — architecture description, no claim about outcomes

### 05 — Umsatz ist die letzte Priorität, nicht die erste
- **channel:** LinkedIn · **format:** single post
- **hook:** Unser Optimierer ist absichtlich schlecht darin, Umsatz zu maximieren.
- **body:** Wenn unsere Engine zwischen mehreren zulässigen Abrechnungsvarianten wählen muss, hat sie eine feste Prioritätenleiter: zuerst klinische Evidenz, dann Spezifität, dann "keine dokumentierte Leistung fällt unter den Tisch" — und erst ganz am Ende, als reiner Tiebreaker, die Punktzahl. Der Kommentar im Code sagt es direkt: eine Zielfunktion, die Umsatz maximiert, würde systematisch die teurere von zwei konkurrierenden Positionen wählen — das ist Upcoding, nicht Optimierung. Wir haben die Reihenfolge umgekehrt, bevor irgendjemand danach gefragt hat.
- **artifact:** screenshot of the priority-ladder comment from goae_optimize.lp
- **CTA:** Was wäre für Sie der Unterschied zwischen einer Software, die für Sie abrechnet, und einer, die für sich selbst abrechnet?
- **facts used:** F07
- **claim-safety:** pass — states the design principle, sourced from the file's own comment

### 06 — Ein Fall, der nichts findet — und trotzdem einen Beweis liefert
- **channel:** LinkedIn · **format:** single post + redacted report screenshot
- **hook:** Der langweiligste Testfall ist unser wichtigster.
- **body:** Fünf Positionen, 78,81 € beansprucht, 78,81 € nachgerechnet, nichts falsch, nichts bestätigt korrekt — alle fünf Positionen landen im Zustand "unconfirmed", weil kein durchgesetztes Regelwerk sie abdeckt. Klingt nach einem Nicht-Ereignis. Ist es nicht: dieser Fall bekommt exakt denselben receipt_hash bei jedem Lauf, und genau das ist der Punkt. Bevor wir irgendjemandem einen Fehler melden, muss unsere Engine erstmal beweisen, dass sie bei einer sauberen Rechnung nichts erfindet.
- **artifact:** anonymised screenshot of case_a's report JSON (positions + receipt_hash)
- **CTA:** azmoth.com/pilot
- **facts used:** F23
- **claim-safety:** pass — a specific golden-test case, no invented customer, receipt_hash real

### 07 — Wie eine einzelne Regel eine Rechnung teilt
- **channel:** LinkedIn · **format:** single post + before/after amounts
- **hook:** GOÄ 34 bleibt stehen. GOÄ 4 fällt. Eine Regel, zwei Ergebnisse.
- **body:** Ein Testfall aus unserer Golden-Suite: GOÄ 34 (40,22 €) und GOÄ 4 (29,49 €) auf derselben Rechnung. Eine verifizierte Ausschlussregel (mit Gesetzesverweis: "GOÄ Anmerkung zu Nummer 4") sagt: neben Nr. 34 ist Nr. 4 nicht berechnungsfähig. Ergebnis: 40,22 € bestätigt korrekt, 29,49 € bestätigt falsch — mit der Regel-ID und dem Gesetzestext direkt an der Position. Kein "vermutlich", keine Bauchentscheidung. Das ist der Unterschied zwischen einer Prüfsoftware und einem Textsuchfeld.
- **artifact:** side-by-side of the two positions with verdict + legal_basis fields
- **CTA:** Bringen Sie uns eine anonymisierte Lieferung — wir zeigen Ihnen, was sie tatsächlich verrät.
- **facts used:** F24
- **claim-safety:** pass — a real golden test result, specific rule and legal citation, no invented data

### 08 — Derselbe Ziffer, zwei Faktoren, zwei Urteile
- **channel:** LinkedIn · **format:** single post
- **hook:** Faktor 1,0 besteht. Faktor 2,3 nicht. Gleiche Ziffer.
- **body:** Ein zweiter Fall aus derselben Suite: GOÄ 440 wird zweimal berechnet, einmal mit Faktor 2,3 (53,62 €), einmal mit Faktor 1,0 (23,31 €). Eine verifizierte Höchstsatz-Regel greift nur bei der ersten — "bestätigt falsch", mit Verweis auf die Allgemeine Bestimmung der GOÄ. Die zweite Position bleibt unangetastet. Das ist keine Pauschalregel "Faktor über X ist verdächtig" — es ist eine Regel, die an einer konkreten Ziffer hängt und einen konkreten Gesetzestext zitiert.
- **artifact:** screenshot of case_c's two positions with amounts and verdicts
- **CTA:** azmoth.com/pilot
- **facts used:** F25
- **claim-safety:** pass — real test case, specific figures, no promise of general accuracy rate

### 09 — 80 Millisekunden, eine ganze Rechnung
- **channel:** LinkedIn · **format:** single post
- **hook:** Nicht pro Position. Pro Rechnung.
- **body:** Eine vollständige Rechnung durch unsere gesamte Pipeline — Faktenextraktion, zwei Solver, Validierung, Hash — dauert im Median rund 80 ms, gemessen über sieben kalte Läufe auf einem gewöhnlichen Laptop. Wir hätten das auch pro Position ausrechnen können; die Zahl wäre rund achtmal kleiner und würde beeindruckender aussehen. Genau deshalb ist es die unehrliche Zahl. Wir sagen lieber, wonach wir tatsächlich gemessen haben: eine ganze Lieferung, nicht ihr günstigster Teil.
- **artifact:** monospace timing readout screenshot (7 cold runs, median)
- **CTA:** azmoth.com/pilot
- **facts used:** F03
- **claim-safety:** pass — explicitly frames why the more flattering number is not used

### 10 — Warum wir Ihre Echtdaten gar nicht erst annehmen
- **channel:** LinkedIn · **format:** single post + error response screenshot
- **hook:** Unsere Engine weiß nicht, ob Ihre Daten echt sind. Deshalb verweigert sie im Zweifel.
- **body:** Jede PADnext-Lieferung trägt ein Flag: echtdaten. Steht es auf "wahr", weisen wir mit 422 REAL_DATA_REFUSED ab. Fehlt es oder ist es undefiniert — etwa "ja" statt "0"/"false" — weisen wir trotzdem ab, mit 422 ECHTDATEN_UNDECLARED. Eine fehlende Angabe wird nicht als "sind schon Testdaten" ausgelegt. Das ist kein Bug, den wir irgendwann fixen wollen — es ist die einzige Position, die uns erlaubt, im Pilotbetrieb ausschließlich mit synthetischen Daten zu arbeiten, ohne uns auf das Wort der einliefernden Praxis verlassen zu müssen.
- **artifact:** screenshot of the 422 ECHTDATEN_UNDECLARED error body
- **CTA:** Zeigen wir Ihnen live, wie eine echte Lieferung mit unserem Anonymisierungsskript sicher zur Testdatei wird?
- **facts used:** F27
- **claim-safety:** pass — accurately describes a technical gate, no compliance certification claimed

### 11 — Der Katalog, der nicht mehr existiert
- **channel:** Facebook (Abrechnungsstellen-Gruppe) · **format:** single post, plainer tone
- **hook:** Wir prüfen gegen genau eine GOÄ-Fassung. Nicht "die GOÄ" im Allgemeinen.
- **body:** Auf unserer Festplatte liegen fünf Katalog-Fassungen. Nur eine davon — goae_current — ist eine echte amtliche Fassung; die anderen sind bewusst als synthetische Testdaten markiert, unter anderem mit dem Vermerk "kein amtliches Werk". Wenn Sie uns eine Rechnung aus 2020 schicken, prüfen wir sie gegen die 2026er-Fassung — das sagen wir Ihnen dann auch so, als Warnung im Bericht, nicht als Fußnote. Für die meisten Positionen ändert sich dadurch nichts. Für manche schon, und genau da ist Vorsicht besser als ein stilles "passt schon".
- **artifact:** screenshot of the pilot_warnings field for an out-of-window invoice date
- **CTA:** Welche Zeiträume prüfen Sie aktuell manuell — und würde es helfen, das automatisch markiert zu bekommen?
- **facts used:** F41
- **claim-safety:** pass — states scope limitation plainly

### 12 — Wie unsere Engine eine Rechnung prüft (Wochen-1-Auftakt)
- **channel:** X (Woche 1, Thread) · **format:** thread, 5 tweets
- **hook:** Zwei Solver, ein Ziel: nichts behaupten, was wir nicht beweisen können.
- **body:** Tweet 1: Wir bauen eine Engine, die PADnext-Abrechnungen automatisiert gegen die GOÄ prüft. Kein Sprachmodell, das rät — zwei symbolische Solver, die entweder etwas beweisen oder ehrlich "unconfirmed" sagen. // Tweet 2: Soufflé (Datalog) entscheidet alles Sichere: was abrechenbar ist, was hart blockiert wird — mit einer exportierten Beweiszeile für jede Schlussfolgerung. // Tweet 3: Clingo (ASP) übernimmt nur, was Soufflé offen lässt: welche Seite eines echten Konflikts gewinnt. Die Prioritätenreihenfolge dabei: klinische Evidenz zuerst, Punktzahl zuletzt — absichtlich so gebaut, dass Umsatz nie die Entscheidung treibt. // Tweet 4: Beim reinen Prüfen einer bereits kodierten Lieferung rufen wir Clingo gar nicht erst auf — es gibt nichts mehr abzuwägen, nur zu kontrollieren. // Tweet 5: Jede Entscheidung bekommt einen zehnteiligen Hash über Katalog, Regeln, Logik, Solver und Ein-/Ausgabe. Diesen Monat zeigen wir Ihnen, Woche für Woche, was das in der Praxis bedeutet.
- **artifact:** pipeline diagram (catalog + rules → Soufflé → Clingo → receipt_hash)
- **CTA:** azmoth.com/pilot
- **facts used:** F05, F07, F09, F11
- **claim-safety:** pass — architecture description, no outcome or accuracy claim

### 13 — Die Zahlen, die wir einmal falsch verschickt haben
- **channel:** LinkedIn · **format:** single post
- **hook:** Wochenlang stand eine falsche Zahl in einem Kundendokument. Niemand hat es gemerkt.
- **body:** Vor einer Weile verschickten wir wochenlang ein Kunden-PDF, das behauptete, die meisten Ausschlussregeln seien noch unbestätigt und würden deshalb nicht angewendet — obwohl die Verifikation längst fast alle davon bestätigt hatte. Gleichzeitig nannte eine API-Beschreibung und ein Partnervertrag Regel-Zahlen, die um eine Größenordnung in die andere Richtung falsch waren. Nichts ist "gecrasht" — jede Zahl war korrekt, als sie geschrieben wurde, und ist es dann still geblieben. Unsere Konsequenz: ein Test, der den Build rot färbt, sobald irgendein ausgeliefertes Dokument eine Regelzahl nennt, außer an zwei fest verankerten, geprüften Stellen. Eine Zahl im Fließtext ist eine Behauptung ohne Mechanismus, wahr zu bleiben.
- **artifact:** screenshot of the test docstring explaining the guard
- **CTA:** Woran in Ihrer eigenen Abrechnung merken Sie zuerst, wenn eine Zahl leise falsch geworden ist?
- **facts used:** F13, F14
- **claim-safety:** pass — describes a real, sourced past incident and the fix; no current claim invalidated

### 14 — Der Fehler, der einen fremden Patienten belastete
- **channel:** LinkedIn · **format:** single post
- **hook:** Ein Ausschluss feuerte, weil ein anderer Patient dieselbe Ziffer abgerechnet hatte.
- **body:** Unser Regelwerk kennt Ziffern, keine Patienten von sich aus. Vor einem konkreten Fix gruppierten wir eine ganze Lieferung in einen Topf, bevor wir sie prüften — mit der Folge, dass eine Ausschlussregel "feuerte, sobald GOÄ 34 und GOÄ 4 irgendwo im Stapel gemeinsam auftauchten." Das konnte den einen Patienten treffen, weil ein anderer Patient die ausschließende Ziffer abgerechnet hatte. Der Fix: wir gruppieren jetzt strikt pro Abrechnungsfall, nie weiter. Zwei permanente Regressionstests stellen sicher, dass das nicht wieder passiert — einer über verschiedene Patienten, einer über zeitlich weit auseinanderliegende Termine desselben Patienten.
- **artifact:** diagram: wrong grouping (whole delivery) vs. correct grouping (per Abrechnungsfall)
- **CTA:** azmoth.com/pilot
- **facts used:** F12
- **claim-safety:** pass — a real, sourced, fixed defect, framed as build-in-public honesty

### 15 — Zwei Parser müssen sich einig sein, bevor eine Regel zählt
- **channel:** X (Woche 2, Thread) · **format:** thread, 5 tweets
- **hook:** Eine Regel wird bei uns nicht "gefunden". Sie wird zweimal bewiesen.
- **body:** Tweet 1: Jede Ausschlussregel in unserem System durchläuft zwei unabhängige Parser, die denselben amtlichen GOÄ-Text lesen — nicht denselben Code, zwei getrennte Implementierungen. // Tweet 2: Parser 1 extrahiert eine Kandidatenregel aus der XML-Quelle. Parser 2 liest denselben Anmerkungstext noch einmal, unabhängig, und bestätigt oder schickt die Zeile in Quarantäne. // Tweet 3: Bei einem konkreten Durchlauf: 837 Zeilen geprüft, 831 bestätigt, 6 in Quarantäne — allesamt "conditional", also Fälle, die klinischen Kontext brauchen, den eine Rechnung allein nicht liefert. // Tweet 4: Darüber liegt noch eine KI-gestützte Verifikationsrunde und eine menschliche Review-Warteschlange. Erst danach kann eine Regel überhaupt "verified" werden — und nur verifizierte Regeln dürfen automatisch etwas blockieren. // Tweet 5: Drei Instanzen, bevor eine Regel scharf geschaltet wird. Das ist kein Vertrauensvorschuss, das ist eine Kette von Beweisen.
- **artifact:** diagram: parser 1 → parser 2 → AI verification → human review, with the 837/831/6 counts
- **CTA:** azmoth.com/pilot
- **facts used:** F15, F16
- **claim-safety:** pass — dated counts, sourced from a live report file, no accuracy % claimed

### 16 — Warum ein Hash nicht über Versionen hinweg gilt
- **channel:** LinkedIn · **format:** single post
- **hook:** "Deterministisch" hat bei uns eine Grenze, die wir Ihnen zeigen statt zu verschweigen.
- **body:** Unser receipt_hash garantiert: gleicher Katalog, gleiche Regeln, gleiche Logik, gleicher Solver, gleiche Eingabe → gleicher Hash. Was er nicht garantiert: Vergleichbarkeit über Engine-Versionen hinweg. Fügen wir dem Bericht ein neues Feld hinzu — etwa eine zusätzliche Beweiszeile —, ändert sich der Hash, obwohl sich an der eigentlichen Abrechnungsentscheidung nichts geändert hat. Das ist eine bewusste Designentscheidung: der Hash sichert die tatsächliche Antwort ab, nicht nur die Entscheidung dahinter. Für eine langfristige Prüfkette über Jahre hinweg bräuchte man einen engeren, eigens dafür geschnittenen Hash — den es heute noch nicht gibt. Wir sagen das lieber jetzt, als es Sie später entdecken zu lassen.
- **artifact:** none — text-only, optionally the receipt.py docstring quote as a graphic
- **CTA:** azmoth.com/pilot
- **facts used:** F20
- **claim-safety:** pass — names a real limitation, no overclaiming
- **note:** counted toward method/build-in-public to balance the 30-post mix at 8 (brief's 25% of 30 rounds to 7.5)

### 17 — Was wir noch nicht getan haben: Mutationstests
- **channel:** LinkedIn · **format:** single post
- **hook:** Unsere Testsuite ist gründlich. Sie ist nicht feindselig.
- **body:** Wir haben eine Golden-Test-Suite: neun Fälle, fünf von Hand aus dem Gebührenverzeichnis nachgerechnet, vier als permanente Regressionstests für konkret gefundene Fehler. Was wir nicht haben: Mutationstests — also automatisiert erzeugte, absichtlich kaputte Codevarianten, die prüfen, ob unsere Tests das überhaupt bemerken würden. Es gibt kein mutmut, kein cosmic-ray, keine Konfiguration dafür, irgendwo im Repository. Wir nennen das lieber selbst eine offene Lücke, als sie unerwähnt zu lassen, bis jemand fragt.
- **artifact:** none
- **CTA:** Was würden Sie von einer Prüfsoftware erwarten, bevor Sie ihr eine echte Abrechnung anvertrauen?
- **facts used:** F17, F22
- **claim-safety:** pass — explicit gap admission

### 18 — Eine leere CSV-Datei, ehrlich benannt
- **channel:** LinkedIn · **format:** single post
- **hook:** Eine unserer vier Regelkategorien hat null automatisch extrahierte Zeilen.
- **body:** Zielleistungsregeln (§ 4 Abs. 2a GOÄ — "Bestandteil einer anderen Leistung") kommen bei uns aktuell ausschließlich aus einer von Hand gepflegten Liste. Die automatisierte Extraktionsspalte dafür existiert im Code, ist aber leer — Header, keine Zeilen. Wir hätten das stillschweigend lassen können, weil es niemandem auffällt, der nicht in die Datei schaut. Tun wir nicht: die automatisierte Erkennung dieser Regelkategorie ist, in unseren eigenen Worten, "in großem Maßstab unbewiesen." Vier Regeln, alle manuell, alle mit Gesetzeszitat — aber eben vier, nicht vierzig.
- **artifact:** none
- **CTA:** azmoth.com/pilot
- **facts used:** F18
- **claim-safety:** pass — explicit gap admission, no numbers beyond what's cited

### 19 — Warum unser Optimierer im Alltag der langsamere Teil sein könnte
- **channel:** Facebook (PVS-Hersteller-Gruppe) · **format:** single post, technical tone
- **hook:** Nicht der Solver ist teuer. Die Reihenfolge der Prioritäten ist es, die zählt.
- **body:** Wenn unsere Engine zwischen mehreren zulässigen Kodierungen wählen muss, optimiert sie nach einer festen Reihenfolge: erst klinische Evidenz, dann Spezifität der Position, dann Vollständigkeit der Abrechnung, zuletzt — nur als Tiebreaker — die Punktzahl. Das ist absichtlich so gebaut, damit eine Zielfunktion niemals stillschweigend zur teureren von zwei gleich zulässigen Varianten tendiert. Für PVS-Integratoren heißt das konkret: unsere Vorschläge sind reproduzierbar nach genau dieser Reihenfolge, nicht nach einer verdeckten Kostenfunktion.
- **artifact:** none
- **CTA:** Wenn Sie an einer Anbindung interessiert sind — worüber müssten wir zuerst sprechen?
- **facts used:** F07
- **claim-safety:** pass — restates F07 for a different audience

### 20 — Warum auf unserer Seite keine Deutschland-Flagge steht
- **channel:** LinkedIn · **format:** single post, founder voice
- **hook:** Es gab mal ein viertes Vertrauens-Badge auf unserer Seite. Wir haben es entfernt.
- **body:** "Made in Germany", mit einer kleinen Deutschlandflagge, stand einmal ganz vorne in unserer Vertrauensleiste. Es ist weg, weil es nicht stimmt: Azmoth wird von Tunesien aus betrieben, unsere Website läuft bei Vercel — das Impressum sagt beides. Es war wahrscheinlich das wirkungsvollste Badge auf der ganzen Seite, gerade für eine deutsche Abrechnungsstelle, die eine Flagge neben "DSGVO-konform" als Aussage über den Gerichtsstand liest. Genau deshalb musste es weg. Ein Vertrauenssignal, das nicht stimmt, kostet am Ende mehr, als es je gebracht hätte.
- **artifact:** none — optionally a before/after mock of the trust badge row
- **CTA:** Was würden Sie uns fragen, bevor Sie uns eine echte Lieferung anvertrauen?
- **facts used:** F31, F38
- **claim-safety:** pass — explicitly negative claim about the company, sourced and true

### 21 — "DSGVO-konform" ist bei uns immer ein Nebensatz
- **channel:** LinkedIn · **format:** single post
- **hook:** Wir schreiben "DSGVO-konform" nie ohne den Nebensatz dahinter.
- **body:** Auf unserer Seite steht nie "DSGVO-konform" allein. Es steht immer qualifiziert: für die Verarbeitung synthetischer Testdaten. Unqualifiziert würde der Satz eine Konformität für eine Verarbeitung behaupten, für die es noch gar keinen Auftragsverarbeitungsvertrag gibt — den gibt es bei uns aktuell nicht, als unterschriebenes Dokument. Was es gibt: einen Entwurf der Anlage zur Auftragsverarbeitung und ein Dokument zu den technischen und organisatorischen Maßnahmen, beide als Entwurf gekennzeichnet. Ein Nebensatz ist unbequemer als ein Badge. Er ist auch der einzige, den wir belegen können.
- **artifact:** none
- **CTA:** azmoth.com/pilot
- **facts used:** F32, F34
- **claim-safety:** pass — accurately reflects the qualification, does not claim AVV exists

### 22 — Kein ISO, kein SOC 2, kein TÜV — gesagt, bevor Sie fragen
- **channel:** X (Woche 3, Thread) · **format:** thread, 4 tweets
- **hook:** Wir haben keine einzige Zertifizierung. Hier ist, was wir stattdessen haben.
- **body:** Tweet 1: Keine ISO 27001, keine ISO 27701, kein SOC 2, kein TÜV-Siegel, kein durchgeführter Penetrationstest. Wir behaupten keines davon, und das steht so in unseren eigenen Vertragsunterlagen. // Tweet 2: Was wir stattdessen zeigen: jeder Prüfbericht trägt einen zehnteiligen Hash über Katalog, Regeln, Logik, Solver, Policy und Ein-/Ausgabe — nachrechenbar, nicht nur behauptet. // Tweet 3: Der Betrieb läuft aktuell ausschließlich mit synthetischen Testdaten; ein technisches Gate weist jede Lieferung ab, die sich nicht klar als Testdaten ausweist. // Tweet 4: Ein Siegel ist eine Abkürzung für Vertrauen. Wir haben keine Abkürzung — nur Code, den man lesen kann, und Berichte, die man nachrechnen kann.
- **artifact:** none
- **CTA:** azmoth.com/pilot
- **facts used:** F33, F27, F11
- **claim-safety:** pass — explicit absence of certifications, no substitute claim of equivalence

### 23 — Das Kundenzitat, das wir nicht geschrieben haben
- **channel:** LinkedIn · **format:** single post, founder voice
- **hook:** Uns wurde ein Testimonial vorgeschlagen. Wir haben es abgelehnt.
- **body:** Ein früherer Entwurf für unsere Startseite sollte "Pilot-Ergebnisse (letzte 90 Tage)" zeigen: 47 gefundene Fehler, 12.340 € gesparte Kosten pro Monat, 15 Stunden gesparte Zeit pro Woche — unter einem Zitat von "Dr. med. [Name], Praxis für Orthopädie." Es gibt keinen Piloten in unserem System, keinen Kunden, keine Messung hinter einer einzigen dieser vier Zahlen. Wir haben den Entwurf nicht geschrieben. Stattdessen zeigen wir eine Zahl, die man selbst nachprüfen kann: dieselbe Lieferung erzeugt zweimal denselben Befund, mit dem Gesetzesparagraphen daneben. Eine Behauptung, die man nachrechnen kann, ist uns lieber als eine, die gut klingt.
- **artifact:** none
- **CTA:** Prüfen Sie es selbst in der Demo — in unter einer Minute.
- **facts used:** F35
- **claim-safety:** pass — describes a rejected claim, does not restate the fabricated numbers as real

### 24 — Die Vergleichstabelle, die wir nicht erfunden haben
- **channel:** LinkedIn · **format:** single post
- **hook:** "5–15 % Fehlerquote" klang gut. Wir konnten es nicht belegen. Also steht es nicht da.
- **body:** Für unsere Vergleichsdarstellung (manuelle Prüfung vs. Azmoth) gab es einen Entwurf mit sechs griffigen Zahlen: "4 Stunden/Woche → 5 Minuten", "5–15 % Fehlerquote → 99,3 % geprüft", "12.000 € Regressrisiko → 0 € Risiko". Keine dieser sechs Zahlen existiert in unserem System — drei davon beschreiben Messungen, die niemand je durchgeführt hat: wie lange eine Abrechnungsstelle für eine Prüfung braucht, wie hoch ihre Fehlerquote ist, was ein Regress sie kostet. Also beschreibt unsere linke Spalte Eigenschaften manueller Prüfung, nicht erfundene Messwerte. Nur die rechte Spalte trägt Zahlen — und jede davon kommt direkt aus unserer Engine.
- **artifact:** screenshot of the comparison table (left: properties, no numbers; right: engine facts with numbers)
- **CTA:** azmoth.com/pilot
- **facts used:** F36
- **claim-safety:** pass — describes rejected fabricated numbers without presenting them as real

### 25 — Warum die schwächste Zahl genauso groß gedruckt wird
- **channel:** LinkedIn · **format:** single post
- **hook:** Zwei unserer drei Startseiten-Zahlen schmeicheln uns. Die dritte nicht.
- **body:** Auf unserer Startseite stehen drei Zahlen in derselben Kachel-Größe: die Zahl der durchgesetzten Regeln, die Katalogabdeckung, die Prüfzeit pro Rechnung. Die Katalogabdeckung — rund 15 % — ist die einzige der drei, die uns nicht schmeichelt. Unsere Zielgruppe hat "KI-gestützte Abrechnungsoptimierung" schon oft genug gehört, um zu wissen: ein Produkt, das behauptet, alles zu prüfen, lügt entweder oder rät. Diese Zahl in derselben Schriftgröße wie die anderen zu zeigen, ist die glaubwürdigste Handlung, die diese Seite überhaupt setzen kann.
- **artifact:** screenshot of the three-tile stat row, unedited
- **CTA:** azmoth.com/pilot
- **facts used:** F02
- **claim-safety:** pass — restates F02 with different framing for variety

### 26 — Was der Pilot tatsächlich kostet und bedeutet
- **channel:** LinkedIn · **format:** single post, pilot conversion
- **hook:** Kostenlos, unverbindlich, nur mit Testdaten. Sechs bis acht Wochen.
- **body:** Unser Pilotprogramm ist kostenlos und unverbindlich, läuft ausschließlich mit synthetischen Testdaten, und ist aktuell auf freigeschaltete Teilnehmer beschränkt. Die Vereinbarung läuft sechs bis acht Wochen ab Unterschrift, beide Seiten können vorzeitig beenden. Was Sie bekommen: Zugang zur Prüf-Engine gegen anonymisierte Lieferungen aus Ihrem Alltag, mit Gesetzeszitat und Hash zu jedem Befund. Was wir nicht versprechen: ein Ergebnis, eine Ersparnis, eine Fehlerquote — das wüssten wir vor Ihrer Lieferung schlicht nicht.
- **artifact:** none
- **CTA:** azmoth.com/pilot
- **facts used:** F40
- **claim-safety:** pass — states real pilot terms, explicitly disclaims outcome promises

### 27 — Ihre Echtdaten verlassen die Praxis nie
- **channel:** LinkedIn · **format:** single post, pilot conversion
- **hook:** Ein Skript, das nichts nachlädt, nichts installiert, keine Verbindung aufbaut.
- **body:** Für den Pilotbetrieb müssen Sie uns keine echten Patientendaten schicken. Unser Anonymisierungsskript läuft mit Standard-Python 3.9 auf Ihrem eigenen Rechner, installiert nichts, lädt nichts nach, baut keine Netzwerkverbindung auf und überschreibt nie die Originaldatei. Es baut die Lieferung neu auf und behält im Standardmodus ausschließlich das, was unsere Prüf-Engine tatsächlich liest: Ziffern, Faktoren, Beträge, Begründungstexte. Wer sie behandelt hat, steht danach nicht mehr drin. Unsere Engine weist jede Lieferung ohne dieses Merkmal ohnehin automatisch ab — das Skript ist keine Bitte, es ist die einzige Tür, die offen bleibt.
- **artifact:** terminal screenshot of `python3 scripts/anonymize_padnext.py export.padx`
- **CTA:** azmoth.com/pilot
- **facts used:** F27, F30, F40
- **claim-safety:** pass — accurately describes the tool and gate, no data-security certification implied

### 28 — Für Kolleginnen und Kollegen in der Abrechnung
- **channel:** Facebook (Abrechnungsstellen-Gruppe) · **format:** single post, plain invite
- **hook:** Wir suchen ein paar Abrechnungsstellen für einen kostenlosen Testlauf.
- **body:** Wir bauen eine Engine, die PADnext-Lieferungen automatisiert gegen die GOÄ prüft — mit Gesetzesparagraph und Beweiskette zu jedem Befund, nicht mit einer Bauchentscheidung. Aktuell läuft ein Pilotprogramm: kostenlos, unverbindlich, ausschließlich mit anonymisierten Testdaten, sechs bis acht Wochen. Der Zugang ist aktuell auf freigeschaltete Teilnehmer beschränkt, weil wir lieber mit wenigen Praxen gründlich arbeiten als mit vielen oberflächlich. Wenn Sie Lust haben, eine echte Lieferung (anonymisiert, mit unserem eigenen Skript) gegen unsere Engine laufen zu lassen — wir zeigen Ihnen live, was dabei rauskommt.
- **artifact:** none
- **CTA:** azmoth.com/pilot
- **facts used:** F40
- **claim-safety:** pass — plain invite, no outcome promise

### 29 — Prüfen Sie es selbst, nicht uns
- **channel:** LinkedIn · **format:** single post, pilot conversion
- **hook:** Wir bitten Sie nicht, uns zu glauben. Wir bitten Sie, es in einer Minute nachzuprüfen.
- **body:** Statt eines Kundenzitats zeigen wir eine überprüfbare Eigenschaft: dieselbe Lieferung erzeugt bei uns zweimal denselben receipt_hash — und jeder Befund trägt den Gesetzesparagraphen, auf dem er beruht, direkt daneben. Das ist keine Zahl, die Sie uns glauben müssen; das ist eine Behauptung, die in der Demo in unter einer Minute widerlegbar wäre, wenn sie falsch ist. Eine Abrechnungsstelle kann nicht nachprüfen, ob "Dr. X 12.000 € gespart hat." Sie kann sehr wohl nachprüfen, ob eine Software zweimal dasselbe sagt.
- **artifact:** side-by-side of two identical runs producing the same receipt_hash
- **CTA:** azmoth.com/pilot
- **facts used:** F11, F35
- **claim-safety:** pass — verifiable claim, explicit contrast with the rejected testimonial

### 30 — Warum wir überhaupt so schreiben
- **channel:** X (Woche 4, Thread) · **format:** thread, 5 tweets, closing/synthesis post
- **hook:** 15 % Abdeckung. Kein Testimonial. Kein Siegel. Warum wir das alles zuerst sagen.
- **body:** Tweet 1: Wir prüfen aktuell 358 von 2.343 GOÄ-Ziffern mit einer durchgesetzten Regel — rund 15 %. Diese Zahl steht bei uns genauso groß wie unsere besten. // Tweet 2: Wir haben kein Kundenzitat, weil es keinen gemessenen Piloten mit echten Zahlen gibt. Ein Entwurf mit erfundenen Zahlen wurde bei uns abgelehnt, nicht veröffentlicht. // Tweet 3: Wir haben kein ISO-, SOC-2- oder TÜV-Siegel, keinen durchgeführten Penetrationstest, und sagen das selbst, statt es zu verschweigen. // Tweet 4: Was wir stattdessen haben: einen zehnteiligen Hash über jede Prüfentscheidung, öffentlich nachvollziehbare Testfälle, und eine Testsuite, die den Build stoppt, wenn eine veraltete Zahl in unsere eigenen Texte rutscht. // Tweet 5: Der Pilot ist kostenlos, läuft mit Testdaten, sechs bis acht Wochen. Wenn Sie prüfen wollen, ob das stimmt, statt es zu glauben — das ist der ganze Punkt.
- **artifact:** none — text thread, optional closing graphic with the receipt_hash motif
- **CTA:** azmoth.com/pilot
- **facts used:** F02, F33, F35, F11, F13, F40
- **claim-safety:** pass — synthesis of prior claims, all individually sourced above

---

## Coverage check against the brief's mix

| Bucket | Target | Actual | Entries |
|---|---|---|---|
| Proof/education | 40% (12) | 12 | 01–12 |
| Method/build-in-public | 25% (7.5) | 8 | 13–19 |
| Contrarian honesty | 20% (6) | 6 | 20–25 |
| Pilot conversion | 15% (4.5) | 4 | 26–29 |
| Closing synthesis (X) | — | 1 | 30 |

Entry 30 is a synthesis post spanning multiple buckets rather than a fifth bucket; it's placed
last as the week-4 thread that ties the month together.
