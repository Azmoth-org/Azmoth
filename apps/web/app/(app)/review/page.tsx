import type { Metadata } from "next"

import { ReviewWorkbench } from "@/components/review/review-workbench"
import { SyntheticDataBanner } from "@/components/review/synthetic-data-banner"
import { readDeepLinkId, type RawSearchParams } from "@/lib/deep-link"

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
 *
 * ## `?id=prop_…`
 *
 * The dashboard's "Letzte Prüfungen" card and every row of `/proposals` link here with an id. The
 * parameter is read here and handed down as a plain string; the fetch itself happens in the
 * workbench, through the `/api/engine` proxy every other call on this screen already uses. Reading
 * it here rather than with `useSearchParams()` in the client keeps this page free of a `Suspense`
 * boundary whose only job would be to satisfy the hook, and matches how `/proposals` reads its own
 * filters.
 *
 * Awaiting `searchParams` is what makes this page dynamic, which is correct — the rendered screen
 * depends on the URL. Unlike `/proposals` it needs no `force-dynamic`, because nothing is fetched
 * from the engine during the render: `next build` inside `docker build` has no engine to reach and
 * nothing here tries to.
 *
 * **A visit without the parameter is untouched.** `deepLinkId` is `null`, the workbench renders its
 * case selector and its existing empty state, and nothing about that path changed.
 */
export default async function ReviewPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>
}) {
  const deepLinkId = readDeepLinkId(await searchParams)

  return (
    <>
      <header className="space-y-1">
        <h1 className="text-display-md">
          GOÄ-Abrechnungsvorschlag prüfen
        </h1>
        <p className="text-sm text-muted-foreground">
          Deterministische Kodierung: eine deterministische Regel-Engine
          entscheidet, was sicher berechnungsfähig ist, ein mathematischer
          Solver löst die verbleibenden Wahlmöglichkeiten, eine unabhängige
          Validierung rechnet nach. Jede Position trägt einen
          Beweisbaum.
        </p>
      </header>

      <SyntheticDataBanner />
      <ReviewWorkbench deepLinkId={deepLinkId} />
    </>
  )
}
