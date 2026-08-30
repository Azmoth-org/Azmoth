# Anlage: Technische und organisatorische Maßnahmen (Entwurf)

**Anlage zum Vertrag über die Auftragsverarbeitung gemäß Art. 28 DSGVO**

> **ENTWURF — noch nicht anwaltlich geprüft.**
>
> Dieses Dokument beschreibt den technischen Ist-Zustand der Azmoth-Engine, damit eine
> Rechtsanwältin oder ein Rechtsanwalt daraus eine belastbare Anlage zum
> Auftragsverarbeitungsvertrag formulieren kann. Es ist **keine Rechtsberatung** und ersetzt keine
> juristische Prüfung. Jede Aussage ist so formuliert, dass sie am Quellcode überprüfbar ist; die
> jeweils maßgebliche Datei oder Einstellung ist genannt.
>
> Grundlage ist [`DATA_HANDLING_POLICY.md`](DATA_HANDLING_POLICY.md), das denselben Sachverhalt in
> weniger formaler Sprache beschreibt. Bei Widersprüchen zwischen beiden Dokumenten ist der
> Quellcode maßgeblich, und das Widersprüchliche ist ein Fehler, der zu melden ist.
>
> **Offene Punkte für die rechtliche Prüfung** sind in [§ 9](#9-offene-punkte) gesammelt und
> bewusst nicht beschönigt.

---

## 1. Gegenstand und Dauer der Verarbeitung

### 1.1 Gegenstand

Der Auftragnehmer prüft im Auftrag des Verantwortlichen bereits kodierte Abrechnungsdaten im Format
**PADnext (ADL, Version 2.12)** gegen die **Gebührenordnung für Ärzte (GOÄ)** und stellt das
Prüfergebnis als strukturierte JSON-Antwort sowie als PDF-Bericht bereit.

Die Prüfung ist **deterministisch und regelbasiert**. Es kommt kein Verfahren des maschinellen
Lernens und kein Sprachmodell zum Einsatz; es findet keine automatisierte Entscheidungsfindung im
Sinne des Art. 22 DSGVO statt, da das Ergebnis ein Prüfhinweis ist und keine Rechtsfolge auslöst.
Die Verantwortung für die Rechnung verbleibt beim Rechnungssteller.

### 1.2 Dauer

Die Verarbeitung erfolgt für die Laufzeit des Hauptvertrags. Die Aufbewahrungsfristen der einzelnen
Datenkategorien sind in [§ 4](#4-speicherdauer-und-löschung) geregelt und unterscheiden sich
erheblich: die hochgeladene Ursprungsdatei wird nach Abschluss der Prüfung automatisch gelöscht,
das Prüfergebnis bleibt bis zur Löschung auf Weisung des Verantwortlichen bestehen.

### 1.3 Art und Zweck

| Zweck | Verarbeitungsschritt |
| --- | --- |
| Prüfung einer Einzelrechnung | Entgegennahme der PADnext-Datei, Prüfung, Rückgabe des Ergebnisses; **keine Speicherung** |
| Prüfung eines Rechnungsstapels | Entgegennahme eines ZIP-Archivs, temporäre Speicherung, Prüfung je Lieferung, Speicherung des Ergebnisses |
| Bereitstellung eines Prüfberichts | Erzeugung eines PDF aus dem gespeicherten Ergebnis |
| Abrechnung der Leistung | Zählung der Anfragen je Organisation und Schlüssel |
| Betrieb und Fehlerbehebung | Protokollierung von Anfragen und unerwarteten Fehlern |

---

## 2. Art der Verarbeitung (Verarbeitungsschritte)

Die technischen Schritte im Einzelnen:

1. **Entgegennahme.** Übertragung der PADnext-Datei über HTTPS an
   `POST /api/v1/audit/single` (Einzeldatei) oder `POST /api/v1/audit/bulk` (ZIP-Archiv).
   Authentifizierung über einen API-Schlüssel; siehe [§ 6.1](#61-zugangskontrolle).
2. **Formatprüfung.** Erkennung des Dateityps anhand der ersten Bytes, nicht anhand des
   Dateinamens. PDF- oder JSON-Inhalte werden mit `400 UNSUPPORTED_INPUT_FORMAT` abgewiesen
   (`app/padnext/formats.py`).
3. **XML-Verarbeitung.** Auspacken eines `.padx`-Containers, Validierung gegen ein
   XML-Schema, Auslesen der abrechnungsrelevanten Felder (`app/padnext/reader.py`). Der Umfang der
   ausgelesenen Felder ist in [§ 3.2](#32-tatsächlich-verarbeitete-datenfelder) abschließend
   aufgeführt.
4. **Regelprüfung.** Auswertung durch ein Datalog-Programm (Soufflé) und, sofern eine echte
   Auswahlentscheidung zu treffen ist, durch einen ASP-Solver (Clingo). Beide laufen **lokal im
   Container**; es erfolgt kein Netzwerkzugriff nach außen.
5. **Ergebniserstellung.** Erzeugung eines JSON-Berichts je Lieferung mit Prüfvermerk je Position,
   Belegstelle und Regel-ID sowie eines SHA-256-Prüfwerts (`receipt_hash`) über Katalog, Regelstand,
   Logikprogramme, Solver-Versionen und Eingabe.
6. **Optionale PDF-Erzeugung.** Rendern eines Prüfberichts aus dem gespeicherten Ergebnis
   (`app/services/pdf.py`). Auch dies erfolgt lokal, ohne externe Bibliothek und ohne Netzwerkzugriff.
7. **Löschung der Ursprungsdatei.** Nach Erreichen eines Endzustands der Stapelprüfung wird das
   hochgeladene Archiv gelöscht (`app/services/uploads.py`).

---

## 3. Art der personenbezogenen Daten

### 3.1 Kategorien

Gegenstand der Verarbeitung ist eine **PADnext-Abrechnungsdatei**. Eine solche Datei kann
Gesundheitsdaten im Sinne des Art. 9 Abs. 1 DSGVO enthalten, da abgerechnete GOÄ-Ziffern
Rückschlüsse auf erbrachte Leistungen und damit auf den Gesundheitszustand zulassen, und kann
darüber hinaus Angaben zur Person des Patienten enthalten.

**Der Auftragnehmer weist ausdrücklich darauf hin:** eine PADnext-Datei ist auch dann als
Gesundheitsdatum zu behandeln, wenn Namensfelder entfernt wurden, solange Leistungsziffern und
Behandlungsdaten enthalten sind.

### 3.2 Tatsächlich verarbeitete Datenfelder

Die Prüfsoftware liest aus der übermittelten Datei **ausschließlich** die folgenden Felder aus:

| Feld | Zweck |
| --- | --- |
| GOÄ-Ziffer, Steigerungsfaktor, Anzahl, Einzel- und Gesamtbetrag | Kern der Regelprüfung |
| Leistungsdatum | Zeitbezogene Regeln |
| Begründungstext (`begruendung`) | Prüfung nach § 12 Abs. 3 GOÄ |
| Punktzahl, Punktwert, Minderungssatz | Nachrechnung des Betrags |
| Behandlungsart, Vertragsart | Auswahl des anwendbaren Regelwerks |
| Nachrichtentyp, Version, Kennzeichen `echtdaten` | Format- und Zulässigkeitsprüfung |

**Nicht ausgelesen** und daher weder im Prüfergebnis noch in der Datenbank noch in Protokollen
enthalten sind insbesondere: Name, Anschrift, Geburtsdatum und Versichertennummer des Patienten.
Diese Felder können in der übermittelten Datei enthalten sein; sie werden von der Software nicht in
eine verarbeitete Struktur übernommen. Solange die hochgeladene Datei auf dem Datenträger liegt
(siehe [§ 4](#4-speicherdauer-und-löschung)), ist sie gleichwohl vollumfänglich als
personenbezogenes Datum zu behandeln.

### 3.3 Kategorien betroffener Personen

- Patientinnen und Patienten des Verantwortlichen (Rechnungsempfänger)
- Behandelnde Ärztinnen und Ärzte, soweit in der Lieferung als Leistungserbringer benannt
- Beschäftigte des Verantwortlichen, soweit sie die Anwendung nutzen (Benutzerkennung, E-Mail-Adresse)

### 3.4 Ausschluss von Echtdaten im Regelbetrieb

Eine Lieferung mit dem Kennzeichen `auftrag/@echtdaten="1"` wird **abgewiesen**
(`422 REAL_DATA_REFUSED`) und weder geprüft noch gespeichert. Die Einstellung
`PADNEXT_ALLOW_REAL_DATA` steht standardmäßig auf `false`.

Die Verarbeitung von Echtdaten setzt das Vorliegen dieses Vertrags, eine dokumentierte
Rechtsgrundlage sowie die ausdrückliche Umstellung dieser Einstellung durch den Auftragnehmer
voraus. Sie ist keine Berechtigung, die ein Aufrufer technisch erlangen kann.

---

## 4. Speicherdauer und Löschung

| Datenkategorie | Speicherort | Dauer |
| --- | --- | --- |
| Hochgeladenes ZIP-Archiv einer Stapelprüfung | Lokaler Datenträger (`UPLOAD_DIR`) | Bis zum Endzustand des Auftrags; danach **automatische Löschung** |
| Einzeldatei bei `POST /audit/single` | Ausschließlich Arbeitsspeicher | **Keine Speicherung** |
| Prüfergebnis (JSON je Lieferung, Gesamtauswertung) | PostgreSQL | Bis zur Löschung auf Weisung |
| API-Schlüssel | PostgreSQL, **ausschließlich als SHA-256-Hashwert** | Bis zum Widerruf; die Zeile bleibt zu Nachweiszwecken bestehen |
| Verbrauchsdaten (Anzahl, Bytes, Dauer, Statuscode) | PostgreSQL | Zur Abrechnung; enthält keine Rechnungsinhalte |
| Fehlerprotokoll unerwarteter Fehler | PostgreSQL | Diagnosezweck; jederzeit löschbar |
| Anfrageprotokolle | Standardausgabe des Containers | Nach der Protokollaufbewahrung der Betriebsumgebung |

Die automatische Löschung des Archivs erfolgt beim Übergang des Auftrags nach `COMPLETED` oder
`FAILED` — also zu dem Zeitpunkt, zu dem die Daten nicht mehr benötigt werden, und nicht erst nach
Ablauf einer Frist. Ein durch einen Neustart unterbrochener Auftrag behält sein Archiv, damit er
fortgesetzt werden kann; die Löschung erfolgt nach dessen Abschluss.

Löschung auf Weisung des Verantwortlichen erfolgt derzeit **manuell** durch den Auftragnehmer
(siehe [§ 9](#9-offene-punkte)).

---

## 5. Ort der Verarbeitung und Unterauftragsverarbeiter

### 5.1 Ort

Die Verarbeitung erfolgt ausschließlich auf Systemen innerhalb der Europäischen Union. Eine
Übermittlung in ein Drittland findet nicht statt.

### 5.2 Unterauftragsverarbeiter

**Derzeit keine.** Die Prüfung erfolgt vollständig innerhalb der Anwendung des Auftragnehmers. Es
werden insbesondere **nicht** eingesetzt:

- Dienste zur Textanalyse, Übersetzung oder Verarbeitung durch Sprachmodelle,
- externe Protokollierungs- oder Analysedienste,
- externe Speicher- oder Objektspeicherdienste.

Der Auftragnehmer hat technisch die Möglichkeit vorgesehen, einen Dienst zur Fehlerüberwachung
anzubinden (`app.core.observability.set_error_hook`). Ein solcher Dienst ist **nicht aktiviert**.
Wird er aktiviert, erhält er ausschließlich die in [§ 6.4](#64-protokollierung) genannten Felder —
keine Rechnungsinhalte — und ist vor Aufnahme des Betriebs als Unterauftragsverarbeiter zu
benennen und vom Verantwortlichen zu genehmigen.

---

## 6. Technische und organisatorische Maßnahmen (Art. 32 DSGVO)

### 6.1 Zugangskontrolle

- **Zwei getrennte Authentifizierungswege.** Die Weboberfläche authentifiziert über eine
  Sitzung, die gegen die Datenbank geprüft wird. Die Programmierschnittstelle authentifiziert über
  einen API-Schlüssel im Header `X-API-Key`, der bei jeder Anfrage gegen die Datenbank geprüft wird
  (`app/api/apikeys.py`).
- **API-Schlüssel werden nicht im Klartext gespeichert.** Gespeichert wird ein
  **SHA-256-Hashwert** des Schlüssels sowie ein nicht zur Authentifizierung geeignetes öffentliches
  Präfix. Der Schlüssel selbst wird genau einmal — in der Antwort auf seine Erzeugung — ausgegeben
  und ist danach auch für den Auftragnehmer nicht wiederherstellbar. Ein Datenbankabzug enthält
  folglich keine verwendbaren Zugangsdaten.
- **Vergleich in konstanter Zeit** (`hmac.compare_digest`), um Rückschlüsse über Laufzeiten
  auszuschließen.
- **Widerruf** erfolgt sofort und für jede weitere Anfrage; die Zeile bleibt zu Nachweiszwecken
  erhalten.

### 6.2 Zugriffskontrolle und Mandantentrennung

- Jeder API-Schlüssel ist genau einer Organisation zugeordnet. Die Organisation wird **aus dem
  Datenbankeintrag des Schlüssels** entnommen und nicht aus der Anfrage. Es existiert kein
  Parameter, mit dem ein Aufrufer eine andere Organisation benennen könnte.
- Jede Lese- und Schreiboperation auf Aufträgen, Ergebnissen und Verbrauchsdaten wird auf die
  Organisation gefiltert. Ein Auftrag einer anderen Organisation wird mit `404` beantwortet, nicht
  mit `403`, damit über die Antwort nicht auf die Existenz fremder Aufträge geschlossen werden kann.

### 6.3 Eingabekontrolle und Integrität

- **Formatprüfung anhand der Byte-Signatur**, nicht anhand des Dateinamens.
- **Schutz vor Dekompressionsangriffen**: Archive werden gegen die deklarierte und zusätzlich gegen
  die tatsächlich entpackte Größe geprüft; Einträge, die das Archivwurzelverzeichnis verlassen,
  werden abgewiesen.
- **Größenbegrenzungen**: 5 MiB je Einzellieferung, 50 MB je Archiv, 256 MiB entpackt, höchstens
  500 Lieferungen je Auftrag.
- **Ratenbegrenzung** je Schlüssel: 100 Anfragen pro Minute für Einzelprüfungen, 10 Uploads pro
  Stunde für Stapelprüfungen.
- **Nachweisbarkeit des Ergebnisses**: jedes Prüfergebnis trägt einen SHA-256-Prüfwert über
  Katalogfassung, Regelstand, Logikprogramme, Solver-Versionen und Eingabe. Damit ist überprüfbar,
  unter welchem Systemstand ein Ergebnis entstanden ist.

### 6.4 Protokollierung

- Jede Anfrage erhält eine **Vorgangsnummer** (`X-Request-ID`), die in jeder zugehörigen
  Protokollzeile erscheint und dem Aufrufer im Fehlerfall mitgeteilt wird. Damit ist eine Rückfrage
  ohne Übermittlung von Rechnungsinhalten möglich.
- Protokolle werden **strukturiert als JSON** geschrieben und enthalten je Anfrage: Vorgangsnummer,
  Zeitpunkt, Endpunkt (als Muster, nicht als aufgelöster Pfad), Statuscode, Dauer sowie — soweit
  bekannt — Schlüsselkennung, Organisation und Auftragsnummer.
- **Nicht protokolliert werden**: Anfrage- und Antwortinhalte, Dateinamen hochgeladener Dateien,
  GOÄ-Ziffern, Beträge, weitere Header-Werte sowie lokale Variablen aus Programmabbrüchen.
- Unerwartete Fehler werden zusätzlich in einer Tabelle erfasst (Fehlertyp, Fehlermeldung,
  Endpunkt, Vorgangsnummer, Organisation). Auch diese Tabelle enthält keine Rechnungsinhalte und
  kann daher von Betriebspersonal eingesehen werden, das keinen Zugang zu Gesundheitsdaten hat.

### 6.5 Trennung von Programm und Daten

- Die Anwendung läuft in einem Container unter einer **nicht privilegierten Kennung** (UID 10001).
- Das Anwendungsverzeichnis ist für diese Kennung **nicht beschreibbar**. Schreibzugriff besteht
  ausschließlich auf ein eigens eingebundenes Verzeichnis für Uploads.
- Prüfregeln und Gebührenkatalog sind versionierte Quelldaten und werden zur Laufzeit **nicht
  verändert**; Entscheidungen einer Prüfkraft werden getrennt in der Datenbank abgelegt.

### 6.6 Verfügbarkeit und Wiederherstellbarkeit

- Die Datenbank (PostgreSQL) wird auf einem persistenten, verschlüsselten Datenträger betrieben.
- Sicherung und Wiederherstellung erfolgen über dokumentierte Skripte
  (`make backup-db` / `make restore-db`, siehe `docs/OPERATIONS.md`).
- Ein durch einen Neustart unterbrochener Stapelauftrag wird automatisch fortgesetzt; bereits
  erzeugte Ergebnisse werden nicht erneut berechnet.

### 6.7 Organisatorische Maßnahmen

- Änderungen am Quellcode erfolgen über nachvollziehbare Pull Requests mit automatisierter
  Prüfung (Tests, Typprüfung, Vertragsabgleich).
- Änderungen an Regeldaten erfolgen in einem eigenen Zweig und erfordern eine gesonderte Freigabe.
- Der Zugriff auf Produktionssysteme ist auf die betriebsführenden Personen beschränkt.

---

## 7. Unterstützung des Verantwortlichen

Der Auftragnehmer unterstützt den Verantwortlichen bei:

- **Auskunft (Art. 15)** — durch Auswertung der zu einer Organisation gespeicherten Prüfergebnisse.
- **Löschung (Art. 17)** — durch Löschung der Prüfergebnisse einer Organisation; die
  Ursprungsdateien sind zu diesem Zeitpunkt bereits automatisch gelöscht.
- **Datenübertragbarkeit (Art. 20)** — die Prüfergebnisse sind über die Schnittstelle als JSON und
  als CSV-Archiv abrufbar.
- **Meldung von Verletzungen (Art. 33)** — unverzügliche Unterrichtung nach Kenntniserlangung.

---

## 8. Rückgabe und Löschung nach Vertragsende

Nach Beendigung des Vertrags werden auf Weisung des Verantwortlichen sämtliche Prüfergebnisse
gelöscht oder in maschinenlesbarer Form herausgegeben. Ursprungsdateien sind zu diesem Zeitpunkt
bereits gelöscht. Verbrauchsdaten werden für die Dauer handels- und steuerrechtlicher
Aufbewahrungsfristen aufbewahrt, soweit sie Grundlage einer Rechnungsstellung waren; sie enthalten
keine personenbezogenen Daten der betroffenen Personen.

---

## 9. Offene Punkte

Für die anwaltliche Prüfung ausdrücklich benannt. Ein Vertrag, der diese Punkte nicht adressiert,
ist unvollständig.

1. **Löschung auf Weisung ist derzeit ein manueller Vorgang.** Es existiert keine
   Selbstbedienungsfunktion. Zu regeln: Frist und Nachweis der Ausführung.
2. **Keine automatische Aufbewahrungsfrist für Prüfergebnisse.** Diese bleiben bis zur Löschung auf
   Weisung bestehen. Zu regeln: Regelaufbewahrungsdauer.
3. **Keine feldbezogene Verschlüsselung.** Der Schutz erfolgt auf Ebene des Datenträgers und des
   Netzwerks. Eine Person mit administrativem Datenbankzugang kann gespeicherte Prüfergebnisse
   einsehen. Zu regeln: Kreis der Berechtigten und Verpflichtung auf Vertraulichkeit.
4. **Kein durchgeführter Penetrationstest, keine Zertifizierung** nach ISO 27001 oder SOC 2.
5. **Sicherungen liegen in der Verantwortung der Betriebsumgebung.** Zu regeln:
   Wiederherstellungszeit und Nachweis erfolgreicher Testwiederherstellungen.
6. **Verarbeitung von Echtdaten ist technisch gesperrt.** Die Aufhebung dieser Sperre ist als
   ausdrücklicher, dokumentierter Schritt zu vereinbaren.
7. **Ratenbegrenzung wirkt je Prozess.** Bei mehreren Instanzen vervielfacht sich die tatsächliche
   Grenze. Für Zusagen zur Verfügbarkeit relevant.
8. **Verbrauchsdaten werden gepuffert geschrieben.** Bei einem Prozessabbruch können einzelne
   Einträge verlorengehen. Für Abrechnungszwecke ist zu vereinbaren, dass im Zweifel zugunsten des
   Verantwortlichen gezählt wird.

---

*Erstellt auf Grundlage des Quellstands zum Zeitpunkt der Erstellung dieses Dokuments. Bei jeder
Änderung an Speicherung, Protokollierung oder Aufbewahrung ist diese Anlage im selben Pull Request
anzupassen.*
