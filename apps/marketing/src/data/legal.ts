/**
 * Legal pages — a structure, not a legal text.
 *
 * German law requires an Impressum (§ 5 DDG) and a GDPR-compliant privacy notice,
 * and both must state facts about a specific company: legal form, registered
 * address, register number, VAT ID, the actual processors under contract. None of
 * those are inventable, and a plausible-looking wrong one is worse than a visible
 * gap — it is the kind of thing that draws an Abmahnung.
 *
 * So every such fact is `[...]` here, the pages render a standing notice saying the
 * text is an unreviewed draft, and the whole thing needs a lawyer before launch.
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

export const datenschutz: LegalDocument = {
  title: "Datenschutzerklärung",
  intro:
    "Diese Erklärung beschreibt, welche personenbezogenen Daten beim Besuch dieser " +
    "Website und bei der Nutzung von Azmoth verarbeitet werden.",
  updated: "2026-08-29",
  sections: [
    {
      title: "1. Verantwortliche Stelle",
      body: [
        "Verantwortlich im Sinne der Datenschutz-Grundverordnung (DSGVO) ist:",
        "[Vollständiger Firmenname], [Rechtsform]\n[Straße und Hausnummer]\n[PLZ, Ort]\nDeutschland",
        "Vertreten durch: [Name der vertretungsberechtigten Person]\nE-Mail: [E-Mail-Adresse]\nHandelsregister: [Registergericht, HRB-Nummer]\nUmsatzsteuer-Identifikationsnummer: [USt-IdNr.]",
      ],
    },
    {
      title: "2. Datenschutzbeauftragter",
      body: [
        "[Sofern ein Datenschutzbeauftragter bestellt ist: Name und Kontaktdaten. " +
          "Andernfalls ist dieser Abschnitt zu streichen.]",
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
        "Hosting-Anbieter: [Name und Anschrift des Anbieters]. Speicherdauer: [Dauer].",
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
        "Eingesetzter Dienst: [Name des Dienstes und Anbieter]. Übermittlung in " +
          "Drittländer: [Angabe, ggf. Rechtsgrundlage der Übermittlung].",
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
          "der Auftragsverarbeitungsvertrag: [Verweis auf den AVV].",
      ],
    },
    {
      title: "6. Ihre Rechte",
      body: [
        "Sie haben das Recht auf Auskunft (Art. 15 DSGVO), Berichtigung (Art. 16 " +
          "DSGVO), Löschung (Art. 17 DSGVO), Einschränkung der Verarbeitung (Art. 18 " +
          "DSGVO), Datenübertragbarkeit (Art. 20 DSGVO) sowie Widerspruch gegen die " +
          "Verarbeitung (Art. 21 DSGVO).",
        "Beschwerden richten Sie an die zuständige Aufsichtsbehörde: " +
          "[Name und Anschrift der Aufsichtsbehörde].",
      ],
    },
  ],
};

export const agb: LegalDocument = {
  title: "Allgemeine Geschäftsbedingungen",
  intro:
    "Diese Bedingungen regeln die Nutzung von Azmoth durch Unternehmerinnen und " +
    "Unternehmer im Sinne des § 14 BGB.",
  updated: "2026-08-29",
  sections: [
    {
      title: "1. Geltungsbereich",
      body: [
        "Diese Bedingungen gelten für sämtliche Verträge zwischen [Firmenname] " +
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
      body: ["[Registrierung, Testphase, Laufzeit, Verlängerung, Kündigungsfristen.]"],
    },
    {
      title: "4. Preise und Zahlung",
      body: ["[Preismodell, Abrechnungszeitraum, Fälligkeit, Zahlungsarten, Verzug.]"],
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
      body: ["[Zugesicherte Verfügbarkeit, Wartungsfenster, Ausnahmen.]"],
    },
    {
      title: "7. Haftung",
      body: [
        "[Haftungsregelung. Zu beachten: Der Haftungsausschluss unterliegt der " +
          "AGB-Inhaltskontrolle nach §§ 305 ff. BGB; die Haftung für Vorsatz, grobe " +
          "Fahrlässigkeit und Schäden aus der Verletzung des Lebens, des Körpers oder " +
          "der Gesundheit ist nicht abdingbar.]",
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
        "Gerichtsstand für alle Streitigkeiten ist [Ort], soweit der Kunde Kaufmann, " +
          "juristische Person des öffentlichen Rechts oder öffentlich-rechtliches " +
          "Sondervermögen ist.",
      ],
    },
  ],
};
