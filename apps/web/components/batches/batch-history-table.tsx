import Link from "next/link"

import { Badge } from "@workspace/ui/components/badge"
import { buttonVariants } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"
import { cn } from "@workspace/ui/lib/utils"

import { CopyableHash } from "@/components/common/copyable-hash"
import { ListToolbar, type StatusOption } from "@/components/lists/list-toolbar"
import { Pagination } from "@/components/lists/pagination"
import {
  LoadFailed,
  NoMatches,
  NoRecords,
  PageOutOfRange,
} from "@/components/lists/table-states"
import { callEngine } from "@/lib/engine"
import { engineQuery, nextHref, pageCount, type ListParams } from "@/lib/lists/params"
import { isBatchAuditJobList, totalOrPageLength } from "@/lib/dashboard/types"
import { BATCH_STATUS, statusPresentation } from "@/lib/status"
import { timestamp } from "@/lib/review/format"

export const BATCH_HISTORY_PATH = "/padnext/batch/history"

export const BATCH_COLUMNS = ["Stapel", "Status", "Dateien", "Erstellt", ""] as const

const STATUS_OPTIONS: readonly StatusOption[] = [
  { value: null, label: "Alle Status" },
  { value: "PENDING", label: "In Warteschlange" },
  { value: "PROCESSING", label: "Wird geprüft" },
  { value: "COMPLETED", label: "Abgeschlossen" },
  { value: "FAILED", label: "Fehlgeschlagen" },
]

export const BATCH_STATUS_VALUES = ["PENDING", "PROCESSING", "COMPLETED", "FAILED"] as const

/**
 * Every batch run this database holds, filtered by status and paged.
 *
 * **This is the page the batch listing endpoint was built for.** A `batch_id` is issued once, in the
 * `202`, and the browser holds it in memory — so before the listing existed, a page reload orphaned a
 * finished batch whose roll-up was still sitting in Postgres with nothing able to ask for it. The
 * dashboard card shows the newest five; this is the whole table.
 *
 * It is also where a run the engine's startup recovery closed becomes findable rather than merely
 * visible: `?status=FAILED` is one link, and `error_message` on those rows reads "Interrupted by
 * server restart". That is the query an operator has after a deploy, and it is why the status filter
 * matters more here than the count of rows does.
 *
 * **No search box.** The engine's batch listing filters on `status` and `created_after`; there is no
 * text column to match, and a field that accepted a batch id and silently ignored it would be worse
 * than no field. `created_after` is deliberately not surfaced either — a date picker is a control
 * with real design questions (timezone, inclusive-or-not, presets) and this page does not need one to
 * do its job. Both are noted as follow-ups rather than half-built.
 *
 * The "Dateien" column shows progress while a run is unfinished, because `file_count` alone says
 * nothing about how far a `PROCESSING` batch got — and those counts come from `batch_files` rather
 * than from `aggregate_summary`, which is null on exactly the jobs whose progress a reader most wants.
 */
export async function BatchHistoryTable({ params }: { params: ListParams }) {
  const result = await callEngine(
    `/api/v1/padnext/batch?${engineQuery({ page: params.page, status: params.status })}`,
  )

  const toolbar = <ListToolbar params={params} statuses={STATUS_OPTIONS} />

  if (!result.ok) {
    return (
      <Shell toolbar={toolbar}>
        <LoadFailed
          headline="Stapelprüfungen konnten nicht geladen werden"
          message={result.failure.message}
        />
      </Shell>
    )
  }

  if (!isBatchAuditJobList(result.body)) {
    return (
      <Shell toolbar={toolbar}>
        <LoadFailed
          headline="Stapelprüfungen konnten nicht geladen werden"
          message="Die Engine hat auf GET /api/v1/padnext/batch keine Stapelliste geantwortet."
        />
      </Shell>
    )
  }

  const jobs = result.body.jobs ?? []
  const total = totalOrPageLength(result.body.total, jobs.length)
  const reset = nextHref(BATCH_HISTORY_PATH, params, { status: null, query: null, page: 1 })

  if (jobs.length === 0) {
    return (
      <Shell toolbar={toolbar}>
        {total > 0 ? (
          <PageOutOfRange
            firstPage={nextHref(BATCH_HISTORY_PATH, params, { page: 1 })}
            pages={pageCount(total)}
          />
        ) : params.status !== null ? (
          <NoMatches
            message="Kein Stapel in diesem Status"
            hint="Es gibt keine Stapelprüfung mit diesem Status."
            reset={reset}
          />
        ) : (
          <NoRecords
            message="Noch keine Stapelprüfungen vorhanden"
            hint={
              "Ein Stapel entsteht in der Stapelprüfung, aus mehreren PADnext-Lieferungen. Er " +
              "bleibt dauerhaft gespeichert und ist danach hier wiederzufinden."
            }
            action={{ href: "/padnext/batch", label: "Zur Stapelprüfung" }}
          />
        )}
        <Pagination
          pathname={BATCH_HISTORY_PATH}
          params={params}
          total={total}
          shown={jobs.length}
        />
      </Shell>
    )
  }

  return (
    <Shell toolbar={toolbar}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Stapel</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Dateien</TableHead>
            <TableHead>Erstellt</TableHead>
            <TableHead className="w-0">
              <span className="sr-only">Aktionen</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((job) => {
            const status = statusPresentation(BATCH_STATUS, job.status)
            const files = job.file_count ?? 0
            const processed = job.processed_file_count ?? 0
            const running = files > 0 && processed < files
            return (
              <TableRow key={job.batch_id}>
                <TableCell>
                  <CopyableHash value={job.batch_id} length={14} label="Stapel-ID" />
                </TableCell>
                <TableCell>
                  <div className="flex flex-col gap-1">
                    <Badge variant={status.variant} className={cn(status.className)}>
                      {status.label}
                    </Badge>
                    {/* The reason a batch failed, where an operator is already looking. On a run
                        the startup recovery closed this is the only place it is stated. */}
                    {job.error_message ? (
                      <span
                        className="text-muted-foreground max-w-56 truncate text-xs"
                        title={job.error_message}
                      >
                        {job.error_message}
                      </span>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell className="text-xs tabular-nums">
                  {running ? (
                    <span>
                      {processed} von {files} geprüft
                    </span>
                  ) : (
                    <span>{files}</span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground text-xs tabular-nums">
                  {timestamp(job.created_at)}
                </TableCell>
                <TableCell className="text-right">
                  <Link
                    href={`/padnext/batch?id=${encodeURIComponent(job.batch_id)}`}
                    className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
                  >
                    Ansehen
                  </Link>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>

      <Pagination
        pathname={BATCH_HISTORY_PATH}
        params={params}
        total={total}
        shown={jobs.length}
      />
    </Shell>
  )
}

function Shell({
  toolbar,
  children,
}: {
  toolbar: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        {toolbar}
        <div className="border-border border-t pt-2">{children}</div>
      </CardContent>
    </Card>
  )
}
