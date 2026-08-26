import type { Metadata } from "next"
import { Suspense } from "react"

import {
  BATCH_COLUMNS,
  BATCH_STATUS_VALUES,
  BatchHistoryTable,
} from "@/components/batches/batch-history-table"
import { Breadcrumbs } from "@/components/layout/breadcrumbs"
import { TableSkeleton } from "@/components/lists/table-states"
import { readListParams, type RawSearchParams } from "@/lib/lists/params"

export const metadata: Metadata = {
  title: "Stapel-Historie",
  description:
    "Alle gespeicherten PADnext-Stapelprüfungen, filterbar nach Status. Nur synthetische Daten.",
}

export const dynamic = "force-dynamic"

/**
 * `/padnext/batch/history` — every batch run the database holds.
 *
 * A sibling route under `/padnext/batch` rather than a `?view=history` on the upload screen, so the
 * upload workbench stays what it is and the history has its own shareable URL. `activeHref` needs no
 * change for it: it resolves the *longest* matching nav href, so this path highlights Stapel-Historie
 * and not Stapelprüfung, which is the whole reason that function does a longest match.
 *
 * The reason this page exists at all is durability. A `batch_id` is issued once, in the `202`, and the
 * browser holds it in memory — so a reload used to orphan a finished batch whose roll-up was still in
 * Postgres. It is also where a run the engine's startup recovery closed is findable: `?status=FAILED`
 * is one link, and those rows carry "Interrupted by server restart" in their message.
 */
export default async function BatchHistoryPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>
}) {
  const raw = await searchParams
  const params = readListParams(raw, { statuses: BATCH_STATUS_VALUES })

  return (
    <>
      <Breadcrumbs
        trail={[
          { label: "Übersicht", href: "/" },
          { label: "Stapelprüfung", href: "/padnext/batch" },
          { label: "Stapel-Historie" },
        ]}
      />

      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Stapel-Historie</h1>
        <p className="text-muted-foreground max-w-3xl text-sm">
          Jede Stapelprüfung bleibt mit ihrer Zusammenfassung gespeichert, auch wenn die Stapel-ID im
          Browser längst verloren ist. Ein <strong>fehlgeschlagener</strong> Stapel hat keine
          Auswertung: entweder brach der Lauf ab, oder er wurde beim Neustart der Engine geschlossen —
          der Grund steht in der Statusspalte.
        </p>
      </header>

      <Suspense
        key={`${params.status ?? ""}|${params.page}`}
        fallback={<TableSkeleton columns={BATCH_COLUMNS} />}
      >
        <BatchHistoryTable params={params} />
      </Suspense>
    </>
  )
}
