import type { Metadata } from "next"
import { Suspense } from "react"

import { Breadcrumbs } from "@/components/layout/breadcrumbs"
import { TableSkeleton } from "@/components/lists/table-states"
import {
  PROPOSAL_COLUMNS,
  PROPOSAL_STATUS_VALUES,
  ProposalsTable,
} from "@/components/proposals/proposals-table"
import { readListParams, type RawSearchParams } from "@/lib/lists/params"

export const metadata: Metadata = {
  title: "Alle Prüfungen",
  description:
    "Alle gespeicherten GOÄ-Abrechnungsvorschläge, filterbar nach Status und Fall-ID. Nur synthetische Daten.",
}

/**
 * Rendered per request, never prerendered.
 *
 * The rows are live, and `next build` runs inside `docker build` where no engine exists — a
 * statically generated list would either fail the image build or bake in "Engine nicht erreichbar"
 * and serve it forever. The same reason the dashboard is dynamic.
 */
export const dynamic = "force-dynamic"

/**
 * `/proposals` — every billing draft the database holds.
 *
 * This is the screen the durable store was for. An approval survives a restart, and until now
 * nothing in the UI could find one afterwards: the dashboard shows the newest five, and before that
 * the only route back to a record was an id a reader still happened to have in a scrollback.
 *
 * **The filter state lives in the URL, not in React.** `?status=REJECTED&page=2` is the whole state
 * of this page, which makes a filtered list a link somebody can paste into a ticket, and makes the
 * back button work. It also keeps the fetch on the server: `searchParams` comes in, `callEngine` runs
 * server-side, and `ENGINE_BASE_URL` never reaches the browser. The only client code on this screen
 * is the toolbar that pushes a new URL. See `lib/lists/params.ts`.
 *
 * `searchParams` is a promise in this Next version, and awaiting it is what makes the page dynamic in
 * the first place. It is awaited here and passed down as a plain value so nothing below has to know
 * that.
 *
 * The table is inside `Suspense` with a keyed fallback, so changing a filter re-suspends and shows
 * the skeleton rather than leaving the previous page's rows on screen looking current.
 */
export default async function ProposalsPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>
}) {
  const raw = await searchParams
  const params = readListParams(raw, { statuses: PROPOSAL_STATUS_VALUES })

  return (
    <>
      <Breadcrumbs
        trail={[{ label: "Übersicht", href: "/" }, { label: "Alle Prüfungen" }]}
      />

      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Alle Prüfungen
        </h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Jeder erzeugte Abrechnungsvorschlag bleibt dauerhaft gespeichert, mit
          seinem Status, dem Zeitpunkt und dem Receipt-Hash über Katalog,
          Regeltabellen, Logikprogramme, Solver-Versionen und Eingabe.{" "}
          <strong>Ein Entwurf ist keine Rechnung</strong> — nur ein
          freigegebener Vorschlag ist von einer namentlich benannten Person
          verantwortet.
        </p>
      </header>

      {/*
        Keyed on the filters, so a new query string re-mounts the boundary and the skeleton appears.
        Without the key React would keep the resolved subtree mounted and the old rows would sit
        there, un-greyed, until the new fetch returned — which reads as "these are the results".
      */}
      <Suspense
        key={`${params.status ?? ""}|${params.query ?? ""}|${params.page}`}
        fallback={<TableSkeleton columns={PROPOSAL_COLUMNS} />}
      >
        <ProposalsTable params={params} />
      </Suspense>
    </>
  )
}
