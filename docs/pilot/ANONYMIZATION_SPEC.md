# Anonymisierung von PADnext-Lieferungen

**Spezifikation zu `scripts/anonymize_padnext.py`**
Stand: 30. August 2026 · Gilt für den Pilotbetrieb

---

## 1. Wozu dieses Dokument

Azmoth prüft PADnext-Lieferungen gegen die GOÄ. Für diese Prüfung werden ausschließlich die
abgerechneten Ziffern, Faktoren, Beträge und Begründungen benötigt — **nicht**, wer behandelt
wurde.

Damit das nicht nur eine Absichtserklärung bleibt, gibt es zwei technische Maßnahmen, die
zusammengehören:

1. **Das Anonymisierungsskript** entfernt die Identität aus der Exportdatei, bevor sie die Praxis
   verlässt, und kennzeichnet das Ergebnis mit `echtdaten="false"`.
2. **Die Engine weist jede Lieferung ab**, die diese Kennzeichnung nicht trägt — mit
   `422 ECHTDATEN_UNDECLARED`. Eine fehlende Angabe wird *nicht* als „Testdaten" ausgelegt.

Die zweite Maßnahme ist der Grund, warum die erste keine Bitte ist: Eine nicht anonymisierte Datei
wird nicht geprüft, sondern zurückgewiesen. Es gibt keinen Weg an ihr vorbei, der nicht das
bewusste Setzen von `PADNEXT_ALLOW_REAL_DATA=1` auf dem Server durch den Betreiber wäre — und der
setzt eine eigene Rechtsgrundlage voraus.

Dieses Dokument beschreibt, **was das Skript genau tut**, **was es ausdrücklich nicht tut** und
**welche datenschutzrechtliche Bewertung sich daraus ergibt**. Es ist so geschrieben, dass es einer
Datenschutzbeauftragten vorgelegt werden kann.

---

## 2. Kurzanleitung

Das Skript benötigt nur Python 3.9 oder neuer aus der Standardinstallation. Es installiert nichts,
lädt nichts nach und stellt keine Netzwerkverbindung her.

```bash
# Funktionsprüfung — braucht keine Datei, prüft nur, ob das Skript intakt ist
python3 scripts/anonymize_padnext.py --selftest

# Anonymisieren
python3 scripts/anonymize_padnext.py export.padx
# → schreibt export.anonymized.padx

# Eigener Ausgabename
python3 scripts/anonymize_padnext.py export.padx -o pilot-01.padx
```

Verarbeitet werden `.padx`-Container, einzelne `*_padx.xml`-Nutzdatendateien und `.auf`-Auftrags-
dateien. **Die Eingabedatei wird nie verändert und nie überschrieben.** Das Skript verweigert die
Ausgabe, wenn sie auf die Eingabe zeigen würde.

Hochgeladen wird ausschließlich die **Ausgabedatei**.

### Rückgabewerte

| Wert | Bedeutung |
|------|-----------|
| `0` | Datei geschrieben |
| `1` | Eingabe nicht lesbar oder Ausgabe nicht schreibbar |
| `2` | Aufruffehler (z. B. Ausgabedatei existiert bereits — mit `--force` überschreiben) |
| `3` | Datei geschrieben, aber die Freitextprüfung hat etwas gefunden **und** `--fail-on-residual` war gesetzt |

---

## 3. Was das Skript entfernt

### 3.1 Zwei Betriebsarten

Der Unterschied liegt darin, was mit einem Feld geschieht, **das das Skript nicht kennt**.

#### `--mode strict` (Voreinstellung) — Positivliste

Die Nutzdaten werden neu aufgebaut und enthalten danach **ausschließlich** die Elemente und
Attribute, die die Prüf-Engine tatsächlich liest:

| Element | Attribute |
|---------|-----------|
| `rechnungen` | `anzahl`, `echtdaten`, `schemaLocation` |
| `nachrichtentyp` | `version` |
| `rechnung` | `id` |
| `abrechnungsfall` | — |
| `behandlungsart`, `vertragsart`, `minderungssatz` | — |
| `positionen` | `posanzahl` |
| `goziffer` | `positionsnr`, `go`, `ziffer`, `analog` |
| `datum`, `anzahl`, `text`, `faktor`, `einzelbetrag`, `begruendung`, `minderungssatz`, `punktzahl`, `punktwert`, `gesamtbetrag` | — |

**Alles andere wird entfernt** — unabhängig davon, ob es auf irgendeiner Liste steht. Ein Element
`<patientenchip>`, das ein Praxisverwaltungssystem im letzten Frühjahr eingeführt hat, verschwindet
nicht, weil es erkannt wurde, sondern weil es nicht behalten wurde.

Ausdrücklich mit entfernt werden dabei auch:

- `rechnungsersteller` und `leistungserbringer` — die Praxis bzw. die behandelnde Person. Das sind
  ebenfalls personenbezogene Daten (Art. 4 Nr. 1 DSGVO), auch wenn sie keine Patientendaten sind.
- `rechnung/@aisrechnungsnr` — die praxisinterne Rechnungsnummer. Sie ist ein direkter
  Zuordnungsschlüssel für jeden, der zugleich das Praxisjournal hat.

#### `--mode mask` — Negativliste

Das Dokument behält seine Struktur; bekannte Identitätsfelder werden entfernt. Diese Betriebsart
existiert für den Fall, dass ein nachgelagertes System die Originalstruktur benötigt. **Sie ist
prinzipiell weniger sicher**, weil ein unbekanntes Feld erhalten bleibt. Das Skript weist bei jedem
Lauf in dieser Betriebsart darauf hin.

Für den Upload nach Azmoth wird `strict` empfohlen.

#### Warum `strict` die Voreinstellung ist

Die beiden Fehlerarten wiegen nicht gleich schwer. Eine zu enge Positivliste erzeugt einen Bericht
mit einer Lücke — das fällt auf. Eine zu enge Negativliste erzeugt eine Datei, die anonymisiert
*aussieht*, es nicht ist, und hochgeladen wird.

### 3.2 Die Identitätsliste

In beiden Betriebsarten werden Elemente und Attribute mit diesen Namen entfernt (Vergleich ohne
Berücksichtigung von Groß-/Kleinschreibung und XML-Namensraum):

| Kategorie | Namen |
|-----------|-------|
| **Name** | `patient`, `patient_name`, `patientname`, `patientenname`, `patientendaten`, `behandelter`, `person`, `name`, `nachname`, `vorname`, `geburtsname`, `titel`, `namenszusatz`, `vorsatzwort`, `anrede` |
| **Rechnungsempfänger** | `rechnungsempfaenger`, `zahlungspflichtiger`, `kostentraeger`, `empfaengeradresse` |
| **Geburtsdatum, Geschlecht** | `geburtsdatum`, `gebdatum`, `geburtstag`, `geschlecht` |
| **Anschrift** | `patient_address`, `patientenadresse`, `anschrift`, `adresse`, `wohnort`, `strasse`, `strassehausnummer`, `hausnummer`, `plz`, `postleitzahl`, `ort`, `ortsteil`, `land`, `staat`, `postfach` |
| **Kontakt** | `telefon`, `telefonnummer`, `telefonprivat`, `telefondienst`, `telefax`, `fax`, `email`, `emailadresse`, `mobil`, `mobilnummer` |
| **Versicherung, Fallkennungen** | `versichertennummer`, `versichertennr`, `versicherungsnummer`, `versichertenid`, `versichertenstatus`, `kvnr`, `krankenversicherung`, `versicherung`, `versicherungsnehmer`, `versicherungsart`, `tarif`, `policennummer`, `patientennummer`, `patientenid`, `patid`, `fallnummer`, `aktenzeichen`, `chipkartennummer`, `egknummer` |
| **Zahlungsdaten** | `iban`, `bic`, `kontonummer`, `kontoinhaber`, `blz`, `bankverbindung`, `bankname`, `mandatsreferenz`, `glaeubigerid`, `sepa`, `lastschrift` |
| **Sonstiges** | `unterschrift`, `ausweisnummer`, `steuernummer` |

Ein entferntes Element nimmt seinen **gesamten Unterbaum** mit: `<patient>` steht auf der Liste,
also verschwinden `<patient><name>…</name><geburtsdatum>…</geburtsdatum></patient>` als Einheit.

**Eine dokumentierte Ausnahme:** `auftrag > datei > name` bleibt erhalten. Das ist der *Dateiname*
der Nutzdaten, kein Personenname; ohne ihn kann ein empfangendes System die Container-Mitglieder
nicht mehr zuordnen.

### 3.3 Die Kennzeichnung `echtdaten="false"`

Das Skript setzt `echtdaten="false"`

- am Wurzelelement `<auftrag>` der Auftragsdatei — dort sieht die PADnext-Spezifikation das
  Attribut vor;
- **zusätzlich** am Wurzelelement `<rechnungen>` der Nutzdaten.

Der zweite Ort ist eine Erweiterung. Sie ist nötig, weil eine Nutzdatendatei auch **ohne**
Container hochgeladen werden kann — dann gibt es kein `<auftrag>`, über das sie sich erklären
könnte. Das Teilschema in `data/schemas/padnext/padx_adl_v2.12.subset.xsd` lässt sie zu
(`xs:anyAttribute` auf `<rechnungen>`).

Der vorherige Wert wird nicht verworfen, sondern im Protokoll ausgegeben. Die Zeile
„`<auftrag> echtdaten="false" gesetzt (war echtdaten="ja")`" ist die wichtigste Zeile der Ausgabe.

### 3.4 Prüfsummen

Nach der Bearbeitung stimmen `datei/dateilaenge/@laenge` und `@pruefsumme` in der Auftragsdatei
nicht mehr. Das Skript berechnet beide über die **anonymisierten** Nutzdaten neu (Länge in Bytes,
SHA-1 als 40 Hexzeichen). Der Container bleibt damit für ein empfangendes System
integritätsgeprüft. Die Prüfsumme ist eine Transportsicherung gegen Übertragungsfehler und wird an
keiner Stelle als Sicherheitsmerkmal behandelt.

### 3.5 Kommentare

XML-Kommentare gehen bei der Verarbeitung verloren. Das ist beabsichtigt: Ein Kommentar kann einen
Patientennamen genauso gut enthalten wie ein Element, und die Prüfung liest keine Kommentare.

---

## 4. Was das Skript ausdrücklich **nicht** tut

Dieser Abschnitt ist der wichtigste des Dokuments.

### 4.1 Freitext wird nicht gelesen

`<text>` und `<begruendung>` bleiben **erhalten**. Sie müssen erhalten bleiben: Die Begründung nach
**§ 12 Abs. 3 GOÄ** ist genau das, was die Prüfung bewertet. Eine Steigerung über den
Schwellenwert ohne Begründung ist einer der häufigsten Befunde überhaupt — ohne den Text kann die
Engine dazu nichts sagen.

Freitext wird jedoch von Menschen geschrieben. Ein Satz wie

> „Bericht an Dr. Weber zum Befund von Frau Schmidt, geb. 14.03.1961"

ist ein personenbezogenes Datum, das kein Elementname als solches kennzeichnet. **Kein
Automatismus kann das zuverlässig erkennen**, und ein Skript, das es versuchte, würde entweder
Begründungen zerstören oder Namen übersehen — meistens beides.

Deshalb tut das Skript etwas anderes: Es durchsucht den verbliebenen Freitext nach den
offensichtlichen Mustern

- Datum im Format TT.MM.JJJJ (mögliches Geburtsdatum),
- Versichertennummer-Muster (Buchstabe gefolgt von neun Ziffern),
- IBAN-Muster,
- Ziffernfolgen ab acht Stellen,
- E-Mail-Adressen,
- Anreden mit nachfolgendem Namen („Herr/Frau/Dr./Prof. + Name"),

und **gibt aus, was es gefunden hat**. Es entfernt nichts davon.

> **Diese Ausgabe ist eine Aufforderung an einen Menschen, keine Filterung.**
> Wer die Datei hochlädt, muss die gemeldeten Stellen ansehen.

Mit `--redact-freetext` werden diese Felder durch `ANONYMISIERT` ersetzt. Das entfernt zugleich die
Begründungen, die die Prüfung bewertet — der Bericht verliert dadurch Aussagekraft. Die Option
existiert, ist aber nicht die Voreinstellung, weil sie die Prüfung teilweise entwertet.

### 4.2 Behandlungsdaten bleiben erhalten

Das Ergebnis enthält weiterhin:

- **Behandlungsdaten** (`<datum>`) — taggenau,
- **GOÄ-Ziffern**, also die erbrachten Leistungen,
- **Beträge und Faktoren**,
- **Behandlungsart und Vertragsart**.

Das ist kein Versehen, sondern der Zweck der Übermittlung. Eine GOÄ-Prüfung ohne Leistungen und
Daten ist keine GOÄ-Prüfung.

Für die datenschutzrechtliche Bewertung ist das der entscheidende Punkt, und er wird in
Abschnitt 5 behandelt.

### 4.3 Es ist keine Pseudonymisierung mit Schlüssel

Es wird **kein** Zuordnungsschlüssel erzeugt, gespeichert oder übertragen — weder im Skript noch
irgendwo sonst. Aus der Ausgabedatei allein lässt sich das Original nicht rekonstruieren.

Das bedeutet zugleich: Ein Befund im Bericht kann von Azmoth aus **nicht** einem Patienten
zugeordnet werden. Die Zuordnung leistet allein die Praxis, über die `rechnung/@id`, die im
Ergebnis erhalten bleibt und die die Praxis in ihrem eigenen System nachschlagen kann.

---

## 5. Datenschutzrechtliche Bewertung

> Dieser Abschnitt beschreibt die Bewertung, auf der die technische Umsetzung beruht. Er ersetzt
> keine Prüfung durch die/den Datenschutzbeauftragte(n) der Praxis. Verantwortliche im Sinne des
> Art. 4 Nr. 7 DSGVO bleibt die Praxis.

### 5.1 Der Ausgangspunkt: Art. 9 DSGVO

Rohe PADnext-Exporte enthalten Gesundheitsdaten im Sinne des Art. 4 Nr. 15 DSGVO — Name, Anschrift,
Geburtsdatum, Versichertennummer, und dazu die erbrachten ärztlichen Leistungen. Ihre Verarbeitung
ist nach **Art. 9 Abs. 1 DSGVO grundsätzlich untersagt** und nur unter den engen Voraussetzungen
des Art. 9 Abs. 2 zulässig. Hinzu kommt die strafbewehrte Schweigepflicht nach **§ 203 StGB**, die
die Praxis trifft und nicht uns.

Ein Pilotbetrieb, der rohe Exporte an einen Dienstleister überträgt, bräuchte dafür eine
tragfähige Rechtsgrundlage, einen Auftragsverarbeitungsvertrag mit vollständigem technischem
Anhang und eine Einbindung nach § 203 Abs. 3 StGB. Das ist möglich, aber es ist keine Grundlage,
auf der ein Pilot in wenigen Wochen startet.

### 5.2 Das Ziel: Erwägungsgrund 26

**Erwägungsgrund 26 zur DSGVO** stellt klar, dass die Grundsätze des Datenschutzes für
*anonyme Informationen* nicht gelten — also für Informationen, die sich nicht auf eine
identifizierte oder identifizierbare Person beziehen. Für solche Daten gilt die Verordnung nicht;
damit greift auch Art. 9 nicht.

Ob Daten anonym sind, ist nach Erwägungsgrund 26 danach zu beurteilen, welche Mittel
„nach allgemeinem Ermessen wahrscheinlich genutzt werden", um die Person zu bestimmen — und zwar
**von dem Verantwortlichen oder einer anderen Person**. Dabei sind alle objektiven Faktoren zu
berücksichtigen: Kosten, Zeitaufwand, verfügbare Technologie.

### 5.3 Die Bewertung — und wo sie unterschiedlich ausfällt

Die entscheidende Beobachtung ist, dass die Antwort **für die beiden Beteiligten verschieden**
ausfällt. Das ist keine Schwäche der Argumentation, sondern der Kern der geltenden Rechtslage
(relativer Personenbezug).

**Für Azmoth als Empfänger:** Die Ausgabedatei enthält keinen Namen, keine Anschrift, kein
Geburtsdatum, keine Versichertennummer, keine Kontaktdaten, keine Bankverbindung und keine
praxisinterne Patienten- oder Rechnungsnummer. Sie enthält eine Liste von GOÄ-Ziffern mit Daten
und Beträgen. Azmoth verfügt über **kein Zusatzwissen**, mit dem sich daraus eine Person bestimmen
ließe: kein Patientenverzeichnis, keinen Schlüssel, keinen zweiten Datenbestand zum Abgleich. Die
Mittel, die nach allgemeinem Ermessen zur Verfügung stünden, führen nicht zu einer identifizierten
Person. **Aus dieser Perspektive ist die Ausgabedatei anonym, und Art. 9 DSGVO ist nicht
einschlägig.**

**Für die Praxis:** Die Praxis besitzt weiterhin das Original und ihr Praxisverwaltungssystem. Über
`rechnung/@id` und über die Kombination aus Behandlungsdatum und Ziffernfolge kann sie den Fall
jederzeit zuordnen — sie *muss* das können, sonst wäre der Prüfbericht für sie wertlos.
**Für die Praxis bleiben die Daten daher personenbezogen**, und ihre Verarbeitung im eigenen Haus
richtet sich unverändert nach Art. 9 Abs. 2 lit. h DSGVO in Verbindung mit § 630f BGB und den
berufsrechtlichen Vorgaben. Daran ändert das Skript nichts, und es soll auch nichts daran ändern:
Die Praxis darf mit den Daten ihrer eigenen Patienten arbeiten.

**Was das Skript bewirkt**, ist damit präzise beschreibbar: Es verhindert nicht, dass die Praxis
Gesundheitsdaten verarbeitet — das darf sie. Es verhindert, dass **Azmoth** sie verarbeitet. Die
Grenze verläuft an der Praxistür, und das Skript läuft davor.

### 5.4 Restrisiko, ehrlich benannt

Die Bewertung in 5.3 hat zwei Voraussetzungen, die nicht automatisch erfüllt sind.

**Erstens: der Freitext.** Bleibt ein Name in einer `<begruendung>` stehen, ist die Datei nicht
anonym, und die gesamte Argumentation entfällt für diese Lieferung. Die Restbefundprüfung
(Abschnitt 4.1) adressiert das, ersetzt aber nicht den Blick eines Menschen. **Dies ist das
größte verbliebene Risiko der Anonymisierung.**

**Zweitens: Singularität.** Ein sehr ungewöhnlicher Behandlungsverlauf — eine seltene
Ziffernkombination an einem bestimmten Tag — kann theoretisch auch ohne Namen auf eine Person
hindeuten, wenn jemand über passendes Zusatzwissen verfügt. Bei einer Rechnungsprüfung mit
gängigen GOÄ-Positionen ist dieses Risiko gering, aber es ist nicht null. Praxen mit sehr kleinen,
hochspezialisierten Patientenkollektiven sollten es mit ihrer/ihrem DSB besprechen.

Wir halten diese Risiken für beherrschbar und für deutlich kleiner als die Alternative — die
Übertragung roher Exporte. Wir halten es aber für falsch, sie zu verschweigen.

### 5.5 Warum eine fehlende Kennzeichnung abgewiesen wird

Bis vor dieser Änderung galt: Eine Lieferung ohne erkennbares `echtdaten` wurde geprüft, und der
Bericht trug den Hinweis „Es wurde von Testdaten ausgegangen".

Diesen Satz muss man von hinten lesen. Eine Praxis exportiert aus einem System, das
`echtdaten="ja"` schreibt, lädt echte Patientendaten hoch — und bekommt mitgeteilt, dass wir
angenommen haben, sie seien es nicht. Die Annahme trug die gesamte Rechtmäßigkeit der
Verarbeitung, und die Datei hatte nichts gesagt, was sie gestützt hätte.

Die Abwägung ist eindeutig, weil die Fehlerkosten es sind:

| | Kosten |
|---|---|
| Eine anonymisierte Lieferung wird abgewiesen, weil sie sich nicht erklärt hat | Ein Befehl, ein erneuter Upload |
| Eine echte Lieferung wird als Testdaten geprüft | Verarbeitung von Gesundheitsdaten nach Art. 9 DSGVO ohne Rechtsgrundlage, § 203 StGB für die Praxis, Meldepflicht nach Art. 33 DSGVO |

Deshalb gilt jetzt:

| `echtdaten` | Verhalten |
|-------------|-----------|
| `"1"` oder `"true"` | **Abweisung** — `422 REAL_DATA_REFUSED` |
| `"0"` oder `"false"` | Prüfung läuft |
| jeder andere Wert (`"ja"`, `"yes"`, `"nein"`, `"2"`, `""`) | **Abweisung** — `422 ECHTDATEN_UNDECLARED` |
| Attribut fehlt vollständig | **Abweisung** — `422 ECHTDATEN_UNDECLARED` |

Auch `"nein"` wird abgewiesen. Die Regel lautet nicht „weise ab, was bejahend aussieht", sondern
„weise ab, was diese Engine raten müsste" — eine Regel, die Deutsch zu interpretieren versuchte,
würde irgendwann ein Wort falsch herum verstehen.

Die technische Umsetzung steht in `apps/engine/app/padnext/reader.py` (`parse_echtdaten`) und
`apps/engine/app/padnext/audit.py` (`EchtdatenUndeclared`). Beide sind durch Tests in
`apps/engine/tests/test_padnext.py` und `apps/engine/tests/test_error_handling.py` abgesichert,
einschließlich des Falls `echtdaten="ja"`.

---

## 6. Ablauf im Pilotbetrieb

1. Export aus dem Praxisverwaltungssystem als `.padx` oder `*_padx.xml`.
2. `python3 scripts/anonymize_padnext.py <export> -o <ausgabe>`
3. **Die Ausgabe des Skripts lesen.** Insbesondere:
   - die Zeile zu `echtdaten` — stand dort vorher `"1"` oder `"ja"`?
   - den Abschnitt „RESTBEFUNDE IM FREITEXT", falls vorhanden.
4. Gemeldete Freitextstellen prüfen. Falls sie Patientendaten enthalten: im
   Praxisverwaltungssystem korrigieren und neu exportieren, oder `--redact-freetext` verwenden und
   den Verlust an Prüftiefe in Kauf nehmen.
5. **Nur die Ausgabedatei** hochladen.
6. Das Original verbleibt in der Praxis und wird nicht übertragen.

### Kontrolle vor dem ersten Echtlauf

Es empfiehlt sich, die Ausgabedatei beim ersten Mal in einem Texteditor zu öffnen (bei einem
`.padx`-Container: entpacken) und nach dem Namen einer bekannten Patientin zu suchen. Das dauert
zwei Minuten und ist der einzige Test, der die gesamte Kette abdeckt.

---

## 7. Was Azmoth speichert

Ergänzend, weil es zur selben Frage gehört: Auch aus einer anonymisierten Lieferung liest die
Engine keine Identität. Die Datenmodelle in `apps/engine/app/schemas/padnext.py` besitzen kein
Feld für Name, Anschrift oder Geburtsdatum — ein Test (`test_no_parsed_model_can_hold_patient_identity`)
stellt sicher, dass sich das nicht unbemerkt ändert. Ein Feld, das es nicht gibt, kann nicht
befüllt, nicht protokolliert und nicht exportiert werden.

Einzelheiten dazu: [`docs/DATA_HANDLING_POLICY.md`](../DATA_HANDLING_POLICY.md) und
[`docs/AVV_TECHNICAL_ANNEX_DRAFT.md`](../AVV_TECHNICAL_ANNEX_DRAFT.md).

---

## 8. Verweise

| Thema | Datei |
|-------|-------|
| Das Skript | [`scripts/anonymize_padnext.py`](../../scripts/anonymize_padnext.py) |
| Fehlercodes der API | [`docs/errors.md`](../errors.md) |
| Was gespeichert wird | [`docs/DATA_HANDLING_POLICY.md`](../DATA_HANDLING_POLICY.md) |
| Offene Punkte, ehrlich geführt | [`docs/compliance/PRIVATE_DATA_WARNING.md`](../compliance/PRIVATE_DATA_WARNING.md) |
| AVV-Anhang (Entwurf) | [`docs/AVV_TECHNICAL_ANNEX_DRAFT.md`](../AVV_TECHNICAL_ANNEX_DRAFT.md) |
| Ablauf des Pilotbetriebs | [`docs/pilot/PILOT_DEMO_GUIDE.md`](PILOT_DEMO_GUIDE.md) |
