import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"

import { RuleReviewWorkbench } from "@/components/rules/review-workbench"
import { RULE_REVIEW_ENABLED } from "@/lib/features"

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
 *
 * ## Off unless the deployment asks for it
 *
 * This is our tooling, not a customer's. A pilot user who finds this screen reads it as an
 * invitation to correct the engine, and "the verdicts are not something you tune" is the
 * proposition the pilot is selling. So the screen is behind `RULE_REVIEW_ENABLED`, off by default,
 * and a deployment that has not opted in answers `404` — the same answer a path that was never
 * built gets, which is the right one for a screen this deployment does not have.
 *
 * `notFound()` and not a redirect: a redirect would say "this exists somewhere else", and it
 * doesn't. The nav entry is filtered out by the same flag in `components/layout/nav.ts`, so with
 * the flag off there is nothing to click; this is what closes the typed URL. Both are needed —
 * `lib/features.ts` explains why neither is an access control.
 */
export default function RulesPage() {
  if (!RULE_REVIEW_ENABLED) notFound()

  return (
    <>
      <header className="space-y-1">
        <h1 className="text-display-md">
          GOÄ-Regeln prüfen
        </h1>
        <p className="text-sm text-muted-foreground">
          Die meisten Regeln dieser Engine wurden automatisch aus dem
          Verordnungstext der GOÄ extrahiert. Eine ungeprüfte Regel setzt nichts
          durch: sie darf keine berechnungsfähige Leistung unterdrücken, bevor
          ein Mensch sie bestätigt hat. Der aktuelle Stand steht in der
          Fortschrittsleiste darunter.
        </p>
        <p className="text-sm text-muted-foreground">
          Genau das ist der Grund, warum eine{" "}
          <Link href="/padnext" className="underline">
            PADnext-Prüfung
          </Link>{" "}
          so viel in die Gruppe <strong>unbestätigt</strong> einordnet — das ist
          kein Vorwurf gegen eine Praxis, sondern die Grenze dessen, was die
          Engine belegen darf. Jede hier verifizierte Regel verschiebt diese
          Grenze und wirkt ab sofort auf alle folgenden Prüfungen.
        </p>
        <p className="text-sm text-muted-foreground">
          Die CSV-Dateien unter{" "}
          <span className="font-mono text-xs">data/rules/</span> werden dabei
          nicht verändert. Sie sind versionierte Quelldaten; Entscheidungen aus
          dieser Liste werden in der Datenbank gespeichert und beim Laden über
          die CSVs gelegt.
        </p>
      </header>

      <RuleReviewWorkbench />
    </>
  )
}
