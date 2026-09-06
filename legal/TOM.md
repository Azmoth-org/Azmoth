# Technische und organisatorische Maßnahmen (TOM)

**Status: Entwurf — ersetzt keine anwaltliche Prüfung**

**Betriebsmodus: Pilotbetrieb ausschließlich mit synthetischen Testdaten — keine
Verarbeitung personenbezogener Daten.**

Maßnahmen nach Art. 32 DSGVO für den Betrieb der Anwendung **Azmoth** — Prüfung privatärztlicher
Abrechnungslieferungen im Format PADnext (ADL 2.12) gegen die Gebührenordnung für Ärzte (GOÄ).

| Angabe | Wert |
| --- | --- |
| Dokument | Technische und organisatorische Maßnahmen (Art. 32 DSGVO) |
| Verantwortlicher / Auftragnehmer | Azmoth, Bureau 5, Centre Aziza, 1. Etage, Av. de l'Indépendance, Menzel Bourguiba 7050, Tunesien |
| Vertretungsberechtigt | Oussama Khadraoui |
| Kontakt | contact@azmoth.com, +216 50 745 682 |
| Version | 0.2 |
| Stand | 2026-09-06 |
| Nächste Überprüfung | 07.09.2027 |
| Grundlage | Quellstand des Repositorys zum 2026-09-06 |

**Version 0.1** — Ersterstellung, 2026-09-06.
**Version 0.2** — 07.09.2026 — Platzhalter ergänzt.

---

## 0. Vorbemerkung: Geltungsbereich und Betriebsmodus

Dieses Dokument beschreibt den **tatsächlich umgesetzten** technischen und organisatorischen Stand.
Maßnahmen, die geplant, aber nicht umgesetzt sind, sind als solche gekennzeichnet
(„in Umsetzung, Zieltermin TT.MM.JJJJ"). Aussagen, die der Auftragnehmer nicht belegen kann, sind
nicht enthalten.

**Betriebsmodus zum Stand dieses Dokuments: Pilotbetrieb ausschließlich mit synthetischen
Testdaten.** Die Verarbeitung von Echtdaten ist technisch gesperrt: eine PADnext-Lieferung, deren
Auftragsdatei `auftrag/@echtdaten="1"` trägt, wird mit `422 REAL_DATA_REFUSED` abgewiesen und weder
geprüft noch gespeichert; eine Lieferung, die zu diesem Kennzeichen **keine oder eine nicht
definierte Angabe** macht (etwa `echtdaten="ja"`), wird mit `422 ECHTDATEN_UNDECLARED` ebenfalls
abgewiesen. Beide Sperren sind über die Einstellung `PADNEXT_ALLOW_REAL_DATA` aufhebbar, die
standardmäßig und in allen ausgelieferten Betriebsdateien auf `false` steht. Die Aufhebung ist eine
ausdrückliche, dokumentierte Entscheidung des Auftragnehmers und **begründet für sich genommen keine
Rechtsgrundlage**.

Vor der ersten Verarbeitung von Echtdaten sind der Auftragsverarbeitungsvertrag, die
Datenschutz-Folgenabschätzung und die Bewertung nach § 203 StGB abzuschließen; der Stand dieser
Punkte ist in `legal/COMPLIANCE_ROADMAP.md` festgehalten.

Der Auftragnehmer verfügt über **keine Zertifizierung** nach ISO 27001, ISO 27701, SOC 2 oder einem
anderen Standard und behauptet keine.

---

## 1. Vertraulichkeit

### 1.1 Zutrittskontrolle (physischer Zugang zu Verarbeitungsanlagen)

Der Auftragnehmer betreibt **kein eigenes Rechenzentrum**. Sämtliche Verarbeitung findet auf
Systemen von Unterauftragsverarbeitern statt; die physische Zutrittskontrolle obliegt diesen.

| Anlage | Ort | Zutrittskontrolle durch |
| --- | --- | --- |
| Virtuelle Maschine (Anwendung, Prüf-Engine, TLS-Terminierung) | AWS `eu-central-1`, Frankfurt am Main | Amazon Web Services EMEA SARL |
| Datenbank (PostgreSQL, verwaltet) | Neon auf AWS `aws-eu-central-1`, Frankfurt am Main | Neon, LLC / Amazon Web Services |
| Verschlüsselte Datenbanksicherungen | Amazon S3, `eu-central-1`, Frankfurt am Main | Amazon Web Services EMEA SARL |

Die Region wird **technisch erzwungen und nicht nur dokumentiert**: das Bereitstellungsskript
`infra/aws/provision.sh` bricht mit einer Fehlermeldung ab, wenn eine Region außerhalb der
Europäischen Union angegeben wird, und legt den Objektspeicher mit ausdrücklicher
`LocationConstraint` an, damit ein Speicherbereich nicht unbeabsichtigt in einer US-Region entsteht.

Die Nachweise zur Zutrittskontrolle der Rechenzentren sind bei den genannten Anbietern abzurufen.
**Der Auftragnehmer macht sich diese Nachweise nicht zu eigen und leitet aus ihnen keine eigene
Zertifizierung ab.**

Arbeitsplätze des Auftragnehmers befinden sich in Bureau 5, Centre Aziza, 1. Etage, Av. de l'Indépendance, Menzel Bourguiba 7050, Tunesien. Ein Zugriff auf Produktionssysteme von
diesen Arbeitsplätzen aus erfolgt ausschließlich über SSH mit einem Schlüsselpaar (siehe § 1.2).

*Offen:* Eine schriftliche Richtlinie zur physischen Sicherung der Arbeitsplätze
(Bildschirmsperre, Verschlüsselung der Endgeräte, Aufbewahrung von Datenträgern) liegt noch nicht
vor — **in Umsetzung, Zieltermin 07.09.2027**.

### 1.2 Zugangskontrolle (Verhinderung unbefugter Systemnutzung)

**Weboberfläche.** Die Anwendung erfordert eine Anmeldung. Verwendet wird Better Auth mit
Sitzungen, die gegen die Datenbank geprüft werden; die Sitzung läuft nach sieben Tagen ab und wird
bei Aktivität frühestens alle 24 Stunden verlängert. Das Sitzungscookie ist `HttpOnly` und wird im
Produktionsbetrieb (`NODE_ENV=production`) mit dem Attribut `Secure` gesetzt.

**Registrierung ist standardmäßig geschlossen.** `apps/web/lib/auth-allowlist.ts` prüft jede
Kontoerstellung gegen eine im Betrieb hinterlegte Freigabeliste (`SIGNUP_ALLOWLIST`) aus exakten
Adressen und Domains. Eine **nicht gesetzte oder leere** Liste bedeutet im Produktionsbetrieb, dass
**niemand** ein Konto anlegen kann — die Voreinstellung ist die geschlossene Tür, nicht die offene.
Die Prüfung greift an der Kontoerstellung und erfasst damit sowohl die Registrierung mit Passwort
als auch eine etwaige Anmeldung über Google. Die Ablehnung nennt gegenüber dem Aufrufer nicht, ob
die Liste fehlt oder die Adresse nicht enthalten ist; die Unterscheidung steht nur im Serverprotokoll.

**Programmierschnittstelle.** Die Partner-Schnittstelle authentifiziert über einen API-Schlüssel im
Header `X-API-Key`. Der Schlüssel wird **nicht im Klartext gespeichert**: abgelegt werden ein
SHA-256-Hashwert und ein öffentliches, nicht zur Authentifizierung geeignetes Präfix. Der Schlüssel
selbst existiert genau einmal — in der Antwort, die ihn erzeugt hat — und ist danach auch für den
Auftragnehmer nicht wiederherstellbar. Ein Datenbankabzug enthält folglich keine verwendbaren
Zugangsdaten. Der Vergleich erfolgt laufzeitunabhängig (`hmac.compare_digest`). Ein Widerruf wirkt
ab der nächsten Anfrage; die Zeile bleibt zu Nachweiszwecken erhalten.

**Zugang zum Server.** Der Zugang erfolgt ausschließlich über SSH mit einem öffentlichen Schlüssel;
eine Passwortanmeldung ist nicht vorgesehen. Der Zugang zum Port 22 ist auf **eine einzige
IP-Adresse** beschränkt — die des Auftragnehmers. Das Bereitstellungsskript ermittelt diese Adresse
bei jedem Lauf, trägt sie ein und **entfernt jede andere Freigabe auf Port 22**; es verweigert
zudem den Lauf, wenn die Adresse nicht ermittelt werden kann, anstatt auf `0.0.0.0/0` auszuweichen.

**Netzwerkseitige Begrenzung.** Die Sicherheitsgruppe der virtuellen Maschine gibt genau drei Ports
frei: 22 (IP-beschränkt), 80 und 443. Port 80 dient ausschließlich der Zertifikatsausstellung
(ACME HTTP-01) und der Weiterleitung auf 443. Zusätzlich wird auf dem Host `ufw` mit der
Voreinstellung *deny incoming* und denselben drei Freigaben aktiviert (`scripts/deploy.sh`).

**Keine dauerhaften Cloud-Zugangsdaten auf dem Server.** Die virtuelle Maschine erhält ihre
Berechtigung für den Objektspeicher über eine IAM-Rolle und ein Instanzprofil; es liegt **kein
AWS-Schlüsselpaar auf dem Datenträger**. Der Metadatendienst ist auf IMDSv2 gestellt
(`HttpTokens=required`) mit `HttpPutResponseHopLimit=1`, so dass ein Container die Anmeldedaten
nicht abrufen kann.

*Offen:* Eine Mehr-Faktor-Authentifizierung für die Weboberfläche ist **nicht umgesetzt** —
**in Umsetzung, Zieltermin 07.09.2027**.

### 1.3 Zugriffskontrolle (Beschränkung auf das Erforderliche)

**Mandantentrennung wird bei jeder Abfrage erzwungen.** Jeder API-Schlüssel ist genau einer
Organisation zugeordnet; die Organisation wird **aus der Datenbankzeile des Schlüssels** entnommen
und nicht aus der Anfrage. Es existiert kein Parameter, mit dem ein Aufrufer eine fremde
Organisation benennen könnte. Lese- und Schreiboperationen auf Prüfergebnissen, Aufträgen und
Verbrauchsdaten sind auf die Organisation gefiltert (`proposals.organization_id`,
`batch_jobs.organization_id`). Ein Datensatz einer fremden Organisation wird mit `404` beantwortet,
nicht mit `403`, damit über die Antwort nicht auf dessen Existenz geschlossen werden kann.

**Datenminimierung im Prüfvorgang.** Die Prüfsoftware liest **keine Angaben zur Person der
Patientin oder des Patienten**. Die verarbeiteten Datenstrukturen besitzen kein Feld, das einen
Namen, eine Anschrift, ein Geburtsdatum oder eine Versichertennummer aufnehmen könnte; ein
automatisierter Test (`test_no_parsed_model_can_hold_patient_identity` in
`apps/engine/tests/test_padnext.py`) prüft dies bei jedem Lauf und schlägt fehl, sobald ein solches
Feld entstünde. Die Maßnahme ist damit **nicht eine Zusage, sondern eine geprüfte Eigenschaft**.
Solche Angaben können in einer hochgeladenen Datei gleichwohl enthalten sein; die Datei ist,
solange sie auf dem Datenträger liegt, in vollem Umfang als personenbezogenes Datum zu behandeln.

**Trennung von Anwendung und Betriebssystem.** Der Anwendungscontainer läuft unter einer nicht
privilegierten Kennung (UID 10001); das Anwendungsverzeichnis ist für diese Kennung nicht
beschreibbar. Schreibzugriff besteht ausschließlich auf ein eigens eingebundenes Verzeichnis für
Uploads.

**Nicht veröffentlichte Endpunkte.** Der umgekehrte Proxy (Caddy) veröffentlicht auf dem
API-Hostnamen ausschließlich die mit API-Schlüssel authentifizierte Prüfschnittstelle
(`/api/v1/audit/*`), zwei Verfügbarkeitsendpunkte ohne Mandantenbezug sowie die
Schnittstellenbeschreibung. **Jeder andere Pfad wird mit `404` beantwortet** und ist ausschließlich
innerhalb des internen Container-Netzes erreichbar. Dies ist die Maßnahme, die die Endpunkte der
Weboberfläche schützt, welche die Nutzeridentität aus einem vom Web-Tier gesetzten Header
übernehmen.

**Erhöhte Prüfung bei plattformweiten Änderungen.** Die Freigabe einer Prüfregel
(`POST /api/v1/rules/{rule_id}/review`) wirkt auf alle nachfolgenden Prüfungen und verlangt deshalb
ein von der Engine **selbst verifiziertes** JSON Web Token (Aussteller, Zielgruppe und Signatur
gegen die veröffentlichten Schlüssel der Weboberfläche), nicht lediglich einen Header.

*Offen — ausdrücklich benannt:*

- **Es gibt keine Rollen innerhalb einer Praxis.** Jedes freigeschaltete Konto einer Organisation
  kann Prüfungen anstoßen, freigeben, ablehnen und exportieren. Eine Trennung zwischen prüfender
  und administrierender Person besteht **nicht** — **in Umsetzung (RBAC), Zieltermin 07.09.2027**.
- **Keine feldbezogene Verschlüsselung.** Der Schutz gespeicherter Daten erfolgt auf Ebene des
  Datenträgers und des Netzwerks. Eine Person mit administrativem Datenbankzugang kann gespeicherte
  Prüfergebnisse einsehen. Der Kreis dieser Personen ist organisatorisch zu begrenzen und auf
  Vertraulichkeit zu verpflichten.
- **Die Prüf-Engine authentifiziert selbst niemanden** (mit Ausnahme des vorstehenden
  Regel-Endpunkts). Sie vertraut den Headern `X-User-ID` und `X-Organization-ID`, die der Web-Tier
  aus der geprüften Sitzung setzt. Dies ist ausschließlich deshalb tragfähig, weil die Engine nicht
  öffentlich erreichbar ist (siehe oben). Die Umstellung auf ein von der Engine geprüftes Token für
  alle Endpunkte ist **in Umsetzung, Zieltermin 07.09.2027**.

### 1.4 Trennungskontrolle

- **Trennung nach Mandant:** über die Spalte `organization_id` auf allen mandantenbezogenen
  Tabellen und einen Filter auf jeder Abfrage (siehe § 1.3). Ein Zugriff ohne Organisationsbezug
  wird mit `403` abgewiesen.
- **Trennung nach Zweck:** Prüfregeln und Gebührenkatalog sind versionierte Quelldaten und werden
  zur Laufzeit nicht verändert. Die Entscheidung einer Prüfkraft wird getrennt davon in der
  Datenbank abgelegt.
- **Trennung von Produktion und Entwicklung:** Entwicklungs- und Testbetrieb verwenden eine
  getrennte Datenbank; die Anwendung **verweigert den Start im Produktionsbetrieb**, wenn die
  konfigurierte Datenbank kein PostgreSQL ist, und verweigert dort zudem die automatische
  Schemaerzeugung — ein Schemastand entsteht im Produktionsbetrieb ausschließlich über eine
  geprüfte Migration.
- **Trennung der Konten beim Anbieter:** Die Datenbank liegt in dem von Neon betriebenen
  AWS-Konto, die verschlüsselten Sicherungen in dem des Auftragnehmers; beide werden über
  verschiedene Zugangsdaten erreicht.
- **Trennung von Echt- und Testdaten:** siehe § 0. Im Pilotbetrieb existieren ausschließlich
  synthetische Daten; jede mitgelieferte Beispiel- und Testdatei bezeichnet sich selbst als
  synthetisch, und ein automatisierter Test schlägt fehl, wenn eine Testdatei diese Kennzeichnung
  verliert oder ein Feld mit Personenbezug enthält.

---

## 2. Integrität

### 2.1 Weitergabekontrolle (Transport und Übermittlung)

- **Transportverschlüsselung ohne Ausnahme.** Caddy terminiert TLS mit Zertifikaten von Let's
  Encrypt und erneuert sie unbeaufsichtigt. Ein unverschlüsselter Dienst wird **nicht** angeboten;
  Port 80 dient allein der Zertifikatsausstellung und der Weiterleitung auf 443. Auf dem Hostnamen
  der Weboberfläche wird zusätzlich `Strict-Transport-Security` mit `max-age=31536000;
  includeSubDomains` gesetzt — bewusst **ohne** `preload`.
- **Sicherheitsheader** auf allen Hostnamen: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`; die Versionsangabe
  des Servers wird entfernt.
- **Verbindung zur Datenbank.** Die Verbindung zu Neon (PostgreSQL, Frankfurt) erfolgt
  ausschließlich TLS-gesichert.
- **Objektspeicher nur über TLS.** Der Speicherbereich der Sicherungen trägt eine Richtlinie, die
  **jeden** Zugriff ohne Transportverschlüsselung verweigert (`aws:SecureTransport: false` →
  `Deny`), einschließlich des Zugriffs durch den Auftragnehmer selbst. Der öffentliche Zugriff ist
  zusätzlich auf Ebene des Speicherbereichs blockiert.
- **Sicherungen verlassen den Server nur verschlüsselt.** Der Datenbankabzug wird **auf der
  virtuellen Maschine** mit `age` gegen einen öffentlichen Schlüssel verschlüsselt; der zugehörige
  private Schlüssel liegt auf keinem Produktivsystem und bei keinem Unterauftragsverarbeiter,
  sondern ausschließlich beim Auftragnehmer außerhalb der Betriebsumgebung. **Ein kompromittiertes
  Produktivsystem kann Sicherungen schreiben und keine einzige lesen.** Das Sicherungsskript
  verweigert den Lauf, wenn kein Empfängerschlüssel gesetzt ist.
- **Keine Übermittlung an Dritte im Prüfpfad.** Die Prüfung ist deterministisch und regelbasiert
  (Datalog/Soufflé und ASP/Clingo, beide lokal im Container). Es besteht **kein** Aufruf einer
  externen Schnittstelle während der Prüfung, insbesondere kein Sprachmodell, kein
  Übersetzungsdienst und kein externer Protokollierungsdienst. Eine Anbindung zur Fehlerüberwachung
  ist technisch vorgesehen, aber **nicht aktiviert**; eine Aktivierung macht den Dienst zum
  Unterauftragsverarbeiter und ist vorher zu benennen und genehmigen zu lassen.
- **Verschlüsselung im Ruhezustand.** Der Datenträger der virtuellen Maschine ist ein
  verschlüsselter EBS-gp3-Datenträger (`Encrypted: true`). Der Objektspeicher ist serverseitig
  verschlüsselt (SSE-S3, AES-256). Die verwaltete Datenbank ist anbieterseitig im Ruhezustand
  verschlüsselt. **Eine feldbezogene Verschlüsselung besteht nicht** (siehe § 1.3).

### 2.2 Eingabekontrolle (Nachvollziehbarkeit von Eingabe, Änderung, Löschung)

- **Ein fortschreibungsgeschütztes Protokoll.** Die Tabelle `audit_events` ist *append-only*, und
  dies ist **erzwungen, nicht nur beschrieben**: der Datenzugriffslayer verweigert jedes UPDATE und
  jedes DELETE auf dieser Tabelle mit einer eigenen Ausnahme (`AuditLogIsAppendOnly` in
  `apps/engine/app/db/models.py`). Ergänzend ist ein `REVOKE UPDATE, DELETE ON audit_events` für
  die Anwendungsrolle in der Datenbank vorgesehen; dessen Einrichtung ist Teil der
  Berechtigungsvergabe der Betriebsumgebung — **in Umsetzung, Zieltermin 07.09.2027**.
- **Protokolliert wird**, jeweils mit handelnder Person (`actor`) und Zeitstempel und in derselben
  Transaktion wie die protokollierte Änderung: Erstellung (`CREATED`), Einsichtnahme (`VIEWED`),
  Freigabe (`APPROVED`), Ablehnung (`REJECTED`), Export (`EXPORTED`) sowie die Löschung durch die
  Aufbewahrungsroutine (`DATA_PURGED`). Für Vorgänge über die Weboberfläche ist `actor` eine
  auflösbare Benutzerkennung.
- **Ein unattribuierter Protokolleintrag ist nicht schreibbar**; das Schreiben verweigert eine
  leere Handelndenangabe.
- **Nachweis des Systemstands.** Jedes Prüfergebnis trägt einen SHA-256-Prüfwert (`receipt_hash`)
  über Katalogfassung, Regelstand, die Logikprogramme, die Solver-Versionen und die Eingabe. Damit
  ist überprüfbar, unter welchem Systemstand ein Ergebnis entstanden ist.
- **Eingabeprüfung.** Der Dateityp wird anhand der Byte-Signatur erkannt, nicht anhand des
  Dateinamens. Archive werden gegen die deklarierte **und** gegen die tatsächlich entpackte Größe
  geprüft; Einträge, die das Archivwurzelverzeichnis verlassen, werden abgewiesen. Es gelten
  Größen- und Mengenbegrenzungen (5 MiB je Einzellieferung, 50 MB je Archiv, 256 MiB entpackt,
  höchstens 500 Lieferungen je Auftrag) sowie eine Ratenbegrenzung je Schlüssel (100 Anfragen pro
  Minute für Einzelprüfungen, 10 Uploads pro Stunde für Stapelprüfungen).
- **Vorgangsnummer.** Jede Anfrage erhält eine `X-Request-ID`, die in jeder zugehörigen
  Protokollzeile erscheint und dem Aufrufer im Fehlerfall genannt wird, so dass eine Rückfrage
  **ohne Übermittlung von Rechnungsinhalten** möglich ist.
- **Was nicht protokolliert wird:** Anfrage- und Antwortinhalte, Dateinamen hochgeladener Dateien,
  GOÄ-Ziffern, Beträge, weitere Header-Werte sowie lokale Variablen aus Programmabbrüchen. Auch die
  Fehlertabelle (`error_log`) enthält ausschließlich Fehlertyp, Fehlermeldung, Routenmuster,
  Vorgangsnummer und Organisation — **keine Rechnungsinhalte**.

*Offen:* Eine **Manipulationssicherheit im vollen Sinne** — eine Hash-Kette oder ein externer Zeuge,
so dass auch eine Person mit Eigentümerrechten an der Datenbank das Protokoll nicht unbemerkt
umschreiben kann — ist **nicht umgesetzt**. Umgesetzt ist die Verweigerung auf Anwendungsebene;
**in Umsetzung, Zieltermin 07.09.2027**.

---

## 3. Verfügbarkeit und Belastbarkeit

### 3.1 Verfügbarkeitskontrolle

- **Verwaltete Datenbank** (Neon, PostgreSQL, Region `aws-eu-central-1`) mit anbieterseitiger
  Verschlüsselung im Ruhezustand und Wiederherstellung auf einen Zeitpunkt. Das Zeitfenster dieser
  Wiederherstellung ist tarifabhängig; der Auftragnehmer hält ausdrücklich fest: **ein Zeitfenster
  von sechs Stunden ist ein Rollback und keine Sicherung.**
- **Tägliche verschlüsselte Sicherung.** Ein Abzug der Datenbank wird erzeugt, **bei der Erzeugung
  auf Lesbarkeit geprüft** (`pg_restore --list`), mit `age` verschlüsselt (§ 2.1) und in einen
  privaten Speicherbereich in Frankfurt hochgeladen. Der Upload wird **zurückgelesen und seine
  Länge verglichen**, so dass ein Upload, der Erfolg meldet und nichts gespeichert hat, erkannt wird.
- **Der Speicherbereich ist versioniert**, so dass ein Überschreiben die vorherige Fassung erhält.
- **Das Produktivsystem kann Sicherungen nicht löschen.** Die IAM-Berechtigung der virtuellen
  Maschine umfasst ausschließlich `s3:PutObject` und `s3:GetObject` auf die Objekte genau dieses
  Speicherbereichs. `s3:DeleteObject`, `s3:ListBucket` und jede Änderung der Speicherbereichs-
  richtlinie sind **nicht** enthalten. Ein kompromittierter Server kann die Sicherungen daher weder
  zerstören noch aufzählen noch den Speicherbereich öffentlich schalten.
- **Betriebssicherheit der Anwendung:** unterbrochene Stapelaufträge werden beim Start
  automatisch geschlossen bzw. fortgesetzt; bereits erzeugte Ergebnisse werden nicht erneut
  berechnet. Verbindungsbedingte Datenbankfehler werden begrenzt und mit Zufallsverzögerung
  wiederholt; deterministische Fehler nicht.
- **Verfügbarkeitsendpunkte** (`/health`, `/api/v1/health`) sind ohne Mandantenbezug abrufbar und
  für eine externe Überwachung vorgesehen.

*Offen — ausdrücklich benannt:*

- **Eine Testwiederherstellung ist nicht nachgewiesen.** Geprüft werden die Lesbarkeit des Archivs
  und der Upload, **nicht** die vollständige Rückführung in eine Datenbank. Eine dokumentierte
  Testwiederherstellung mit gemessener Wiederherstellungszeit ist **in Umsetzung, Zieltermin
  07.09.2027**.
- **Für die Sicherungen ist keine Aufbewahrungsfrist eingerichtet.** Derzeit löscht kein Verfahren
  die abgelegten Objekte. Zu beachten ist, dass der Speicherbereich versioniert ist: eine Regel,
  die nur die jeweils aktuelle Fassung verfallen lässt, löscht die vorherigen Fassungen **nicht**.
  Die Aufbewahrungsdauer der Sicherungen ist die tatsächliche Obergrenze dafür, wie lange Daten
  eine Löschungsaufforderung überdauern — **in Umsetzung, Zieltermin 07.09.2027**.
- **Der Verlust des privaten `age`-Schlüssels macht sämtliche Sicherungen unbrauchbar.** Das ist
  der bewusst eingegangene Preis für die Eigenschaft, dass ein Produktivsystem Sicherungen
  schreiben und nicht lesen kann. Die Verwahrung des Schlüssels ist eine organisatorische Maßnahme
  und als solche zu regeln.
- **Anwendung, Datenbank und Sicherungen liegen bei einem einzigen Infrastrukturanbieter.** Die
  Trennung besteht auf Ebene der Konten, der Dienste und der Zugangsdaten, und die Sicherungen sind
  zusätzlich mit einem Schlüssel verschlüsselt, der bei keinem Unterauftragsverarbeiter liegt. Ein
  Ausfall oder eine Kündigung auf Seiten von AWS trifft jedoch alle drei Bestandteile zugleich.
- **Es besteht keine zugesagte Verfügbarkeit (SLA).** Der Betrieb erfolgt auf einer einzelnen
  virtuellen Maschine ohne Lastverteilung und ohne Bereitschaftsinstanz.

### 3.2 Wiederherstellbarkeit und Aufbewahrung (Speicherbegrenzung, Art. 5 Abs. 1 lit. e DSGVO)

Die Aufbewahrung ist **umgesetzt und konfigurierbar**:

| Datenkategorie | Speicherort | Aufbewahrung |
| --- | --- | --- |
| Einzelprüfung `POST /api/v1/audit/single` | Ausschließlich Arbeitsspeicher | **Keine Speicherung** |
| Hochgeladenes Archiv einer Stapelprüfung | Datenträger (`UPLOAD_DIR`) | Bis zum Endzustand des Auftrags, danach automatische Löschung (`RETAIN_BULK_UPLOADS=false`) |
| Prüfergebnisse, Aufträge, Vorschläge | PostgreSQL | `DATA_RETENTION_DAYS` — Voreinstellung 90 Tage, im Pilotbetrieb 30 |
| Fehlerprotokoll (`error_log`) | PostgreSQL | `DATA_RETENTION_DAYS` |
| API-Schlüssel (nur Hashwert) | PostgreSQL | Bis zum Widerruf; die Zeile bleibt zu Nachweiszwecken |
| Protokoll `audit_events` | PostgreSQL | **Wird nicht gelöscht** (siehe unten) |

Die Löschung führt `apps/engine/scripts/purge_old_data.py` aus, das der Betrieb nächtlich über
`cron` startet; die Anwendung selbst besitzt bewusst keinen eigenen Zeitplaner. Eigenschaften des
Verfahrens:

- **Eine Transaktion**, die entweder vollständig wirkt oder gar nicht. Dateien auf dem Datenträger
  werden **innerhalb** der Transaktion gelöscht; scheitert eine Löschung, wird der gesamte Lauf
  zurückgerollt, damit kein Archiv zurückbleibt, das keine Zeile mehr benennt.
- **Wiederholbar (idempotent)**: ein zweiter Lauf findet keine Zeilen mehr und tut nichts; ein
  zurückgerollter Lauf ist kein Sonderfall, sondern ein Lauf, der nichts gelöscht hat.
- **`--dry-run`** berichtet, was gelöscht würde, und ändert nichts.
- **`RETENTION_ENABLED=false`** setzt die Löschungen für einen *legal hold* aus, ohne den Auftrag
  zu stoppen; der Lauf berichtet weiterhin, was über der Frist liegt.
- **Das Protokoll überlebt die Löschung, und das ist der Zweck.** Art. 5 Abs. 1 lit. e begründet
  die Pflicht zu löschen; Art. 5 Abs. 2 begründet die davon getrennte Pflicht, die Einhaltung
  **nachweisen** zu können. Jeder gelöschte Vorgang hinterlässt daher einen `DATA_PURGED`-Eintrag,
  der den Vorgang (über eine mitgeführte Kennung, nicht über einen Fremdschlüssel), den Zeitpunkt,
  die angewandte Aufbewahrungsfrist und den Stichtag benennt. Der verbleibende Datensatz ist damit
  der Nachweis der Löschung, nicht der klinische Inhalt.
- **Die Frist ist eine Untergrenze, keine Obergrenze.** Ein Verantwortlicher, der längeren
  gesetzlichen Aufbewahrungspflichten unterliegt (etwa § 147 AO, § 10 MBO-Ä), erhöht den Wert.

*Offen:* **Eine Löschung auf Weisung ist ein manueller Vorgang**; eine Selbstbedienungsfunktion
besteht nicht — **in Umsetzung, Zieltermin 07.09.2027**.

---

## 4. Auftragskontrolle (Verarbeitung nur auf Weisung)

- Die Verarbeitung erfolgt ausschließlich zur Prüfung der übermittelten Abrechnungslieferungen. Es
  findet **keine** Verarbeitung zu eigenen Zwecken des Auftragnehmers statt, insbesondere kein
  Training von Modellen, keine Auswertung zu Marktforschungszwecken und keine Weitergabe an Dritte.
- **Unterauftragsverarbeiter** sind in `legal/AVV_Anlage.md` benannt; ihre Beauftragung erfolgt
  nach den dort geregelten Bedingungen.
- **Der Auftragsverarbeitungsvertrag ist noch nicht abgeschlossen** — weder mit einem
  Verantwortlichen noch als gegengezeichneter Vertrag mit sämtlichen Unterauftragsverarbeitern.
  Dies ist der Grund, aus dem ausschließlich synthetische Daten verarbeitet werden
  (§ 0) — **in Umsetzung, Zieltermin 30.06.2027**.
- **Verpflichtung auf Vertraulichkeit.** Personen, die für den Auftragnehmer tätig sind, sind auf
  Vertraulichkeit zu verpflichten; im Hinblick auf § 203 Abs. 4 StGB ist diese Verpflichtung
  **schriftlich, personenbezogen und nachweisbar** zu erteilen. Der Stand ist in
  `legal/COMPLIANCE_ROADMAP.md` festgehalten — **in Umsetzung, Zieltermin 30.06.2027**.
- **Änderungskontrolle.** Änderungen am Quellcode erfolgen über nachvollziehbare Pull Requests mit
  automatisierter Prüfung (Testsuite, Typprüfung, Vertragsabgleich der Schnittstelle). Änderungen
  an Regeldaten erfolgen in einem eigenen Zweig und erfordern eine gesonderte fachliche Freigabe.
  Der Zugriff auf Produktionssysteme ist auf die betriebsführenden Personen beschränkt.

---

## 5. Verfahren zur Behandlung von Sicherheitsvorfällen (Incident Response)

**Erkennung.**

- Strukturierte Protokollierung (JSON, eine Zeile je Anfrage) mit Vorgangsnummer, Zeitpunkt,
  Routenmuster, Statuscode, Dauer und — soweit bekannt — Schlüsselkennung und Organisation.
- Erfassung jedes unerwarteten Fehlers in `error_log` mit Fehlertyp, Meldung, Route,
  Vorgangsnummer und Organisation, **ohne Rechnungsinhalte**, so dass die Tabelle auch von Personen
  eingesehen werden kann, die keinen Zugang zu Gesundheitsdaten haben.
- Externe Verfügbarkeitsüberwachung über `/health`.

**Meldeweg und Fristen.**

1. Feststellung und Erstbewertung durch Oussama Khadraoui; Erreichbarkeit: contact@azmoth.com, +216 50 745 682.
2. Eindämmung: Widerruf betroffener API-Schlüssel (wirkt ab der nächsten Anfrage), Ungültigmachen
   von Sitzungen, erforderlichenfalls Sperrung des Zugangs auf Netzwerkebene.
3. **Unverzügliche Unterrichtung des Verantwortlichen** nach Kenntniserlangung, damit dieser die
   Frist des Art. 33 Abs. 1 DSGVO (72 Stunden gegenüber der Aufsichtsbehörde) einhalten kann. Der
   Auftragnehmer ist Auftragsverarbeiter; die Meldung an die Aufsichtsbehörde obliegt dem
   Verantwortlichen (Art. 33 Abs. 2 DSGVO).
4. Dokumentation des Vorfalls, seiner Auswirkungen und der ergriffenen Maßnahmen; Nachbereitung mit
   Ableitung technischer oder organisatorischer Änderungen.

**Offen — ausdrücklich benannt:** Es besteht **kein** automatisiertes Angriffserkennungs- oder
Alarmierungssystem, keine zentrale Protokollzusammenführung (SIEM) und keine dokumentierte
Rufbereitschaft. Die Erkennung beruht auf der Protokollauswertung und der externen
Verfügbarkeitsüberwachung — **in Umsetzung, Zieltermin 07.09.2027**.

---

## 6. Überprüfung, Bewertung und Evaluierung (Art. 32 Abs. 1 lit. d DSGVO)

| Gegenstand | Turnus | Verantwortlich |
| --- | --- | --- |
| Überprüfung dieses Dokuments gegen den tatsächlichen Systemstand | jährlich **und** bei jeder Änderung an Speicherung, Protokollierung, Aufbewahrung, Verarbeitungsort oder Kreis der Unterauftragsverarbeiter — dann im selben Pull Request | Oussama Khadraoui |
| Prüfung der Aufbewahrungsläufe (Protokoll der `cron`-Ausführung, `DATA_PURGED`-Einträge) | monatlich | Oussama Khadraoui |
| Prüfung der Freigabeliste für Registrierungen und der ausgegebenen API-Schlüssel | vierteljährlich | Oussama Khadraoui |
| Testwiederherstellung einer Sicherung | halbjährlich, sobald eingerichtet (§ 3.1) | Oussama Khadraoui |
| Überprüfung der Unterauftragsverarbeiter und ihrer Nachweise | jährlich | Oussama Khadraoui |
| Penetrationstest durch einen unabhängigen Dritten | **noch nicht durchgeführt** — Zieltermin 31.12.2026 | Oussama Khadraoui |

Die automatisierte Testsuite läuft bei jeder Änderung und prüft dabei unter anderem die in diesem
Dokument genannten Eigenschaften: dass keine Datenstruktur Patientenidentität aufnehmen kann, dass
Beispiel- und Testdateien sich als synthetisch bezeichnen und keine Personendaten enthalten, dass
keine Einstellung ein Geheimnis führt, dass das Protokoll nicht änderbar ist und dass die
Aufbewahrungsroutine wiederholbar und transaktional arbeitet.

---

## 7. Ausdrücklich nicht behauptet

Der Auftragnehmer stellt klar, dass folgende Aussagen **nicht** getroffen werden:

- keine Zertifizierung nach ISO 27001, ISO 27701, SOC 2, TISAX oder einem anderen Standard;
- kein durchgeführter Penetrationstest und keine externe Sicherheitsüberprüfung;
- keine abgeschlossene Datenschutz-Folgenabschätzung;
- kein unterzeichneter Auftragsverarbeitungsvertrag mit einem Verantwortlichen oder mit sämtlichen
  Unterauftragsverarbeitern;
- keine abgeschlossene Bewertung nach § 203 StGB und keine erteilten
  Verschwiegenheitsverpflichtungen nach § 203 Abs. 4 StGB;
- keine feld- oder spaltenbezogene Verschlüsselung in der Datenbank;
- keine Anonymisierung im Sinne einer nicht rückführbaren Verarbeitung: freie Textfelder
  (`begruendung`, `text`) werden fachlich benötigt und bleiben erhalten;
- keine Zusage einer bestimmten Verfügbarkeit;
- keine nachgewiesene Testwiederherstellung.

---

*Erstellt auf Grundlage des Quellstands zum 2026-09-06. Bei jeder Änderung an Speicherung,
Protokollierung, Aufbewahrung, am Verarbeitungsort oder am Kreis der Unterauftragsverarbeiter ist
dieses Dokument im selben Pull Request anzupassen. Dieses Dokument ist ein Entwurf und ersetzt keine
anwaltliche Prüfung.*
