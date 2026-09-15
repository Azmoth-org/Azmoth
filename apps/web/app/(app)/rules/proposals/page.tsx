import type { Metadata } from "next"
import { DownloadIcon } from "lucide-react"
import { Suspense } from "react"

import { buttonVariants } from "@workspace/ui/components/button"
import { cn } from "@workspace/ui/lib/utils"

import { Breadcrumbs } from "@/components/layout/breadcrumbs"
import { TableSkeleton } from "@/components/lists/table-states"
import {
  RULE_PROPOSAL_COLUMNS,
  RuleProposalsTable,
} from "@/components/rules/rule-proposals-table"
import { readListParams, type RawSearchParams } from "@/lib/lists/params"

export const metadata: Metadata = {
  title: "Ziffer-Meldungen",
  description:
    "Alle Meldungen aus „Regel fehlt? Ziffer melden“ der eigenen Organisation, mit CSV-Export.",
}

/**
 * Rendered per request, never prerendered — the rows are live, the same reason `/proposals` is.
 */
export const dynamic = "force-dynamic"

/**
 * `/rules/proposals` — every `Regel fehlt? Ziffer melden` report this organisation has filed.
 *
 * The button that opens that dialog is on every audit report, and until now what it produced was a
 * write nobody could read back: a report landed in `rule_proposals` and then only direct database
 * access could say what had accumulated. This is the read side — paged, and exportable as one CSV
 * for whoever compiles the backlog into the next batch of rules to verify.
 *
 * No status and no filter. A report is a data point, not a ticket with a state — see the engine's
 * `app.schemas.rule_proposals` module docstring — so the only control this screen needs is paging.
 */
export default async function RuleProposalsPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>
}) {
  const raw = await searchParams
  const params = readListParams(raw, { statuses: [] })

  return (
    <>
      <Breadcrumbs
        trail={[{ label: "Übersicht", href: "/" }, { label: "Ziffer-Meldungen" }]}
      />

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-display-md">Ziffer-Meldungen</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Jede Meldung über „Regel fehlt? Ziffer melden“ bleibt hier auffindbar
            — mit der gemeldeten Ziffer, der Anmerkung und, sofern vorhanden,
            dem Receipt-Hash des Prüfberichts. Eine Meldung ist ein Hinweis für
            die nächste Regelprüfung, keine Entscheidung und kein Vorwurf.
          </p>
        </div>
        <a
          href="/api/engine/rules/proposals/export"
          className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
        >
          <DownloadIcon aria-hidden />
          Als CSV exportieren
        </a>
      </header>

      <Suspense
        key={params.page}
        fallback={<TableSkeleton columns={RULE_PROPOSAL_COLUMNS} />}
      >
        <RuleProposalsTable params={params} />
      </Suspense>
    </>
  )
}
