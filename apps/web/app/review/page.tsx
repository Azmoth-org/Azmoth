import type { Metadata } from "next"

import { ReviewWorkbench } from "@/components/review/review-workbench"
import { SyntheticDataBanner } from "@/components/review/synthetic-data-banner"

export const metadata: Metadata = {
  title: "GOÄ-Prüfung — Entwurf",
  description:
    "Ärztliche Prüfung eines deterministisch erzeugten GOÄ-Abrechnungsvorschlags. Nur synthetische Daten.",
}

/**
 * `/review` — the human approval boundary.
 *
 * A server component shell: the banner is static and must render even if the client bundle fails,
 * and the workbench below it is the only interactive part.
 */
export default function ReviewPage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">GOÄ-Abrechnungsvorschlag prüfen</h1>
        <p className="text-muted-foreground text-sm">
          Deterministische Kodierung: Datalog entscheidet, was sicher berechnungsfähig ist, ASP löst
          die verbleibenden Wahlmöglichkeiten, eine unabhängige Validierung rechnet nach. Jede Position
          trägt einen Beweisbaum.
        </p>
      </header>

      <SyntheticDataBanner />
      <ReviewWorkbench />
    </main>
  )
}
