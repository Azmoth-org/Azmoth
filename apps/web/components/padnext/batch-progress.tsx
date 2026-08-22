"use client"

import { CircleAlertIcon, Loader2Icon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Card, CardContent } from "@workspace/ui/components/card"

import type { BatchAuditJob } from "@/lib/padnext/batch-types"

const STATUS_LABEL: Record<BatchAuditJob["status"], string> = {
  PENDING: "in der Warteschlange",
  PROCESSING: "wird geprüft",
  COMPLETED: "abgeschlossen",
  FAILED: "fehlgeschlagen",
}

/**
 * "45 von 100 geprüft", with a bar.
 *
 * The bar is sized by *file count*, not by money, and the label says so — unlike the coverage bar
 * on the dashboard, which is a share of euros. Two bars on one screen measuring different things
 * would be confusing enough without one of them being silent about which.
 */
export function BatchProgress({ job }: { job: BatchAuditJob }) {
  const total = job.file_count ?? 0
  const done = job.processed_file_count ?? 0
  const percent = total > 0 ? Math.min(100, (done / total) * 100) : 0
  const running = job.status === "PENDING" || job.status === "PROCESSING"

  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex items-center gap-2 text-sm font-medium">
            {running ? (
              <Loader2Icon className="size-4 animate-spin" aria-hidden />
            ) : (
              <CircleAlertIcon className="size-4 opacity-0" aria-hidden />
            )}
            {done} von {total} Dateien geprüft
          </span>
          <span className="text-muted-foreground font-mono text-xs">
            {job.batch_id} · {STATUS_LABEL[job.status]}
          </span>
        </div>

        <div
          className="bg-muted h-2 w-full overflow-hidden rounded-full"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          aria-label={`${done} von ${total} Dateien geprüft`}
        >
          <div
            className="bg-primary h-full transition-[width] duration-300"
            style={{ width: `${percent}%` }}
          />
        </div>

        <p className="text-muted-foreground text-xs">
          {job.completed_file_count} erfolgreich · {job.failed_file_count} fehlgeschlagen. Der
          Fortschritt zählt Dateien, nicht Beträge.
        </p>
      </CardContent>
    </Card>
  )
}

/**
 * Shown above a finished dashboard when some deliveries could not be read.
 *
 * Not a footnote. The roll-up below it speaks only for the files that were audited, so a reader
 * who does not know that two of a hundred failed would take the totals for the whole upload.
 */
export function FailedFilesNotice({ job }: { job: BatchAuditJob }) {
  if (!job.failed_file_count) return null

  const all = job.failed_file_count === job.file_count

  return (
    <Alert variant={all ? "destructive" : "default"}>
      <CircleAlertIcon />
      <AlertTitle>
        {job.failed_file_count} von {job.file_count} Dateien{" "}
        {job.failed_file_count === 1 ? "konnte" : "konnten"} nicht geprüft werden
      </AlertTitle>
      <AlertDescription>
        {all ? (
          <p>
            Keine der hochgeladenen Dateien war lesbar, daher enthält die Auswertung unten keine
            Beträge. Die Gründe stehen je Datei in der Tabelle.
          </p>
        ) : (
          <p>
            Die Auswertung unten umfasst nur die {job.completed_file_count} geprüften Dateien. Die
            übrigen sind in der Tabelle mit ihrem Fehler aufgeführt und gehen in keine Summe ein.
          </p>
        )}
      </AlertDescription>
    </Alert>
  )
}
