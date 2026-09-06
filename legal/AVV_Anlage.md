# Anlage zum Vertrag über die Auftragsverarbeitung

**Status: Entwurf — ersetzt keine anwaltliche Prüfung**

**Betriebsmodus: Pilotbetrieb ausschließlich mit synthetischen Testdaten — keine
Verarbeitung personenbezogener Daten.**

Anlage gemäß Art. 28 Abs. 3 DSGVO zum Vertrag über die Auftragsverarbeitung zwischen dem
Verantwortlichen und dem Auftragnehmer über die Nutzung der Anwendung **Azmoth** — Prüfung
privatärztlicher Abrechnungslieferungen im Format PADnext (ADL 2.12) gegen die Gebührenordnung für
Ärzte (GOÄ).

| Angabe | Wert |
| --- | --- |
| Dokument | Anlage zum Auftragsverarbeitungsvertrag (Art. 28 Abs. 3 DSGVO) |
| Auftragnehmer (Auftragsverarbeiter) | Azmoth, Bureau 5, Centre Aziza, 1. Etage, Av. de l'Indépendance, Menzel Bourguiba 7050, Tunesien |
| Vertretungsberechtigt | Oussama Khadraoui |
| Kontakt für Datenschutzanfragen | contact@azmoth.com, +216 50 745 682 |
| Verantwortlicher | [FIRMENNAME des Verantwortlichen], [ADRESSE] |
| Version | 0.2 |
| Stand | 2026-09-06 |
| Nächste Überprüfung | 07.09.2027 |

**Version 0.1** — Ersterstellung, 2026-09-06.
**Version 0.2** — 07.09.2026 — Platzhalter ergänzt; Art.-27-Abschnitt aufgenommen.

> **Hinweis zum Stand.** Ein Auftragsverarbeitungsvertrag ist zum Stand dieses Dokuments **nicht
> abgeschlossen**, weder mit einem Verantwortlichen noch als gegengezeichneter Vertrag mit
> sämtlichen Unterauftragsverarbeitern. Diese Anlage beschreibt den technischen Ist-Zustand, damit
> daraus eine belastbare Vertragsanlage formuliert werden kann. Der Betrieb erfolgt bis dahin
> **ausschließlich mit synthetischen Testdaten** (§ 8).

---

## 1. Gegenstand, Art und Zweck der Verarbeitung (Art. 28 Abs. 3 Satz 1 DSGVO)

### 1.1 Gegenstand

Der Auftragnehmer prüft im Auftrag und nach Weisung des Verantwortlichen bereits kodierte
Abrechnungsdaten im Format **PADnext (ADL, Version 2.12)** gegen die **GOÄ** und stellt das
Prüfergebnis als strukturierte JSON-Antwort sowie wahlweise als PDF-Prüfbericht bereit.

### 1.2 Art der Verarbeitung

Erhebung, Speicherung (soweit in § 4 vorgesehen), Auslesen, Abfragen, Verwendung zur regelbasierten
Prüfung, Bereitstellung des Ergebnisses und Löschung. Die einzelnen Verarbeitungsschritte:

1. **Entgegennahme** der Datei über HTTPS an `POST /api/v1/audit/single` (Einzellieferung) oder
   `POST /api/v1/audit/bulk` (ZIP-Archiv); Authentifizierung über einen API-Schlüssel.
2. **Formatprüfung** anhand der Byte-Signatur, nicht anhand des Dateinamens.
3. **XML-Verarbeitung**: Auspacken eines `.padx`-Containers, Prüfung des Dokumentrahmens gegen ein
   XML-Schema, Auslesen der abrechnungsrelevanten Felder nach § 3.2.
4. **Regelprüfung** durch ein Datalog-Programm (Soufflé) und, sofern eine echte
   Auswahlentscheidung zu treffen ist, durch einen ASP-Solver (Clingo). Beide laufen **lokal im
   Container**; ein Netzwerkzugriff nach außen findet nicht statt.
5. **Ergebniserstellung** je Lieferung mit Prüfvermerk je Position, Belegstelle und Regel-ID sowie
   einem SHA-256-Prüfwert (`receipt_hash`) über Katalogfassung, Regelstand, Logikprogramme,
   Solver-Versionen und Eingabe.
6. **Optionale PDF-Erzeugung** aus dem gespeicherten Ergebnis, lokal und ohne Netzwerkzugriff.
7. **Löschung der Ursprungsdatei** beim Erreichen eines Endzustands der Stapelprüfung.

Die Prüfung ist **deterministisch und regelbasiert**. Es kommt kein Verfahren des maschinellen
Lernens und kein Sprachmodell zum Einsatz. Eine automatisierte Entscheidung im Sinne des Art. 22
DSGVO findet nicht statt: das Ergebnis ist ein Prüfhinweis mit dem Status *Entwurf*, die Freigabe
erfolgt durch eine namentlich benannte Person, und die Verantwortung für die Rechnung verbleibt
beim Rechnungssteller.

### 1.3 Zweck

| Zweck | Verarbeitungsschritt |
| --- | --- |
| Prüfung einer Einzelrechnung | Entgegennahme, Prüfung, Rückgabe des Ergebnisses; **keine Speicherung** |
| Prüfung eines Rechnungsstapels | Entgegennahme eines Archivs, temporäre Speicherung, Prüfung je Lieferung, Speicherung des Ergebnisses |
| Bereitstellung eines Prüfberichts | Erzeugung eines PDF aus dem gespeicherten Ergebnis |
| Abrechnung der Leistung | Zählung der Anfragen je Organisation und Schlüssel |
| Betrieb und Fehlerbehebung | Protokollierung von Anfragen und unerwarteten Fehlern |

---

## 2. Dauer der Verarbeitung

Die Verarbeitung erfolgt für die Laufzeit des Hauptvertrags. Die Aufbewahrungsfristen der einzelnen
Datenkategorien sind in § 4 geregelt und unterscheiden sich erheblich: eine Einzelprüfung wird gar
nicht gespeichert, die hochgeladene Archivdatei einer Stapelprüfung wird nach Abschluss der Prüfung
automatisch gelöscht, das Prüfergebnis unterliegt einer konfigurierbaren Aufbewahrungsfrist.

---

## 3. Art der personenbezogenen Daten und Kategorien betroffener Personen

### 3.1 Kategorien personenbezogener Daten

Gegenstand der Verarbeitung ist eine **PADnext-Abrechnungsdatei**. Eine solche Datei kann
**Gesundheitsdaten im Sinne des Art. 9 Abs. 1 DSGVO** enthalten, da abgerechnete GOÄ-Ziffern
Rückschlüsse auf erbrachte Leistungen und damit auf den Gesundheitszustand zulassen, und kann
darüber hinaus Angaben zur Person der Patientin oder des Patienten enthalten.

**Der Auftragnehmer weist ausdrücklich darauf hin:** eine PADnext-Datei ist auch dann als
Gesundheitsdatum zu behandeln, wenn Namensfelder entfernt wurden, solange Leistungsziffern und
Behandlungsdaten enthalten sind. Eine Re-Identifizierung aus einem kleinen klinischen Datensatz ist
häufig möglich.

Ferner verarbeitet werden **Bestandsdaten der Nutzenden** des Verantwortlichen: Name und
E-Mail-Adresse zur Kontoführung, Sitzungsdaten sowie die Zuordnung zur Organisation.

### 3.2 Tatsächlich ausgelesene Datenfelder

Die Prüfsoftware liest aus der übermittelten Datei **ausschließlich** die folgenden Felder aus:

| Feld | Zweck |
| --- | --- |
| GOÄ-Ziffer, Steigerungsfaktor, Anzahl, Einzel- und Gesamtbetrag | Kern der Regelprüfung |
| Leistungsdatum | Zeitbezogene Regeln |
| Begründungstext (`begruendung`), Leistungstext (`text`) | Prüfung nach § 12 Abs. 3 GOÄ |
| Punktzahl, Punktwert, Minderungssatz | Nachrechnung des Betrags |
| Behandlungsart, Vertragsart | Auswahl des anwendbaren Regelwerks |
| Nachrichtentyp, Version, Kennzeichen `echtdaten` | Format- und Zulässigkeitsprüfung |

**Nicht ausgelesen** und daher weder im Prüfergebnis noch in der Datenbank noch in Protokollen
enthalten sind insbesondere **Name, Anschrift, Geburtsdatum und Versichertennummer** der Patientin
oder des Patienten. Die verarbeitenden Datenstrukturen besitzen für diese Angaben **kein Feld**;
ein automatisierter Test prüft dies bei jedem Lauf und schlägt fehl, sobald ein solches Feld
entstünde (`test_no_parsed_model_can_hold_patient_identity`).

**Einschränkung, die der Auftragnehmer ausdrücklich benennt:** Diese Angaben können in der
übermittelten Datei gleichwohl enthalten sein. Solange eine hochgeladene Datei auf dem Datenträger
liegt (§ 4), ist sie **in vollem Umfang als personenbezogenes Datum zu behandeln**. Zudem bleiben
freie Textfelder erhalten, weil sie den Gegenstand der Prüfung nach § 12 Abs. 3 GOÄ bilden — ein
Name, den eine behandelnde Person in einen Begründungssatz geschrieben hat, überdauert die
Verarbeitung.

### 3.3 Kategorien betroffener Personen

- Patientinnen und Patienten des Verantwortlichen (Rechnungsempfänger);
- behandelnde Ärztinnen und Ärzte, soweit in der Lieferung als Leistungserbringer benannt;
- Beschäftigte des Verantwortlichen, soweit sie die Anwendung nutzen (Benutzerkennung,
  Name, E-Mail-Adresse, Sitzungsdaten).

---

## 4. Speicherdauer, Löschung und Rückgabe (Art. 28 Abs. 3 lit. g DSGVO)

### 4.1 Speicherorte und Fristen

| Datenkategorie | Speicherort | Dauer |
| --- | --- | --- |
| Einzellieferung bei `POST /api/v1/audit/single` | Ausschließlich Arbeitsspeicher | **Keine Speicherung** |
| Hochgeladenes ZIP-Archiv einer Stapelprüfung | Datenträger der virtuellen Maschine (`UPLOAD_DIR`) | Bis zum Endzustand des Auftrags (`COMPLETED`/`FAILED`), dann **automatische Löschung** |
| Prüfergebnisse, Aufträge, Vorschläge | PostgreSQL (Neon, Frankfurt) | `DATA_RETENTION_DAYS`, Voreinstellung **90 Tage**, im Pilotbetrieb **30 Tage** |
| Fehlerprotokoll (`error_log`) | PostgreSQL | `DATA_RETENTION_DAYS` |
| Verbrauchsdaten (Anzahl, Bytes, Dauer, Statuscode) | PostgreSQL | Zur Abrechnung; **ohne Rechnungsinhalte** |
| API-Schlüssel | PostgreSQL, **ausschließlich als SHA-256-Hashwert** | Bis zum Widerruf; die Zeile bleibt zu Nachweiszwecken |
| Nachweisprotokoll `audit_events` | PostgreSQL | **Wird nicht gelöscht** (§ 4.3) |
| Anfrageprotokolle | Standardausgabe des Containers | Nach der Protokollaufbewahrung der Betriebsumgebung |
| Verschlüsselte Datenbanksicherungen | Amazon S3, Frankfurt | **Derzeit unbefristet** (§ 4.4) |

Die automatische Löschung des Archivs erfolgt beim Übergang des Auftrags nach `COMPLETED` oder
`FAILED` — also zu dem Zeitpunkt, zu dem die Daten nicht mehr benötigt werden, und nicht erst nach
Ablauf einer Frist. Ein durch einen Neustart unterbrochener Auftrag behält sein Archiv, damit er
fortgesetzt werden kann; die Löschung erfolgt nach dessen Abschluss.

### 4.2 Löschroutine

Die fristgebundene Löschung führt das Verfahren `apps/engine/scripts/purge_old_data.py` aus, das
der Betrieb nächtlich über `cron` startet. Es arbeitet **in einer Transaktion** (vollständig oder
gar nicht), **wiederholbar** (ein zweiter Lauf findet keine Zeilen mehr) und löscht Dateien auf dem
Datenträger innerhalb derselben Transaktion, so dass kein Archiv zurückbleibt, das keine Zeile mehr
benennt. Ein Probelauf (`--dry-run`) berichtet, was gelöscht würde, ohne etwas zu ändern. Für einen
*legal hold* setzt `RETENTION_ENABLED=false` die Löschungen aus, ohne den Auftrag zu stoppen.

Die Frist ist eine **Untergrenze**: ein Verantwortlicher, der längeren gesetzlichen
Aufbewahrungspflichten unterliegt (etwa § 147 AO, § 10 MBO-Ä), erhöht den Wert.

### 4.3 Das Nachweisprotokoll überdauert die Löschung

`audit_events` wird **nicht** gelöscht, und dies ist beabsichtigt: Art. 5 Abs. 1 lit. e DSGVO
begründet die Pflicht zu löschen, Art. 5 Abs. 2 DSGVO die davon getrennte Pflicht, die Einhaltung
**nachweisen** zu können. Jeder gelöschte Vorgang hinterlässt einen `DATA_PURGED`-Eintrag, der den
Vorgang, den Zeitpunkt, die angewandte Frist und den Stichtag benennt. Was die Löschung überdauert,
ist damit **der Nachweis der Löschung — nicht der klinische Inhalt**. Das Protokoll ist
fortschreibungsgeschützt (*append-only*); der Datenzugriffslayer verweigert jedes UPDATE und jedes
DELETE auf dieser Tabelle.

Der Verantwortliche wird darauf hingewiesen, dass eine Einwendung gegen die Aufbewahrung dieser
Nachweiseinträge nach Art. 17 Abs. 3 lit. b und e DSGVO zu bewerten ist; die Einträge enthalten die
handelnde Person, den Zeitpunkt und den Vorgangsbezug, jedoch keine Abrechnungsinhalte.

### 4.4 Wirkung einer Löschung auf Sicherungen

**Eine Löschung, die gegen die laufende Datenbank ausgeführt wird, erreicht einen bereits
geschriebenen, verschlüsselten Datenbankabzug nicht.** Für die Sicherungen ist zum Stand dieses
Dokuments **keine Aufbewahrungsfrist eingerichtet**; der Speicherbereich ist zudem versioniert, so
dass eine Regel, die nur die jeweils aktuelle Fassung verfallen lässt, die vorherigen Fassungen
nicht löscht. Die Aufbewahrungsdauer der Sicherungen ist damit die tatsächliche Obergrenze dafür,
wie lange Daten eine Löschungsaufforderung überdauern. Einrichtung einer Lebenszyklusregel
einschließlich der Behandlung früherer Fassungen: **in Umsetzung, Zieltermin 07.09.2027**.

### 4.5 Rückgabe und Löschung nach Vertragsende

Nach Beendigung des Vertrags werden auf Weisung des Verantwortlichen sämtliche Prüfergebnisse
gelöscht oder in maschinenlesbarer Form (JSON, CSV) herausgegeben. Ursprungsdateien sind zu diesem
Zeitpunkt bereits gelöscht. Verbrauchsdaten werden für die Dauer handels- und steuerrechtlicher
Aufbewahrungsfristen aufbewahrt, soweit sie Grundlage einer Rechnungsstellung waren; sie enthalten
keine personenbezogenen Daten der betroffenen Personen im Sinne des § 3.3 erster und zweiter
Spiegelstrich.

**Eine Löschung auf Weisung ist derzeit ein manueller Vorgang**; eine Selbstbedienungsfunktion
besteht nicht — **in Umsetzung, Zieltermin 07.09.2027**. Zu vereinbaren sind Ausführungsfrist und
Nachweis der Ausführung.

---

## 5. Ort der Verarbeitung und Unterauftragsverarbeiter (Art. 28 Abs. 2 und 4 DSGVO)

### 5.1 Ort der Verarbeitung

| Verarbeitungsschritt | Ort |
| --- | --- |
| Betrieb der Anwendung (Prüfung, PDF-Erzeugung, Weboberfläche, TLS-Terminierung) | AWS, Region `eu-central-1` (Frankfurt am Main) |
| Datenbank (PostgreSQL, verwaltet über Neon) | AWS, Region `aws-eu-central-1` (Frankfurt am Main) |
| Verschlüsselte Datenbanksicherungen | Amazon S3, Region `eu-central-1` (Frankfurt am Main) |

Die Region wird technisch erzwungen: das Bereitstellungsskript verweigert den Lauf für eine Region
außerhalb der Europäischen Union und legt den Speicherbereich mit ausdrücklicher Regionsbindung an.
**Daten im Ruhezustand und die Verarbeitung selbst finden in Frankfurt am Main statt.**

### 5.2 Verzeichnis der Unterauftragsverarbeiter

| Unterauftragsverarbeiter | Leistung | Ort / Region | Zugängliche Datenkategorien |
| --- | --- | --- | --- |
| **Amazon Web Services EMEA SARL**, Luxemburg (oberste Muttergesellschaft: Amazon.com, Inc., USA) | (1) virtuelle Maschine (EC2), auf der die Anwendung läuft; (2) Objektspeicher (S3) für die verschlüsselten Sicherungen; (3) Infrastruktur, auf der Neon betrieben wird — insoweit als Unterauftragsverarbeiter von Neon | `eu-central-1` (Frankfurt am Main) | Auf Infrastrukturebene alles, was die Anwendung verarbeitet. Die Sicherungen sind clientseitig verschlüsselt und für AWS **nicht lesbar** |
| **Neon, LLC** (Tochtergesellschaft der Databricks, Inc., USA) | Verwaltete PostgreSQL-Datenbank | `aws-eu-central-1` (Frankfurt am Main) | Die vollständige Datenbank: Prüfergebnisse, Freigaben, Nachweisprotokoll, Benutzerkonten und Sitzungen |
| **Vercel Inc.**, USA | Hosting der öffentlichen Marketing-Website (`azmoth.com`) | Unternehmenssitz USA | **Keine Rechnungs- und keine Patientendaten.** Zugänglich sind ausschließlich Zugriffsdaten eines Webservers zu Besuchern einer öffentlichen Informationsseite |
| **GitHub, Inc.**, USA (Microsoft Corporation) | Versionsverwaltung des Quellcodes und Registry der Container-Abbilder | USA | **Keine personenbezogenen Daten des Verantwortlichen und keine Patientendaten.** Quellcode, synthetische Testdaten und Container-Abbilder |

**Erläuterungen, ohne die die Tabelle unvollständig gelesen wird:**

- **AWS steht aus zwei verschiedenen Gründen in dieser Kette, und nur einer ist eine
  Auswahlentscheidung.** Für die Datenbank ist es keine: Neon bietet keine Azure-Region mehr an, in
  der neue Projekte angelegt werden können. Für virtuelle Maschine und Objektspeicher ist es eine.
  Die Folge ist ausdrücklich festzuhalten: **Anwendung, Datenbank und Sicherungen liegen bei einem
  einzigen Infrastrukturanbieter.** Die Trennung besteht fort auf Ebene der Konten (Neon betreibt
  die Datenbank in einem eigenen AWS-Konto, die Sicherungen liegen im Konto des Auftragnehmers),
  der Dienste und der Zugangsdaten; ein Ausfall, eine Kündigung oder eine Sperrung auf Seiten von
  AWS trifft jedoch alle drei Bestandteile zugleich.
- **Vercel erreicht keine personenbezogenen Daten aus dieser Verarbeitung.** Die Marketing-Website
  ist statisch vorgerendert, hält keine Datenbank, kennt keine Sitzung und kommuniziert nicht mit
  der Anwendung.
- **GitHub erhält keine Kundendaten.** Der Auftragnehmer hält dies fest, weil eine Quellcode- und
  Registry-Plattform in einer Unterauftragsverarbeiterliste ohne Erläuterung falsch gelesen wird:
  dort liegen Programmcode, synthetische Testdateien und die gebauten Container-Abbilder, jedoch
  keine Abrechnungs-, Patienten- oder Nutzerdaten des Verantwortlichen. Lizenzierte Fremddaten und
  Betriebsgeheimnisse sind von der Versionsverwaltung ausgeschlossen; ein automatisierter Test
  schlägt fehl, wenn dieser Ausschluss entfällt.
- **Die Tabelle ist keine abschließende Darstellung der gesamten Kette.** Die
  Unterauftragsverarbeiterliste von Neon wird von Databricks unter
  `databricks.com/legal/databricks-subprocessors` geführt und umfasst weitere, überwiegend in den
  Vereinigten Staaten ansässige Unternehmen. Der Verantwortliche ist auf diese vorgelagerte Liste
  zu verweisen; eine Momentaufnahme in dieser Anlage wäre nach kurzer Zeit überholt.

**Nicht eingesetzt werden** insbesondere: Dienste zur Textanalyse, Übersetzung oder Verarbeitung
durch Sprachmodelle; externe Analyse- oder Trackingdienste; externe Protokollierungsdienste. Eine
Anbindung zur Fehlerüberwachung ist technisch vorgesehen, aber **nicht aktiviert**; sie erhielte
ausschließlich Fehlertyp, Meldung, Route, Vorgangsnummer und Organisation — keine Rechnungsinhalte
— und wäre vor Aufnahme des Betriebs als Unterauftragsverarbeiter zu benennen und vom
Verantwortlichen zu genehmigen.

### 5.3 Drittlandbezug

Der Auftragnehmer benennt den Sachverhalt ausdrücklich, anstatt ihn zu übergehen:

- Vertragspartner für die AWS-Dienste ist im Europäischen Wirtschaftsraum die **Amazon Web Services
  EMEA SARL (Luxemburg)**; oberste Muttergesellschaft ist die **Amazon.com, Inc. (USA)**. AWS
  stellt für die Auftragsverarbeitung ein *Data Processing Addendum* bereit, das
  Standardvertragsklauseln einbezieht.
- Die Muttergesellschaft der **Neon, LLC** ist die **Databricks, Inc. (USA)**; die
  Datenschutzerklärung von Neon stützt Übermittlungen auf das *Data Privacy Framework*.
- Die **Vercel Inc.** und die **GitHub, Inc.** haben ihren Sitz in den Vereinigten Staaten; beide
  erhalten nach § 5.2 keine Daten aus dieser Verarbeitung.

Zutreffend ist daher: **Daten im Ruhezustand und die Verarbeitung finden in Frankfurt am Main
statt; ein administrativer oder unterstützender Zugriff durch die genannten US-Muttergesellschaften
und deren Unterauftragsverarbeiter ist nicht auszuschließen** und richtet sich nach dem jeweils
vereinbarten Übermittlungsmechanismus. Die Bewertung dieses Sachverhalts ist eine Rechtsfrage; sie
ist als offener Punkt in § 9 benannt.

### 5.4 Genehmigung weiterer Unterauftragsverarbeiter

Der Auftragnehmer unterrichtet den Verantwortlichen über jede beabsichtigte Änderung in Bezug auf
die Hinzuziehung oder die Ersetzung eines Unterauftragsverarbeiters mit einer Frist von **30
Tagen** vor Wirksamwerden. Der Verantwortliche kann der Änderung innerhalb dieser
Frist widersprechen. Der Auftragnehmer verpflichtet jeden Unterauftragsverarbeiter auf im
Wesentlichen gleichwertige Pflichten.

---

## 6. Technische und organisatorische Maßnahmen (Art. 32 DSGVO) — Zusammenfassung

Die vollständige Darstellung ist Gegenstand des Dokuments **`legal/TOM.md`**, das Bestandteil
dieser Anlage ist. Zusammenfassung der wesentlichen Maßnahmen:

| Bereich | Maßnahme |
| --- | --- |
| **Zugangskontrolle** | Anmeldung mit Sitzung (7 Tage Gültigkeit, `HttpOnly`, im Produktionsbetrieb `Secure`); Registrierung nur über eine ausdrückliche Freigabeliste, die im nicht gesetzten Zustand **niemanden** zulässt; API-Schlüssel ausschließlich als SHA-256-Hashwert gespeichert, laufzeitunabhängiger Vergleich, sofortiger Widerruf |
| **Serverzugang** | SSH ausschließlich mit Schlüssel, Port 22 auf **eine** IP-Adresse beschränkt und bei jedem Bereitstellungslauf bereinigt; Host-Firewall (`ufw`) mit *default deny* und den Freigaben 22/80/443; keine dauerhaften Cloud-Zugangsdaten auf dem Server (IAM-Rolle, IMDSv2) |
| **Zugriffskontrolle** | Mandantentrennung auf jeder Abfrage, Organisationsbezug aus der Datenbankzeile des Schlüssels und nicht aus der Anfrage; fremde Datensätze antworten `404`, nicht `403`; keine Patientenidentität in irgendeiner verarbeiteten Datenstruktur (durch Test erzwungen); Anwendungscontainer unter nicht privilegierter Kennung; nur die authentifizierte Prüfschnittstelle ist öffentlich erreichbar, jeder andere Pfad antwortet `404` |
| **Weitergabekontrolle** | TLS-Terminierung durch Caddy, kein unverschlüsselter Dienst, HSTS auf dem Anwendungshost; TLS zur Datenbank; Objektspeicher verweigert per Richtlinie jeden Zugriff ohne TLS und ist gegen öffentlichen Zugriff gesperrt; Sicherungen **vor** dem Verlassen des Servers mit `age` verschlüsselt, privater Schlüssel außerhalb der Betriebsumgebung; kein externer Dienst im Prüfpfad |
| **Verschlüsselung im Ruhezustand** | Verschlüsselter EBS-gp3-Datenträger; SSE-S3 (AES-256) für Sicherungen; anbieterseitige Verschlüsselung der verwalteten Datenbank. **Keine feldbezogene Verschlüsselung** |
| **Eingabekontrolle** | Fortschreibungsgeschütztes Protokoll `audit_events` mit handelnder Person und Zeitstempel, in derselben Transaktion wie die protokollierte Änderung; `receipt_hash` über den gesamten Systemstand; Vorgangsnummer je Anfrage; Protokolle ohne Rechnungsinhalte |
| **Verfügbarkeitskontrolle** | Verwaltete Datenbank mit Wiederherstellung auf einen Zeitpunkt; tägliche verschlüsselte Sicherung mit Lesbarkeitsprüfung und Rücklesen des Uploads; versionierter Speicherbereich; das Produktivsystem besitzt **kein** Löschrecht auf Sicherungen |
| **Trennungskontrolle** | Trennung nach Mandant, nach Zweck, zwischen Produktion und Entwicklung sowie zwischen Echt- und Testdaten (§ 8); Datenbank und Sicherungen in verschiedenen AWS-Konten mit verschiedenen Zugangsdaten |
| **Auftragskontrolle** | Verarbeitung ausschließlich zur Prüfung; keine Verarbeitung zu eigenen Zwecken, kein Modelltraining, keine Weitergabe; Änderungen am Code über nachvollziehbare Pull Requests mit automatisierter Prüfung |

---

## 7. Unterstützung des Verantwortlichen (Art. 28 Abs. 3 lit. e und f DSGVO)

### 7.1 Rechte betroffener Personen

Der Auftragnehmer unterstützt den Verantwortlichen mit geeigneten technischen und organisatorischen
Maßnahmen bei der Erfüllung von Anträgen betroffener Personen:

- **Auskunft (Art. 15)** — durch Auswertung der zu einer Organisation gespeicherten Prüfergebnisse
  und der zugehörigen Protokolleinträge. Der Auftragnehmer weist darauf hin, dass er
  **Patientinnen und Patienten nicht identifizieren kann**, weil er keine Identitätsangaben
  ausliest; die Zuordnung eines Antrags zu einem Vorgang obliegt dem Verantwortlichen, der die
  Rechnungsnummer oder Vorgangskennung beisteuert.
- **Berichtigung (Art. 16)** — durch erneute Prüfung einer korrigierten Lieferung. Eine Korrektur
  im Nachweisprotokoll ist ausgeschlossen; eine Berichtigung wird als neuer Eintrag geschrieben.
- **Löschung (Art. 17)** — durch Löschung der Prüfergebnisse einer Organisation; siehe § 4.3 zur
  Behandlung der Nachweiseinträge und § 4.4 zur Wirkung auf Sicherungen.
- **Einschränkung (Art. 18)** — durch `RETENTION_ENABLED=false` und Aussetzen der Verarbeitung für
  die betroffene Organisation.
- **Datenübertragbarkeit (Art. 20)** — die Prüfergebnisse sind über die Schnittstelle als JSON und
  als CSV-Archiv abrufbar.
- **Widerspruch (Art. 21)** — durch Aussetzen der Verarbeitung nach Weisung.

Anträge sind an contact@azmoth.com zu richten. Der Auftragnehmer beantwortet Anträge betroffener Personen
nicht selbst, sondern leitet sie unverzüglich an den Verantwortlichen weiter.

### 7.2 Meldung von Verletzungen des Schutzes personenbezogener Daten

Der Auftragnehmer unterrichtet den Verantwortlichen **unverzüglich nach Kenntniserlangung** von
einer Verletzung des Schutzes personenbezogener Daten (Art. 33 Abs. 2 DSGVO), damit dieser die Frist
des Art. 33 Abs. 1 DSGVO einhalten kann. Die Unterrichtung enthält, soweit bekannt: Art der
Verletzung, betroffene Kategorien und ungefähre Zahl der betroffenen Personen und Datensätze,
wahrscheinliche Folgen und ergriffene oder vorgeschlagene Maßnahmen. Meldeweg und Erreichbarkeit
sind in `legal/TOM.md` § 5 geregelt; Kontakt: contact@azmoth.com, +216 50 745 682.

### 7.3 Datenschutz-Folgenabschätzung

Der Auftragnehmer unterstützt den Verantwortlichen bei einer Datenschutz-Folgenabschätzung
(Art. 35 DSGVO) und einer vorherigen Konsultation (Art. 36 DSGVO) durch Bereitstellung der
technischen Angaben aus dieser Anlage und aus `legal/TOM.md`. **Eine eigene
Datenschutz-Folgenabschätzung des Auftragnehmers ist nicht abgeschlossen** — **in Umsetzung,
Zieltermin 30.06.2027**.

---

## 8. Weisungsbindung und der derzeitige Ausschluss von Echtdaten

### 8.1 Weisungsbindung

Der Auftragnehmer verarbeitet personenbezogene Daten ausschließlich auf dokumentierte Weisung des
Verantwortlichen (Art. 28 Abs. 3 lit. a DSGVO). Weisungen erfolgen in Textform an contact@azmoth.com. Ist der
Auftragnehmer der Auffassung, dass eine Weisung gegen datenschutzrechtliche Vorschriften verstößt,
teilt er dies dem Verantwortlichen unverzüglich mit.

### 8.2 Vertraulichkeit

Der Auftragnehmer verpflichtet die zur Verarbeitung befugten Personen zur Vertraulichkeit
(Art. 28 Abs. 3 lit. b DSGVO). Im Hinblick auf § 203 Abs. 4 StGB ist diese Verpflichtung
**schriftlich, personenbezogen und nachweisbar** zu erteilen. **Solche Verpflichtungen sind zum
Stand dieses Dokuments noch nicht erteilt** — **in Umsetzung, Zieltermin 30.06.2027**.

### 8.3 Echtdaten sind technisch gesperrt

Eine Lieferung mit `auftrag/@echtdaten="1"` wird mit `422 REAL_DATA_REFUSED` abgewiesen und weder
geprüft noch gespeichert. Eine Lieferung, die zu diesem Kennzeichen **keine oder eine nicht
definierte Angabe** macht, wird mit `422 ECHTDATEN_UNDECLARED` ebenfalls abgewiesen; ausschließlich
die Werte `0` und `false` lassen eine Lieferung passieren. Die Einstellung
`PADNEXT_ALLOW_REAL_DATA` steht standardmäßig und in allen ausgelieferten Betriebsdateien auf
`false`.

**Diese Sperre ist keine Berechtigung, die ein Aufrufer technisch erlangen kann**, und ihre
Aufhebung begründet für sich genommen keine Rechtsgrundlage. Ihre Aufhebung setzt voraus:
den unterzeichneten Auftragsverarbeitungsvertrag, eine dokumentierte Rechtsgrundlage, die
abgeschlossene Datenschutz-Folgenabschätzung und die Bewertung nach § 203 StGB. Der Stand dieser
Punkte ist in `legal/COMPLIANCE_ROADMAP.md` festgehalten.

**Hinweis für die Praxis:** Ein als „Testdaten" vorbereiteter Export eines Praxisverwaltungssystems
kann das Kennzeichen `echtdaten="1"` aus dem Quellsystem tragen, auch wenn die Patientenfelder
entfernt wurden — das Kennzeichen beschreibt den Export, nicht den Inhalt. Wird ein anonymisierter
Export abgewiesen, ist dies der Grund, und die Korrektur erfolgt im Export.

---

## 9. Kontrollrechte des Verantwortlichen (Art. 28 Abs. 3 lit. h DSGVO)

Der Auftragnehmer stellt dem Verantwortlichen alle erforderlichen Informationen zum Nachweis der
Einhaltung der Pflichten aus Art. 28 DSGVO zur Verfügung und ermöglicht Überprüfungen —
einschließlich Inspektionen —, die vom Verantwortlichen oder einem von diesem beauftragten Prüfer
durchgeführt werden.

**Ausgestaltung:**

1. **Auskunft in Textform.** Der Auftragnehmer beantwortet Fragen zu den Maßnahmen dieser Anlage
   und stellt auf Anforderung die jeweils geltende Fassung von `legal/TOM.md` und dieser Anlage
   sowie die aktuelle Liste der Unterauftragsverarbeiter zur Verfügung. Regelfrist: **14 Tage**
   nach Zugang der Anforderung.
2. **Nachweise Dritter.** Für die Rechenzentrums- und Plattformebene verweist der Auftragnehmer auf
   die Nachweise der Unterauftragsverarbeiter. **Er macht sich diese Nachweise nicht zu eigen und
   leitet aus ihnen keine eigene Zertifizierung ab.**
3. **Prüfung vor Ort oder aus der Ferne.** Nach vorheriger Ankündigung mit angemessener Frist
   (Regelfall: **4 Wochen**), während der üblichen Geschäftszeiten, ohne
   Störung des Betriebsablaufs und beschränkt auf die für diese Verarbeitung eingesetzten Systeme.
   Ein beauftragter Prüfer darf kein Wettbewerber des Auftragnehmers sein und ist auf
   Vertraulichkeit zu verpflichten.
4. **Prüfbare Aussagen.** Jede technische Aussage in dieser Anlage und in `legal/TOM.md` benennt die
   Datei, die Einstellung oder den automatisierten Test, an dem sie überprüfbar ist. Bei
   Widersprüchen zwischen diesen Dokumenten und dem Quellstand ist der Quellstand maßgeblich, und
   der Widerspruch ist ein zu meldender Fehler.
5. **Kosten.** Die erste Prüfung je Kalenderjahr erfolgt ohne gesonderte Vergütung; für darüber
   hinausgehende Prüfungen kann der Auftragnehmer den nachgewiesenen Aufwand berechnen.

---

## 10. Offene Punkte für die anwaltliche Prüfung

Ausdrücklich benannt und nicht beschönigt. Ein Vertrag, der diese Punkte nicht adressiert, ist
unvollständig.

1. **Der Auftragsverarbeitungsvertrag selbst ist nicht abgeschlossen** — weder mit einem
   Verantwortlichen noch als gegengezeichneter Vertrag mit Neon/Databricks. Der im
   Selbstbedienungsverfahren verfügbare Text von Neon ist ein durch Anklicken angenommenes
   produktbezogenes Beiblatt und kein gegengezeichneter Vertrag.
2. **Keine abgeschlossene Datenschutz-Folgenabschätzung**, obwohl Gesundheitsdaten nach Art. 9
   DSGVO betroffen sind.
3. **Keine Bewertung nach § 203 StGB** und keine erteilten Verschwiegenheitsverpflichtungen nach
   § 203 Abs. 4 StGB. § 203 StGB ist Strafrecht: die unbefugte Offenbarung eines Patientengeheimnisses
   durch eine mitwirkende Person ist strafbewehrt, und ein IT-Dienstleister, der im Auftrag einer
   Praxis Patientendaten verarbeitet, steht in diesem Kreis.
4. **Drittlandbezug durch US-Muttergesellschaften** (§ 5.3): Bewertung der jeweiligen
   Übermittlungsmechanismen erforderlich.
5. **Keine feldbezogene Verschlüsselung.** Eine Person mit administrativem Datenbankzugang kann
   gespeicherte Prüfergebnisse einsehen. Zu regeln: Kreis der Berechtigten und Verpflichtung auf
   Vertraulichkeit.
6. **Keine Rollen innerhalb einer Praxis.** Jedes freigeschaltete Konto einer Organisation kann
   freigeben, ablehnen und exportieren.
7. **Kein durchgeführter Penetrationstest, keine Zertifizierung** nach ISO 27001 oder SOC 2.
8. **Keine nachgewiesene Testwiederherstellung** einer Sicherung.
9. **Keine Aufbewahrungsfrist für Sicherungen** (§ 4.4) — die tatsächliche Obergrenze für das
   Überdauern einer Löschung.
10. **Löschung auf Weisung ist manuell** (§ 4.5) — zu regeln sind Frist und Nachweis.
11. **Anwendung, Datenbank und Sicherungen bei einem einzigen Infrastrukturanbieter** (§ 5.2) — zu
    regeln ist, ob eine Zweitsicherung bei einem dritten Anbieter verlangt wird.
12. **Ratenbegrenzung wirkt je Prozess**; bei mehreren Instanzen vervielfacht sich die tatsächliche
    Grenze. Für Verfügbarkeitszusagen relevant.
13. **Verbrauchsdaten werden gepuffert geschrieben**; bei einem Prozessabbruch können einzelne
    Einträge verlorengehen. Für Abrechnungszwecke ist zu vereinbaren, dass im Zweifel zugunsten des
    Verantwortlichen gezählt wird.
14. **Freie Textfelder bleiben erhalten** (§ 3.2). Eine Anonymisierung im Rechtssinne findet nicht
    statt.

---

## 11. EU-Vertreter nach Art. 27 DSGVO

Der Auftragnehmer (Azmoth) hat seinen Sitz außerhalb der Europäischen Union (Tunesien). Sobald die
Verarbeitung personenbezogener Daten echter Patientinnen und Patienten beginnt, wird gemäß Art. 27
DSGVO ein Vertreter in der Union benannt.

**Aktueller Status (Pilotphase):** Es werden ausschließlich synthetische Testdaten verarbeitet; es
findet keine Verarbeitung personenbezogener Daten statt. Ein EU-Vertreter ist daher derzeit nicht
erforderlich.

**Geplante Benennung:** bis 30.06.2027 — zwingend vor Inbetriebnahme mit echten Patientendaten.

**Kontakt nach Benennung:** Name/Firma: TBD · Anschrift (EU): TBD · E-Mail: TBD · Telefon: TBD

---

*Erstellt auf Grundlage des Quellstands zum 2026-09-06. Bei jeder Änderung an Speicherung,
Protokollierung, Aufbewahrung, am Verarbeitungsort oder am Kreis der Unterauftragsverarbeiter ist
diese Anlage im selben Pull Request anzupassen. Dieses Dokument ist ein Entwurf und ersetzt keine
anwaltliche Prüfung.*
