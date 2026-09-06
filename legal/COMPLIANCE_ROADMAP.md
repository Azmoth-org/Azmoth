# Compliance-Fahrplan Azmoth

**Status: Entwurf — ersetzt keine anwaltliche Prüfung**

**Betriebsmodus: Pilotbetrieb ausschließlich mit synthetischen Testdaten — keine
Verarbeitung personenbezogener Daten.**

| Angabe | Wert |
| --- | --- |
| Dokument | Compliance-Fahrplan (verbindliche Zusagenliste, intern und vorzeigbar) |
| Betreiber | Azmoth, Bureau 5, Centre Aziza, 1. Etage, Av. de l'Indépendance, Menzel Bourguiba 7050, Tunesien |
| Verantwortlich gesamt | Oussama Khadraoui |
| Kontakt | contact@azmoth.com, +216 50 745 682 |
| Version | 0.2 |
| Stand | 2026-09-06 |
| Nächste Fortschreibung | 07.12.2026 |

**Version 0.1** — Ersterstellung, 2026-09-06.
**Version 0.2** — 07.09.2026 — Platzhalter ergänzt.

---

## Aktueller Stand, unbeschönigt

**Azmoth befindet sich im Pilotbetrieb und verarbeitet ausschließlich synthetische Testdaten.**
Es liegen keine echten Patientendaten im System, und sie können auch nicht hineingelangen, ohne dass
eine Einstellung ausdrücklich umgestellt wird: eine PADnext-Lieferung, die sich als Echtdaten
ausweist, wird abgewiesen — und ebenso eine Lieferung, die dazu keine oder eine nicht definierte
Angabe macht. Die Sperre ist die Voreinstellung und steht in allen ausgelieferten Betriebsdateien.

Umgesetzt sind: der Betrieb ausschließlich in Frankfurt am Main (technisch erzwungen), TLS ohne
Ausnahme, verschlüsselte Datenträger, tägliche clientseitig verschlüsselte Sicherungen in einem
versionierten Speicherbereich, den das Produktivsystem nicht löschen kann, eine geschlossene
Registrierung, ausschließlich als Hashwert gespeicherte API-Schlüssel, Mandantentrennung bei jeder
Abfrage, ein fortschreibungsgeschütztes Nachweisprotokoll und eine automatisierte, transaktionale
Löschroutine mit konfigurierbarer Frist.

**Nicht abgeschlossen sind die Punkte, die vor der ersten Verarbeitung echter Patientendaten
zwingend abzuschließen sind:** der Auftragsverarbeitungsvertrag, die Datenschutz-Folgenabschätzung
und die Bewertung nach § 203 StGB. Ebenso wenig durchgeführt sind ein Penetrationstest und die
Rollentrennung innerhalb einer Praxis. Der Betreiber führt keine Zertifizierung (ISO 27001, SOC 2
oder vergleichbar) und behauptet keine.

Dieser Fahrplan benennt für jeden dieser Punkte eine verantwortliche Person und einen Zieltermin.
Er ist ausdrücklich dafür bestimmt, Pilotpartnern gezeigt zu werden.

---

## Zusagen

### 1. Auftragsverarbeitungsvertrag (Art. 28 DSGVO) fertigstellen

| | |
| --- | --- |
| **Verantwortlich** | Oussama Khadraoui, anwaltliche Begleitung durch TBD — Beauftragung vor Produktionsstart |
| **Zieltermin** | 30.06.2027 |
| **Stand** | Entwurf der Anlage liegt vor (`legal/AVV_Anlage.md`, `legal/TOM.md`); kein unterzeichneter Vertrag |

Umfang:

- anwaltliche Prüfung und Fertigstellung von Vertrag und Anlage;
- **gegengezeichneter** Auftragsverarbeitungsvertrag mit Neon/Databricks — der im
  Selbstbedienungsverfahren verfügbare Text ist ein durch Anklicken angenommenes produktbezogenes
  Beiblatt und genügt nicht;
- Bestätigung des *AWS Data Processing Addendum* einschließlich der Standardvertragsklauseln;
- Verzeichnis der Unterauftragsverarbeiter mit Änderungs- und Widerspruchsverfahren;
- Verzeichnis von Verarbeitungstätigkeiten nach Art. 30 DSGVO für die eigene Verarbeitung.

**Sperrwirkung:** Ohne Abschluss dieses Punkts wird kein Echtdatenbetrieb aufgenommen.

### 2. Datenschutz-Folgenabschätzung (Art. 35 DSGVO) beginnen und abschließen

| | |
| --- | --- |
| **Verantwortlich** | Oussama Khadraoui |
| **Zieltermin Beginn** | 31.03.2027 |
| **Zieltermin Abschluss** | 30.06.2027 |
| **Stand** | Nicht begonnen |

Umfang: systematische Beschreibung der Verarbeitung, Bewertung von Notwendigkeit und
Verhältnismäßigkeit, Risikobewertung für die betroffenen Personen und Festlegung von
Abhilfemaßnahmen. Eine Folgenabschätzung ist bei Gesundheitsdaten nach Art. 9 DSGVO nicht optional.
Ausdrücklich einzubeziehen sind: die erhaltenen freien Textfelder (`begruendung`, `text`), die
dauerhafte Aufbewahrung der Nachweiseinträge, die Aufbewahrung der verschlüsselten Sicherungen und
der Drittlandbezug über die US-Muttergesellschaften der Anbieter. Zu prüfen ist ferner die
Notwendigkeit einer vorherigen Konsultation der Aufsichtsbehörde nach Art. 36 DSGVO.

**Sperrwirkung:** Ohne Abschluss dieses Punkts wird kein Echtdatenbetrieb aufgenommen.

### 3. Bewertung nach § 203 StGB

| | |
| --- | --- |
| **Verantwortlich** | Oussama Khadraoui, anwaltliche Bewertung durch TBD — Beauftragung vor Produktionsstart |
| **Zieltermin** | 30.06.2027 |
| **Stand** | Nicht begonnen |

§ 203 StGB ist Strafrecht und nicht nur Datenschutzrecht: § 203 Abs. 4 StGB erstreckt die Haftung
auf mitwirkende Personen, und ein IT-Dienstleister, der im Auftrag einer Praxis Patientendaten
verarbeitet, steht in diesem Kreis. Umfang:

- Bestimmung der Rolle des Betreibers als *sonstige mitwirkende Person* im Sinne des § 203 Abs. 3
  Satz 2 StGB;
- **schriftliche, personenbezogene und nachweisbare Verpflichtung zur Geheimhaltung** jeder Person,
  die für den Betreiber tätig ist (§ 203 Abs. 4 Satz 1 Nr. 1 StGB) — einschließlich der Frage, wie
  dies bei Unterauftragsverarbeitern abgebildet wird;
- Dokumentation, dass gegenüber dem Betreiber nur das Erforderliche offenbart wird;
- Abgleich mit der einschlägigen Berufsordnung (§ 10 MBO-Ä) und dem jeweiligen Landesrecht.

**Sperrwirkung:** Ohne Abschluss dieses Punkts wird kein Echtdatenbetrieb aufgenommen.

### 4. Penetrationstest durch einen unabhängigen Dritten

| | |
| --- | --- |
| **Verantwortlich** | Oussama Khadraoui, Durchführung durch TBD — Beauftragung vor Produktionsstart |
| **Zieltermin Beauftragung** | 31.10.2026 |
| **Zieltermin Bericht** | 31.12.2026 |
| **Zieltermin Behebung der Befunde mit hoher Kritikalität** | 31.01.2027 |
| **Stand** | Nicht durchgeführt |

Umfang: Weboberfläche einschließlich Anmeldung und Sitzungsverwaltung, Partner-Schnittstelle
einschließlich Schlüsselprüfung und Mandantentrennung, der umgekehrte Proxy und die Konfiguration
der virtuellen Maschine. Ausdrücklich zu prüfen sind die Mandantentrennung (der Versuch, Daten einer
fremden Organisation zu lesen), die Verarbeitung hochgeladener Archive und die Endpunkte, die nicht
öffentlich erreichbar sein sollen. Ergebnis und Behebungsstand werden Pilotpartnern auf Anfrage
mitgeteilt.

### 5. Rollen- und Rechtekonzept (RBAC) fertigstellen

| | |
| --- | --- |
| **Verantwortlich** | Oussama Khadraoui |
| **Zieltermin** | 07.09.2027 |
| **Stand** | Mandantentrennung umgesetzt; Rollen innerhalb einer Organisation **nicht** umgesetzt |

Umgesetzt ist die Trennung **zwischen** Praxen: jede Abfrage ist auf die Organisation gefiltert, und
ein fremder Datensatz antwortet `404`. Nicht umgesetzt ist die Trennung **innerhalb** einer Praxis:
jedes freigeschaltete Konto kann prüfen, freigeben, ablehnen und exportieren. Umfang:

- mindestens die Rollen *Prüfkraft* (prüfen, vorschlagen) und *Freigabeberechtigte(r)*
  (freigeben, ablehnen, exportieren) sowie *Administration* (Konten und Schlüssel verwalten);
- Durchsetzung der Rollen serverseitig, nicht in der Oberfläche;
- Zusammenführung von `approved_by` mit der angemeldeten Identität — derzeit werden die
  freigebende Person und das angemeldete Konto getrennt erfasst und müssen nicht übereinstimmen;
- Ablösung der vom Web-Tier gesetzten Identitäts-Header durch ein von der Prüf-Engine selbst
  verifiziertes Token für **alle** Endpunkte.

### 6. Ergänzende technische Zusagen

Ohne Sperrwirkung für den Echtdatenbetrieb, aber Bestandteil dieses Fahrplans:

| Nr. | Zusage | Verantwortlich | Zieltermin |
| --- | --- | --- | --- |
| 6.1 | **Aufbewahrungsregel für die verschlüsselten Sicherungen** einrichten, einschließlich der Behandlung früherer Objektfassungen — bis dahin ist die Aufbewahrung der Sicherungen die tatsächliche Obergrenze dafür, wie lange Daten eine Löschung überdauern | Oussama Khadraoui | 07.09.2027 |
| 6.2 | **Testwiederherstellung** einer Sicherung dokumentiert durchführen, Wiederherstellungszeit messen, danach halbjährlich wiederholen | Oussama Khadraoui | 07.09.2027 |
| 6.3 | **`REVOKE UPDATE, DELETE ON audit_events`** für die Anwendungsrolle in der Datenbank einrichten (zweite Hälfte des Schreibschutzes, die derzeit nur auf Anwendungsebene besteht) | Oussama Khadraoui | 07.09.2027 |
| 6.4 | **Selbstbedienungsfunktion für die Löschung auf Weisung**; bis dahin manuelle Ausführung mit Nachweis | Oussama Khadraoui | 07.09.2027 |
| 6.5 | **Mehr-Faktor-Authentifizierung** für die Weboberfläche | Oussama Khadraoui | 07.09.2027 |
| 6.6 | **Manipulationssicherheit des Nachweisprotokolls im vollen Sinne** (Hash-Kette oder externer Zeuge), so dass auch eine Person mit Eigentümerrechten an der Datenbank das Protokoll nicht unbemerkt umschreiben kann | Oussama Khadraoui | 07.09.2027 |
| 6.7 | **Verfahren zur Behandlung von Sicherheitsvorfällen** verschriftlichen, Erreichbarkeit festlegen und einmal proben (Art. 33 DSGVO, 72-Stunden-Frist des Verantwortlichen) | Oussama Khadraoui | 07.09.2027 |
| 6.8 | **Entscheidung über eine Zweitsicherung bei einem dritten Anbieter** — derzeit liegen Anwendung, Datenbank und Sicherungen bei einem einzigen Infrastrukturanbieter | Oussama Khadraoui | 07.09.2027 |
| 6.9 | **Prüfung der Benennungspflicht** einer/eines Datenschutzbeauftragten (Art. 37 DSGVO, § 38 BDSG) und gegebenenfalls Benennung | Oussama Khadraoui | 07.09.2027 |
| 6.10 | **Import einer echten historischen GOÄ-Fassung** mit Herkunftsnachweis; bis dahin wird jede Prüfung gegen die aktuelle Fassung gerechnet, und eine Lieferung mit älterem Leistungsdatum wird im Bericht ausdrücklich als solche gekennzeichnet | Oussama Khadraoui | 07.09.2027 |

---

## Was ausdrücklich nicht behauptet wird

Damit dieser Fahrplan als Zusagenliste taugt, benennt er, was zum Stand 2026-09-06 **nicht** besteht:

- keine Zertifizierung nach ISO 27001, ISO 27701, SOC 2, TISAX oder einem anderen Standard;
- kein durchgeführter Penetrationstest und keine externe Sicherheitsüberprüfung;
- keine abgeschlossene Datenschutz-Folgenabschätzung;
- kein unterzeichneter Auftragsverarbeitungsvertrag — weder mit einer Praxis noch mit sämtlichen
  Unterauftragsverarbeitern;
- keine abgeschlossene Bewertung nach § 203 StGB und keine erteilten
  Verschwiegenheitsverpflichtungen nach § 203 Abs. 4 StGB;
- keine feld- oder spaltenbezogene Verschlüsselung in der Datenbank;
- keine Rollentrennung innerhalb einer Praxis und keine Mehr-Faktor-Authentifizierung;
- keine nachgewiesene Testwiederherstellung und keine zugesagte Verfügbarkeit;
- keine Anonymisierung im Rechtssinne — freie Textfelder werden fachlich benötigt und bleiben
  erhalten.

---

## Fortschreibung

Dieser Fahrplan wird **vierteljährlich** fortgeschrieben und zusätzlich immer dann, wenn eine der
Zusagen erfüllt wird oder ein Zieltermin nicht gehalten werden kann. Ein verstrichener Termin wird
nicht stillschweigend verschoben, sondern mit dem neuen Termin und dem Grund vermerkt.

Nächste Fortschreibung: **07.12.2026**. Verantwortlich: Oussama Khadraoui, contact@azmoth.com, +216 50 745 682.

---

*Stand: 2026-09-06, Version 0.2. Grundlage ist der Quellstand des Repositorys zum selben Datum.
Dieses Dokument ist ein Entwurf und ersetzt keine anwaltliche Prüfung.*
