# Datenschutzerklärung für die Webanwendung Azmoth

**Status: Entwurf — ersetzt keine anwaltliche Prüfung**

**Betriebsmodus: Pilotbetrieb ausschließlich mit synthetischen Testdaten — keine
Verarbeitung personenbezogener Daten.**

Diese Erklärung beschreibt die Verarbeitung personenbezogener Daten **der Nutzerinnen und Nutzer
der Webanwendung** (Prüfkräfte, Praxismitarbeitende, Beschäftigte einer Abrechnungsstelle) nach
Art. 13 und 14 DSGVO.

| Angabe | Wert |
| --- | --- |
| Dokument | Datenschutzerklärung der Webanwendung |
| Version | 0.2 |
| Stand | 2026-09-06 |
| Nächste Überprüfung | 07.09.2027 |
| Geltungsbereich | Die unter `app.azmoth.com` erreichbare Webanwendung |

**Version 0.1** — Ersterstellung, 2026-09-06.
**Version 0.2** — 07.09.2026 — Platzhalter ergänzt; Art.-27-Abschnitt aufgenommen.

> **Nicht Gegenstand dieser Erklärung** sind die in der Anwendung geprüften Abrechnungsdaten. Diese
> verarbeitet der Betreiber **als Auftragsverarbeiter** im Auftrag der jeweiligen Praxis oder
> Abrechnungsstelle; Verantwortlicher hierfür ist die jeweilige Praxis oder Abrechnungsstelle. Die
> Einzelheiten regeln der Auftragsverarbeitungsvertrag und dessen Anlage (`legal/AVV_Anlage.md`).

---

## 1. Verantwortlicher

**Azmoth**
Bureau 5, Centre Aziza, 1. Etage, Av. de l'Indépendance, Menzel Bourguiba 7050, Tunesien
Vertreten durch: Oussama Khadraoui
E-Mail: contact@azmoth.com
Telefon: +216 50 745 682

**Datenschutzbeauftragte(r):** Azmoth hat zum Stand dieses Dokuments keine
Datenschutzbeauftragte und keinen Datenschutzbeauftragten benannt. Ob eine Benennungspflicht nach
Art. 37 DSGVO in Verbindung mit § 38 BDSG besteht, ist Gegenstand der laufenden rechtlichen Prüfung
(`legal/COMPLIANCE_ROADMAP.md`). Anfragen zum Datenschutz richten Sie bitte an contact@azmoth.com.

---

## 2. Welche Daten wir verarbeiten, wozu und auf welcher Grundlage

### 2.1 Konto und Anmeldung

| Datum | Zweck | Rechtsgrundlage | Speicherdauer |
| --- | --- | --- | --- |
| Name, E-Mail-Adresse | Führung des Benutzerkontos, Anmeldung, Zuordnung zur Praxis oder Abrechnungsstelle | Art. 6 Abs. 1 lit. b DSGVO (Vertrag bzw. vorvertragliche Maßnahme) | Bis zur Löschung des Kontos |
| Passwort — **ausschließlich als kryptographischer Hashwert** | Anmeldung | Art. 6 Abs. 1 lit. b DSGVO | Bis zur Löschung des Kontos |
| Sitzungsdaten (Sitzungskennung, Ablaufzeitpunkt, aktive Organisation) | Aufrechterhaltung der Anmeldung | Art. 6 Abs. 1 lit. b DSGVO | Sitzungsdauer, längstens **7 Tage** |

Die Registrierung ist **nicht offen**: ein Konto kann nur anlegen, wessen E-Mail-Adresse oder
E-Mail-Domain vorab freigeschaltet wurde. Ist keine Freigabeliste hinterlegt, ist die Registrierung
im Produktionsbetrieb für **niemanden** möglich.

### 2.2 Nutzung der Anwendung

| Datum | Zweck | Rechtsgrundlage | Speicherdauer |
| --- | --- | --- | --- |
| Nachweiseinträge zu Erstellung, Einsichtnahme, Freigabe, Ablehnung, Export und Löschung eines Prüfvorgangs — jeweils mit Benutzerkennung und Zeitstempel | Nachvollziehbarkeit ärztlicher Abrechnungsfreigaben; Nachweispflicht nach Art. 5 Abs. 2 DSGVO | Art. 6 Abs. 1 lit. c und lit. f DSGVO (Nachweis- und Rechenschaftspflicht; berechtigtes Interesse an einem manipulationsgeschützten Freigabenachweis) | **Dauerhaft.** Diese Einträge werden nicht gelöscht — siehe § 6 |
| Server- und Anfrageprotokolle: Zeitpunkt, Routenmuster, Statuscode, Dauer, Vorgangsnummer, ggf. Organisationskennung | Betrieb, Fehlersuche, Abwehr missbräuchlicher Nutzung | Art. 6 Abs. 1 lit. f DSGVO | Nach der Protokollaufbewahrung der Betriebsumgebung |
| Fehlerprotokoll bei unerwarteten Fehlern: Fehlertyp, Meldung, Route, Vorgangsnummer, Organisation | Fehlersuche | Art. 6 Abs. 1 lit. f DSGVO | `DATA_RETENTION_DAYS` — 90 Tage, im Pilotbetrieb 30 Tage |

Protokolle enthalten **keine** Abrechnungsinhalte: weder Anfrage- oder Antwortkörper noch Dateinamen
hochgeladener Dateien, GOÄ-Ziffern, Beträge oder weitere Header-Werte.

### 2.3 Was wir nicht verarbeiten

- **Keine Werbung, kein Profiling, keine automatisierte Entscheidungsfindung** im Sinne des Art. 22
  DSGVO. Das Prüfergebnis ist ein Hinweis im Status *Entwurf*; die Freigabe trifft ein Mensch.
- **Keine Weitergabe zu eigenen Zwecken**, kein Verkauf von Daten, **kein Training von Modellen**.
  Im Prüfpfad wird keine externe Schnittstelle aufgerufen; ein Sprachmodell kommt nicht zum Einsatz.
- **Keine Angaben zur Person von Patientinnen und Patienten.** Die Prüfsoftware liest weder Namen
  noch Anschrift, Geburtsdatum oder Versichertennummer aus einer Abrechnungsdatei aus; die
  verarbeitenden Datenstrukturen besitzen für diese Angaben kein Feld, und ein automatisierter Test
  erzwingt dies bei jeder Änderung.

---

## 3. Cookies

Die Anwendung verwendet **ausschließlich technisch notwendige Cookies**. Es findet **keine Analyse,
keine Reichweitenmessung und kein Tracking** statt; es sind keine Analyse- oder Werbedienste
eingebunden. Ein Einwilligungsbanner entfällt daher, weil es nichts gäbe, wofür eine Einwilligung
einzuholen wäre (§ 25 Abs. 2 Nr. 2 TDDDG).

| Cookie | Zweck | Eigenschaften | Laufzeit |
| --- | --- | --- | --- |
| `better-auth.session_token` (im Produktionsbetrieb mit dem Präfix `__Secure-`) | Anmeldung: identifiziert die Sitzung | `HttpOnly`, `SameSite=Lax`, im Produktionsbetrieb `Secure` | 7 Tage |
| `onboarding_complete` | Merkt, dass die Ersteinrichtung abgeschlossen ist, damit sie nicht erneut angezeigt wird | `HttpOnly`, `SameSite=Lax`, im Produktionsbetrieb `Secure` | 7 Tage; wird bei jeder Anfrage ohne gültige Sitzung gelöscht |

Rechtsgrundlage für das Setzen dieser Cookies: § 25 Abs. 2 Nr. 2 TDDDG (unbedingt erforderlich für
den vom Nutzer ausdrücklich gewünschten Dienst) in Verbindung mit Art. 6 Abs. 1 lit. b DSGVO für
die anschließende Verarbeitung.

---

## 4. Anmeldung über Google (nur wenn im jeweiligen Betrieb aktiviert)

Die Anwendung kann eine Anmeldung über ein Google-Konto anbieten. Diese Möglichkeit ist
**standardmäßig abgeschaltet** und nur verfügbar, wenn der Betreiber sie für den jeweiligen Betrieb
ausdrücklich aktiviert hat.

Ist sie aktiviert und nutzen Sie sie, werden Sie zur Anmeldung an Google weitergeleitet; Google
erfährt dabei, dass und wann Sie sich an dieser Anwendung anmelden, und übermittelt uns Ihre
E-Mail-Adresse und Ihren Namen. Anbieter ist die Google Ireland Limited, Gordon House, Barrow
Street, Dublin 4, Irland. Rechtsgrundlage ist Art. 6 Abs. 1 lit. b DSGVO. **Über den geprüften
Abrechnungsinhalt erfährt Google nichts.** Auch bei dieser Anmeldung greift die Freigabeliste aus
§ 2.1: ein nicht freigeschaltetes Google-Konto erhält kein Konto.

Nutzen Sie die Anmeldung über Google nicht, findet keine Verarbeitung durch Google statt.

---

## 5. Empfänger und Ort der Verarbeitung

Die Verarbeitung findet auf Systemen in **Frankfurt am Main** statt. Eingesetzt werden:

| Empfänger | Leistung | Ort |
| --- | --- | --- |
| Amazon Web Services EMEA SARL, Luxemburg | Betrieb der virtuellen Maschine und Objektspeicher für verschlüsselte Sicherungen | AWS `eu-central-1`, Frankfurt am Main |
| Neon, LLC | Verwaltete PostgreSQL-Datenbank | AWS `aws-eu-central-1`, Frankfurt am Main |

Die Übertragung zwischen Ihrem Browser und der Anwendung erfolgt ausnahmslos TLS-verschlüsselt; ein
unverschlüsselter Dienst wird nicht angeboten. Datenbanksicherungen werden **vor** dem Verlassen des
Servers zusätzlich verschlüsselt; der zugehörige private Schlüssel liegt bei keinem der genannten
Empfänger.

### 5.1 Drittlandübermittlung

**Eine Übermittlung Ihrer Daten in ein Drittland ist nicht beabsichtigt, und die Verarbeitung sowie
die Speicherung im Ruhezustand finden ausschließlich in Frankfurt am Main statt.**

Der Betreiber weist gleichwohl offen darauf hin, dass die genannten Anbieter US-amerikanische
Muttergesellschaften haben (Amazon.com, Inc. für AWS; Databricks, Inc. für Neon) und ein
administrativer oder unterstützender Zugriff aus einem Drittland nicht mit letzter Sicherheit
ausgeschlossen werden kann. Für die Auftragsverarbeitung mit AWS bestehen Standardvertragsklauseln
nach dem *AWS Data Processing Addendum*; Neon stützt Übermittlungen auf das *Data Privacy
Framework*. Die abschließende rechtliche Bewertung dieses Sachverhalts ist Gegenstand der laufenden
Prüfung (`legal/COMPLIANCE_ROADMAP.md`). Der Betreiber zieht es vor, diesen Punkt zu benennen,
anstatt eine Zusage zu machen, die er nicht in vollem Umfang belegen kann.

Nutzen Sie die Anmeldung über Google (§ 4), kann eine Verarbeitung durch Google auch außerhalb der
Europäischen Union stattfinden.

---

## 6. Speicherdauer

- **Konto- und Sitzungsdaten:** bis zur Löschung des Kontos; Sitzungen längstens sieben Tage.
- **Fehlerprotokoll und Prüfergebnisse:** `DATA_RETENTION_DAYS` — 90 Tage, im Pilotbetrieb 30 Tage.
  Die Löschung führt ein nächtlich laufendes, wiederholbares Verfahren in einer Transaktion aus.
- **Nachweiseinträge (`audit_events`) werden nicht gelöscht.** Diese Einträge belegen, wer wann
  eine Abrechnungsfreigabe erteilt, abgelehnt oder exportiert hat, und sie belegen zusätzlich, dass
  und wann Daten gelöscht wurden. Art. 5 Abs. 1 lit. e DSGVO verpflichtet zur Löschung; Art. 5
  Abs. 2 DSGVO verpflichtet daneben dazu, die Löschung **nachweisen** zu können — ein Nachweis, der
  sich selbst löscht, erfüllt das nicht. Die Einträge enthalten Benutzerkennung, Zeitpunkt und
  Vorgangsbezug, **keine Abrechnungsinhalte**. Sie sind technisch nicht änderbar und nicht löschbar.
  Zur Reichweite Ihres Löschungsrechts insoweit siehe § 7.

---

## 7. Ihre Rechte

Sie haben nach der DSGVO die folgenden Rechte. Zur Ausübung genügt eine formlose Nachricht an
contact@azmoth.com; die Ausübung ist unentgeltlich.

- **Auskunft (Art. 15 DSGVO)** — Bestätigung, ob wir Sie betreffende Daten verarbeiten, und
  Auskunft über diese Daten sowie über Zwecke, Empfänger und Speicherdauer.
- **Berichtigung (Art. 16 DSGVO)** — Berichtigung unrichtiger und Vervollständigung unvollständiger
  Daten. Ein Nachweiseintrag wird nicht überschrieben; eine Berichtigung wird als neuer Eintrag
  geschrieben.
- **Löschung (Art. 17 DSGVO)** — Löschung Ihrer Daten, soweit kein Ausnahmetatbestand entgegensteht.
  **Ausdrücklicher Hinweis:** Nachweiseinträge nach § 6 bleiben bestehen, soweit sie zur Erfüllung
  einer rechtlichen Verpflichtung oder zur Geltendmachung, Ausübung oder Verteidigung von
  Rechtsansprüchen erforderlich sind (Art. 17 Abs. 3 lit. b und lit. e DSGVO). Ihr Konto und Ihre
  Kontaktdaten werden gelöscht; der Umstand, dass eine bestimmte Benutzerkennung eine Freigabe
  erteilt hat, bleibt protokolliert. Wir teilen Ihnen im Einzelfall mit, was gelöscht wurde und was
  aus welchem Grund bestehen bleibt.
- **Einschränkung der Verarbeitung (Art. 18 DSGVO)** — Sperrung der Verarbeitung statt Löschung,
  etwa während der Prüfung eines Berichtigungsverlangens.
- **Datenübertragbarkeit (Art. 20 DSGVO)** — Herausgabe der von Ihnen bereitgestellten Daten in
  einem strukturierten, gängigen und maschinenlesbaren Format (JSON oder CSV).
- **Widerspruch (Art. 21 DSGVO)** — Widerspruch gegen eine Verarbeitung, die auf Art. 6 Abs. 1
  lit. f DSGVO gestützt ist (§ 2.2), aus Gründen, die sich aus Ihrer besonderen Situation ergeben.
- **Widerruf einer Einwilligung (Art. 7 Abs. 3 DSGVO)** — soweit eine Verarbeitung auf einer
  Einwilligung beruht, mit Wirkung für die Zukunft. Zum Stand dieses Dokuments stützt sich keine
  Verarbeitung in dieser Anwendung auf eine Einwilligung.

**Sie erreichen uns unter contact@azmoth.com und +216 50 745 682.** Wir beantworten Anträge unverzüglich,
spätestens innerhalb eines Monats nach Eingang (Art. 12 Abs. 3 DSGVO).

---

## 8. Beschwerderecht bei einer Aufsichtsbehörde

Unbeschadet anderer Rechtsbehelfe haben Sie das Recht, sich bei einer Aufsichtsbehörde zu
beschweren (Art. 77 DSGVO) — insbesondere in dem Mitgliedstaat Ihres Aufenthaltsorts, Ihres
Arbeitsplatzes oder des Orts des mutmaßlichen Verstoßes.

Azmoth hat seinen Sitz außerhalb der Europäischen Union (Tunesien); eine für den Sitz des
Verantwortlichen zuständige Landesdatenschutzbehörde gibt es daher nicht. Maßgeblich ist stattdessen
die Aufsichtsbehörde am Sitz des nach Art. 27 DSGVO zu benennenden EU-Vertreters (§ 12):

> *(wird mit Benennung des EU-Vertreters ergänzt)*

---

## 9. Pflicht zur Bereitstellung, Erforderlichkeit

Die Angabe von Name und E-Mail-Adresse ist zur Nutzung der Anwendung erforderlich; ohne sie kann
kein Konto geführt und keine Freigabe einer Person zugeordnet werden. Eine gesetzliche oder
vertragliche Pflicht zur Bereitstellung darüber hinausgehender Daten besteht nicht.

---

## 10. Sicherheit der Verarbeitung

Die technischen und organisatorischen Maßnahmen sind vollständig in `legal/TOM.md` beschrieben. Im
Überblick: TLS ohne Ausnahme, verschlüsselte Datenträger, ausschließlich als Hashwert gespeicherte
Passwörter und Schlüssel, geschlossene Registrierung, Trennung der Mandanten bei jeder Abfrage, ein
fortschreibungsgeschütztes Nachweisprotokoll und eine automatisierte Löschroutine.

Der Betreiber benennt ebenso offen, was **nicht** besteht: keine Zertifizierung nach ISO 27001 oder
SOC 2, kein durchgeführter Penetrationstest, keine feldbezogene Verschlüsselung einzelner
Datenbankspalten, keine Mehr-Faktor-Authentifizierung und keine Rollentrennung innerhalb einer
Praxis. Der Stand der jeweiligen Umsetzung ist in `legal/COMPLIANCE_ROADMAP.md` mit Zieltermin
festgehalten.

---

## 11. Änderungen dieser Erklärung

Diese Erklärung wird angepasst, sobald sich die beschriebene Verarbeitung ändert — insbesondere bei
einer Änderung der eingesetzten Dienste, der Speicherorte oder der Speicherdauer. Maßgeblich ist die
jeweils unter dieser Adresse veröffentlichte Fassung; der Stand ist im Kopf dieses Dokuments
angegeben.

---

## 12. EU-Vertreter nach Art. 27 DSGVO

Azmoth hat seinen Sitz außerhalb der Europäischen Union (Tunesien). Sobald die Verarbeitung
personenbezogener Daten echter Patientinnen und Patienten beginnt, wird gemäß Art. 27 DSGVO ein
Vertreter in der Union benannt.

**Aktueller Status (Pilotphase):** Es werden ausschließlich synthetische Testdaten verarbeitet; es
findet keine Verarbeitung personenbezogener Daten statt. Ein EU-Vertreter ist daher derzeit nicht
erforderlich.

**Geplante Benennung:** bis 30.06.2027 — zwingend vor Inbetriebnahme mit echten Patientendaten.

**Kontakt nach Benennung:** Name/Firma: TBD · Anschrift (EU): TBD · E-Mail: TBD · Telefon: TBD

---

*Stand: 2026-09-06, Version 0.2. Dieses Dokument ist ein Entwurf und ersetzt keine anwaltliche
Prüfung.*
