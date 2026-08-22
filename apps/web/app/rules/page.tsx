import type { Metadata } from "next"
import Link from "next/link"

import { RuleReviewWorkbench } from "@/components/rules/review-workbench"

export const metadata: Metadata = {
  title: "Regelprüfung",
  description:
    "Internes Werkzeug: maschinell extrahierte GOÄ-Regeln prüfen und freigeben, um die Gruppe „unbestätigt“ in künftigen Rechnungsprüfungen zu verkleinern.",
}

/**
 * `/rules` — the internal rule verification workflow.
 *
 * A server component shell, like the other screens: the explanation of what verifying a rule
 * actually does must render even if the client bundle fails, because it is the part a reviewer has
 * to have read before they start clicking. Only the queue below is interactive.
 *
 * There is no `SyntheticDataBanner` here, and its absence is deliberate rather than an oversight:
 * this screen holds no invoice and no patient data at all. It shows the GOÄ's own published text
 * and the rule table the engine derived from it.
 */
export default function RulesPage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">GOÄ-Regeln prüfen</h1>
        <p className="text-muted-foreground text-sm">
          859 der 894 Regeln dieser Engine wurden automatisch aus dem Verordnungstext der GOÄ
          extrahiert. Sie setzen nichts durch: eine maschinell gelesene Regel darf keine
          berechnungsfähige Leistung unterdrücken, bevor ein Mensch sie geprüft hat.
        </p>
        <p className="text-muted-foreground text-sm">
          Genau das ist der Grund, warum eine{" "}
          <Link href="/padnext" className="underline">
            PADnext-Prüfung
          </Link>{" "}
          so viel in die Gruppe <strong>unbestätigt</strong> einordnet — das ist kein Vorwurf gegen
          eine Praxis, sondern die Grenze dessen, was die Engine belegen darf. Jede hier
          verifizierte Regel verschiebt diese Grenze und wirkt ab sofort auf alle folgenden
          Prüfungen.
        </p>
        <p className="text-muted-foreground text-sm">
          Die CSV-Dateien unter <span className="font-mono text-xs">data/rules/</span> werden dabei
          nicht verändert. Sie sind versionierte Quelldaten; Entscheidungen aus dieser Liste werden
          in der Datenbank gespeichert und beim Laden über die CSVs gelegt.
        </p>
      </header>

      <RuleReviewWorkbench />
    </main>
  )
}
