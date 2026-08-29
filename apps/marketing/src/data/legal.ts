/**
 * Legal pages — a structure to fill in, not a legal text.
 *
 * German law requires an Impressum (§ 5 DDG, formerly § 5 TMG), a
 * broadcasting-state-treaty content contact (§ 18 Abs. 2 MStV, which replaced
 * § 55 Abs. 2 RStV in November 2020), and a GDPR-compliant privacy notice. All
 * three must state facts about a specific company — legal form, registered
 * address, register number, VAT ID, the actual processors under contract. None of
 * those are inventable, and a plausible-looking wrong one is worse than a visible
 * gap: it is what an Abmahnung is written about.
 *
 * So every such fact is a `{{Platzhalter}}` marker here. `LegalDocumentView`
 * renders each one as a bright, impossible-to-miss inline chip, and every page
 * carries a standing banner saying the text is an unreviewed draft.
 *
 * ────────────────────────────────────────────────────────────────────────────
 * TO FILL IN BEFORE LAUNCH — every marker used below, in one list:
 *
 *   Firmenname                     e.g. "Azmoth GmbH"
 *   Rechtsform                     GmbH / UG (haftungsbeschränkt) / GbR / …
 *   Straße und Hausnummer
 *   PLZ und Ort
 *   Vertretungsberechtigte Person  the managing director(s), full name
 *   E-Mail-Adresse                 must be a monitored mailbox
 *   Telefonnummer                  § 5 DDG wants a "schnelle elektronische
 *                                  Kontaktaufnahme" — email plus one more channel
 *   Registergericht und HRB-Nummer
 *   USt-IdNr.                      § 27a UStG
 *   Inhaltlich Verantwortlicher    § 18 Abs. 2 MStV — name AND full address,
 *                                  even when identical to the above
 *   Aufsichtsbehörde               the competent data-protection authority
 *   Hosting-Anbieter               name and address
 *   Analyse-Dienst                 name and provider of the analytics service
 *   Speicherdauer                  log retention period
 *   Gerichtsstand                  place of jurisdiction
 *
 * AND STILL MISSING ENTIRELY, because they need decisions rather than facts:
 *   - a Datenschutzbeauftragter, if one must be appointed (Art. 37 DSGVO,
 *     § 38 BDSG — from 20 people regularly processing personal data)
 *   - the AVV (Auftragsverarbeitungsvertrag) the privacy notice points at
 *   - §§ 3, 4 and 6 of the AGB: contract term, pricing, availability
 *   - Verbraucherstreitbeilegung under § 36 VSBG, if consumers are served
 * ────────────────────────────────────────────────────────────────────────────
 */

export interface LegalSection {
  title: string;
  body: string[];
}

export interface LegalDocument {
  title: string;
  intro: string;
  /** ISO date of the last revision, rendered as "Stand: …". */
  updated: string;
  sections: LegalSection[];
}

const UPDATED = "2026-08-29";

export const impressum: LegalDocument = {
  title: "Impressum",
  intro: "Angaben gemäß § 5 DDG und § 18 Abs. 2 MStV.",
  updated: UPDATED,
  sections: [
    {
      title: "Diensteanbieter",
      body: [
        "{{Firmenname}} {{Rechtsform}}\n{{Straße und Hausnummer}}\n{{PLZ und Ort}}\nDeutschland",
      ],
    },
    {
      title: "Vertreten durch",
      body: ["{{Vertretungsberechtigte Person}}"],
    },
    {
      title: "Kontakt",
      body: [
        "E-Mail: {{E-Mail-Adresse}}\nTelefon: {{Telefonnummer}}",
        "§ 5 DDG verlangt Angaben, die eine schnelle elektronische Kontaktaufnahme " +
          "ermöglichen. Eine E-Mail-Adresse allein genügt nach der Rechtsprechung " +
          "nicht durchgängig; ein zweiter Kanal gehört dazu.",
      ],
    },
    {
      title: "Registereintrag",
      body: ["Registergericht und Registernummer: {{Registergericht und HRB-Nummer}}"],
    },
    {
      title: "Umsatzsteuer-Identifikationsnummer",
      body: [
        "Umsatzsteuer-Identifikationsnummer gemäß § 27a Umsatzsteuergesetz:\n{{USt-IdNr.}}",
      ],
    },
    {
      title: "Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV",
      body: [
        "{{Inhaltlich Verantwortlicher}}",
        "Anzugeben sind Name und vollständige Anschrift — auch dann, wenn sie mit " +
          "den Angaben des Diensteanbieters übereinstimmen. Die frühere Grundlage " +
          "§ 55 Abs. 2 RStV wurde im November 2020 durch den Medienstaatsvertrag " +
          "abgelöst; die Pflicht selbst besteht unverändert fort.",
      ],
    },
    {
      title: "Haftung für Inhalte und Links",
      body: [
        "Als Diensteanbieter sind wir für eigene Inhalte auf diesen Seiten nach den " +
          "allgemeinen Gesetzen verantwortlich (§ 7 Abs. 1 DDG). Nach §§ 8 bis 10 DDG " +
          "sind wir als Diensteanbieter jedoch nicht verpflichtet, übermittelte oder " +
          "gespeicherte fremde Informationen zu überwachen.",
        "Für die Inhalte externer Links sind ausschließlich deren Betreiber " +
          "verantwortlich. Zum Zeitpunkt der Verlinkung waren keine Rechtsverstöße " +
          "erkennbar; bei Bekanntwerden entfernen wir solche Links umgehend.",
      ],
    },
  ],
};

export const datenschutz: LegalDocument = {
  title: "Datenschutzerklärung",
  intro:
    "Diese Erklärung beschreibt, welche personenbezogenen Daten beim Besuch dieser " +
    "Website und bei der Nutzung von Azmoth verarbeitet werden.",
  updated: UPDATED,
  sections: [
    {
      title: "1. Verantwortliche Stelle",
      body: [
        "Verantwortlich im Sinne der Datenschutz-Grundverordnung (DSGVO) ist:",
        "{{Firmenname}} {{Rechtsform}}\n{{Straße und Hausnummer}}\n{{PLZ und Ort}}\nDeutschland",
        "Vertreten durch: {{Vertretungsberechtigte Person}}\nE-Mail: {{E-Mail-Adresse}}\nHandelsregister: {{Registergericht und HRB-Nummer}}\nUmsatzsteuer-Identifikationsnummer: {{USt-IdNr.}}",
      ],
    },
    {
      title: "2. Datenschutzbeauftragter",
      body: [
        "Ein Datenschutzbeauftragter ist zu benennen, sobald in der Regel mindestens " +
          "20 Personen ständig mit der automatisierten Verarbeitung personenbezogener " +
          "Daten beschäftigt sind (Art. 37 DSGVO, § 38 BDSG). Trifft das zu, gehören " +
          "Name und Kontaktdaten hierher; andernfalls ist dieser Abschnitt zu streichen.",
      ],
    },
    {
      title: "3. Zugriffsdaten",
      body: [
        "Beim Aufruf dieser Website werden durch den Hosting-Anbieter automatisch " +
          "Zugriffsdaten verarbeitet (IP-Adresse, Zeitpunkt, aufgerufene Seite, " +
          "übertragene Datenmenge, Referrer, Browser- und Betriebssystemkennung).",
        "Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO. Das berechtigte Interesse " +
          "liegt im sicheren und stabilen Betrieb der Website.",
        "Hosting-Anbieter: {{Hosting-Anbieter}}\nSpeicherdauer: {{Speicherdauer}}",
      ],
    },
    {
      title: "4. Reichweitenmessung",
      body: [
        "Diese Website setzt Analyse-Cookies ausschließlich nach ausdrücklicher " +
          "Einwilligung ein. Ohne Einwilligung wird kein Analyse-Skript geladen und " +
          "keine Messung durchgeführt.",
        "Rechtsgrundlage ist Art. 6 Abs. 1 lit. a DSGVO in Verbindung mit § 25 Abs. 1 " +
          "TDDDG. Die Einwilligung kann jederzeit mit Wirkung für die Zukunft " +
          "widerrufen werden.",
        "Eingesetzter Dienst: {{Analyse-Dienst}}",
      ],
    },
    {
      title: "5. Verarbeitung im Rahmen der Anwendung",
      body: [
        "Bei der Nutzung von Azmoth werden Behandlungs- und Abrechnungsdaten " +
          "verarbeitet. Diese Verarbeitung erfolgt im Auftrag der jeweiligen Praxis " +
          "auf Grundlage eines Vertrags zur Auftragsverarbeitung nach Art. 28 DSGVO.",
        "Verantwortlich für diese Daten bleibt die Praxis. Einzelheiten zu Zwecken, " +
          "Kategorien, Speicherdauer und technisch-organisatorischen Maßnahmen regelt " +
          "der Auftragsverarbeitungsvertrag.",
      ],
    },
    {
      title: "6. Ihre Rechte",
      body: [
        "Sie haben das Recht auf Auskunft (Art. 15 DSGVO), Berichtigung (Art. 16 " +
          "DSGVO), Löschung (Art. 17 DSGVO), Einschränkung der Verarbeitung (Art. 18 " +
          "DSGVO), Datenübertragbarkeit (Art. 20 DSGVO) sowie Widerspruch gegen die " +
          "Verarbeitung (Art. 21 DSGVO).",
        "Beschwerden richten Sie an die zuständige Aufsichtsbehörde:\n{{Aufsichtsbehörde}}",
      ],
    },
  ],
};

export const agb: LegalDocument = {
  title: "Allgemeine Geschäftsbedingungen",
  intro:
    "Diese Bedingungen regeln die Nutzung von Azmoth durch Unternehmerinnen und " +
    "Unternehmer im Sinne des § 14 BGB.",
  updated: UPDATED,
  sections: [
    {
      title: "1. Geltungsbereich",
      body: [
        "Diese Bedingungen gelten für sämtliche Verträge zwischen {{Firmenname}} " +
          "(nachfolgend „Anbieter“) und dem Kunden über die Nutzung von Azmoth.",
        "Abweichende Bedingungen des Kunden werden nicht Vertragsbestandteil, es sei " +
          "denn, der Anbieter stimmt ihrer Geltung ausdrücklich schriftlich zu.",
      ],
    },
    {
      title: "2. Leistungsgegenstand",
      body: [
        "Azmoth unterstützt bei der Kodierung und Prüfung von Rechnungen nach der " +
          "Gebührenordnung für Ärzte. Die Anwendung erstellt Vorschläge und legt deren " +
          "Begründung offen.",
        "Azmoth trifft keine Abrechnungsentscheidung. Jede Position bedarf der " +
          "Freigabe durch den Kunden. Die Verantwortung für die abgerechnete Rechnung " +
          "verbleibt beim Kunden.",
        "Azmoth ersetzt keine rechtliche oder steuerliche Beratung.",
      ],
    },
    {
      title: "3. Vertragsschluss und Laufzeit",
      body: [
        "{{Registrierung, Testphase, Laufzeit, Verlängerung und Kündigungsfristen}}",
      ],
    },
    {
      title: "4. Preise und Zahlung",
      body: [
        "{{Preismodell, Abrechnungszeitraum, Fälligkeit, Zahlungsarten und Verzug}}",
      ],
    },
    {
      title: "5. Pflichten des Kunden",
      body: [
        "Der Kunde sichert zu, dass er zur Verarbeitung der eingestellten Daten " +
          "berechtigt ist und die erforderlichen datenschutzrechtlichen Grundlagen " +
          "vorliegen.",
        "Zugangsdaten sind vertraulich zu behandeln und dürfen nicht an Dritte " +
          "weitergegeben werden.",
      ],
    },
    {
      title: "6. Verfügbarkeit",
      body: ["{{Zugesicherte Verfügbarkeit, Wartungsfenster und Ausnahmen}}"],
    },
    {
      title: "7. Haftung",
      body: [
        "{{Haftungsregelung}}",
        "Zu beachten: Der Haftungsausschluss unterliegt der AGB-Inhaltskontrolle nach " +
          "§§ 305 ff. BGB. Die Haftung für Vorsatz, grobe Fahrlässigkeit und für " +
          "Schäden aus der Verletzung des Lebens, des Körpers oder der Gesundheit ist " +
          "nicht abdingbar.",
      ],
    },
    {
      title: "8. Datenschutz",
      body: [
        "Die Verarbeitung personenbezogener Daten im Auftrag des Kunden erfolgt auf " +
          "Grundlage eines gesonderten Vertrags zur Auftragsverarbeitung nach Art. 28 " +
          "DSGVO.",
      ],
    },
    {
      title: "9. Schlussbestimmungen",
      body: [
        "Es gilt das Recht der Bundesrepublik Deutschland unter Ausschluss des " +
          "UN-Kaufrechts.",
        "Gerichtsstand für alle Streitigkeiten ist {{Gerichtsstand}}, soweit der Kunde " +
          "Kaufmann, juristische Person des öffentlichen Rechts oder " +
          "öffentlich-rechtliches Sondervermögen ist.",
      ],
    },
  ],
};
