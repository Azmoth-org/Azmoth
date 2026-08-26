import type { Metadata } from "next"

import { AuditWorkbench } from "@/components/padnext/audit-workbench"
import { SyntheticDataBanner } from "@/components/review/synthetic-data-banner"

export const metadata: Metadata = {
  title: "PADnext-Rechnungsprüfung",
  description:
    "Prüfung einer bereits kodierten PADnext-Lieferung gegen die GOÄ-Regeln. Nur synthetische Daten.",
}

/**
 * `/padnext` — audit an already-coded delivery.
 *
 * A server component shell, like `/review`: the banner and the explanation of the three buckets must
 * render even if the client bundle fails, and only the upload below is interactive.
 */
export default function PadnextPage() {
  return (
    <>
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">PADnext-Rechnung prüfen</h1>
        <p className="text-muted-foreground text-sm">
          Eine PADnext-Lieferung kommt fertig kodiert an, also ist dies keine Kodierung, sondern eine
          Prüfung: dieselben Datalog-Regeln entscheiden, welche Positionen bestehen, und der Betrag
          wird aus dem eigenen versionierten Katalog nachgerechnet. Die Datei wird nicht als
          Preisauskunft geglaubt — die GOÄ-Nachrechnung gilt.
        </p>
        <p className="text-muted-foreground text-sm">
          Das Ergebnis wird bewusst in drei Gruppen getrennt, statt in eine einzige Summe „strittig“:
          was wir <strong>beweisen</strong> können, was wir <strong>bestätigen</strong> können, und
          was wir <strong>nicht beurteilen</strong> können.
        </p>
      </header>

      <SyntheticDataBanner />
      <AuditWorkbench />
    </>
  )
}
