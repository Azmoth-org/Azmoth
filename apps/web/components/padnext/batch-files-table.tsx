"use client"

import {
  ChevronDownIcon,
  ChevronRightIcon,
  CircleAlertIcon,
  CircleCheckIcon,
  CircleSlashIcon,
  ClockIcon,
} from "lucide-react"
import { useState } from "react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import { FindingsPanel } from "@/components/padnext/findings-panel"
import { PositionsTable } from "@/components/padnext/positions-table"
import { BUCKET_TONE_CLASS, eur, percent } from "@/lib/padnext/format"
import type { BatchAuditJob, BatchFileResult } from "@/lib/padnext/batch-types"

const STATUS_BADGE: Record<
  BatchFileResult["status"],
  { label: string; icon: typeof CircleCheckIcon; className: string }
> = {
  COMPLETED: { label: "geprüft", icon: CircleCheckIcon, className: BUCKET_TONE_CLASS.fine.badge },
  FAILED: { label: "nicht lesbar", icon: CircleSlashIcon, className: BUCKET_TONE_CLASS.wrong.badge },
  PENDING: { label: "ausstehend", icon: ClockIcon, className: BUCKET_TONE_CLASS.unknown.badge },
}

function StatusBadge({ status }: { status: BatchFileResult["status"] }) {
  const presentation = STATUS_BADGE[status]
  const Icon = presentation.icon
  return (
    <Badge className={presentation.className}>
      <Icon aria-hidden />
      {presentation.label}
    </Badge>
  )
}

/**
 * The expanded detail for one file: the same tables the single-file screen renders.
 *
 * Reused rather than reimplemented, and that is the point of the batch report storing the full
 * `PadnextAuditReport` per file: a reviewer who clicks into the riskiest invoice sees exactly the
 * positions, verdicts, rule ids and findings they would have seen had they audited that file on its
 * own. `BucketSummary` is deliberately *not* repeated here — the three cards are already at the top
 * of the page for the whole batch, and a second set inside every row would drown them.
 */
function FileDetail({ file }: { file: BatchFileResult }) {
  if (file.status === "FAILED") {
    return (
      <div className="space-y-2 py-2">
        <p className="text-sm font-medium">Diese Datei konnte nicht geprüft werden.</p>
        <p className="text-muted-foreground font-mono text-xs break-all">
          {file.error_message ?? "Kein Grund angegeben."}
        </p>
        <p className="text-muted-foreground text-xs">
          Sie geht in keine der Summen oben ein. Eine nicht lesbare Datei ist kein Befund gegen die
          Praxis.
        </p>
      </div>
    )
  }

  if (!file.report) {
    return (
      <p className="text-muted-foreground py-2 text-sm">
        Für diese Datei liegt noch kein Bericht vor.
      </p>
    )
  }

  return (
    <div className="space-y-6 py-2">
      <PositionsTable report={file.report} />
      <FindingsPanel report={file.report} />
    </div>
  )
}

/**
 * Every uploaded file, riskiest first.
 *
 * The order comes from the engine. The web app is forbidden from doing arithmetic on money
 * (`CONTRIBUTING.md`, hard rule 3) — the amounts are exact decimal strings so that a JavaScript
 * client cannot round them — so sorting a column of euros here would mean parsing them into floats,
 * which is exactly what that rule prohibits. `GET /padnext/batch/{id}` returns the list already
 * sorted by `confirmed_wrong_eur` descending, and this table renders it in the order given.
 */
export function BatchFilesTable({ job }: { job: BatchAuditJob }) {
  const [expanded, setExpanded] = useState<number | null>(null)
  const files = job.files ?? []

  return (
    <section className="space-y-4" aria-labelledby="batch-files-heading">
      <div className="space-y-1">
        <h2 id="batch-files-heading" className="text-lg font-semibold tracking-tight">
          Dateien ({files.length})
        </h2>
        <p className="text-muted-foreground text-sm">
          Sortiert nach <strong>nachweislich falsch</strong>, absteigend — die Rechnungen mit dem
          größten belastbaren Befund zuerst. Eine Zeile anklicken zeigt die Einzelprüfung.
        </p>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" />
            <TableHead>Datei</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">berechnet</TableHead>
            <TableHead className="text-right">nachweislich falsch</TableHead>
            <TableHead className="text-right">bestätigt korrekt</TableHead>
            <TableHead className="text-right">unbestätigt</TableHead>
            <TableHead className="text-right">Abdeckung</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {files.map((file, index) => {
            const open = expanded === index
            const report = file.report
            return [
              <TableRow
                key={`row-${index}`}
                className="hover:bg-muted/50 cursor-pointer"
                onClick={() => setExpanded(open ? null : index)}
              >
                <TableCell>
                  <button
                    type="button"
                    aria-expanded={open}
                    aria-label={open ? `${file.filename} einklappen` : `${file.filename} aufklappen`}
                    className="text-muted-foreground"
                    onClick={(event) => {
                      event.stopPropagation()
                      setExpanded(open ? null : index)
                    }}
                  >
                    {open ? (
                      <ChevronDownIcon className="size-4" aria-hidden />
                    ) : (
                      <ChevronRightIcon className="size-4" aria-hidden />
                    )}
                  </button>
                </TableCell>
                <TableCell className="max-w-xs truncate font-mono text-xs">
                  {file.filename}
                </TableCell>
                <TableCell>
                  <StatusBadge status={file.status} />
                </TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {eur(report?.claimed_total_eur)}
                </TableCell>
                <TableCell
                  className={`text-right font-mono text-xs tabular-nums ${
                    report ? BUCKET_TONE_CLASS.wrong.text : ""
                  }`}
                >
                  {eur(report?.confirmed_wrong_eur)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {eur(report?.confirmed_fine_eur)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {eur(report?.unconfirmed_eur)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {report ? percent(report.coverage_ratio) : "—"}
                </TableCell>
              </TableRow>,
              open ? (
                <TableRow key={`detail-${index}`} className="hover:bg-transparent">
                  {/* `max-w-0` stops the nested audit tables from setting this table's width.
                      Without it, opening a row makes the summary columns above scroll sideways out
                      of view; with it the detail's own container scrolls instead — which is what
                      should happen, since the detail is the wide thing. */}
                  <TableCell colSpan={8} className="bg-muted/30 max-w-0">
                    <FileDetail file={file} />
                  </TableCell>
                </TableRow>
              ) : null,
            ]
          })}
        </TableBody>
      </Table>

      {files.some((file) => file.status === "FAILED") ? (
        <p className="text-muted-foreground flex items-start gap-2 text-xs">
          <CircleAlertIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          Nicht lesbare Dateien stehen am Ende und tragen zu keiner Summe bei — sie haben keinen
          Risikowert, nach dem sie einsortiert werden könnten.
        </p>
      ) : null}
    </section>
  )
}
