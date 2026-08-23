"use client"

import { DownloadIcon, LayersIcon, Loader2Icon } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"

import { CopyableHash } from "@/components/common/copyable-hash"
import { BatchDropzone } from "@/components/padnext/batch-dropzone"
import { BatchFilesTable } from "@/components/padnext/batch-files-table"
import { BatchProgress, FailedFilesNotice } from "@/components/padnext/batch-progress"
import { BucketBoard, type BucketCounts } from "@/components/padnext/bucket-summary"
import { ErrorPanel } from "@/components/review/error-panel"
import { downloadBatchExport } from "@/lib/download"
import {
  POLL_INTERVAL_MS,
  POLL_TIMEOUT_MS,
  fetchBatch,
  uploadBatch,
} from "@/lib/padnext/batch-client"
import {
  hasBucketFields,
  isTerminal,
  type BatchAuditJob,
  type ReviewError,
} from "@/lib/padnext/batch-types"

/**
 * The aggregate's position counts, in the shape the shared bucket cards want.
 *
 * Counting, not arithmetic on money: the engine sends these as integers precisely so the screen
 * does not have to walk a hundred reports to find out how many positions landed where.
 */
function aggregateCounts(summary: {
  confirmed_wrong_positions?: number
  confirmed_fine_positions?: number
  unconfirmed_positions?: number
}): BucketCounts {
  return {
    confirmed_wrong: summary.confirmed_wrong_positions ?? 0,
    confirmed_fine: summary.confirmed_fine_positions ?? 0,
    unconfirmed: summary.unconfirmed_positions ?? 0,
  }
}

/**
 * Download the finished batch as CSVs.
 *
 * Read-only, unlike the single-proposal export: it changes no status and can be taken as often as
 * the reader likes, so there is no dialog and no name to collect. The reason for the difference is
 * that a proposal export records a decision a person took, while this renders a computation that
 * already finished — see the engine route.
 *
 * The reassurance below the button matters more than it looks. A browser download is silent, and
 * the archive contains four files whose relationship is not obvious from a filename, so the button
 * says what will land before it is pressed and which file arrived afterwards.
 */
function BatchExport({ job }: { job: BatchAuditJob }) {
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [failure, setFailure] = useState<ReviewError | null>(null)

  async function download() {
    setPending(true)
    setFailure(null)
    const result = await downloadBatchExport(job.batch_id)
    if (result.kind === "error") {
      setFailure(result.error)
    } else {
      setSaved(result.filename)
    }
    setPending(false)
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 pt-6">
          <Button variant="outline" onClick={() => void download()} disabled={pending}>
            {pending ? (
              <>
                <Loader2Icon className="animate-spin" aria-hidden />
                Export wird erstellt…
              </>
            ) : (
              <>
                <DownloadIcon aria-hidden />
                Als CSV exportieren
              </>
            )}
          </Button>
          <div className="text-muted-foreground min-w-0 text-xs">
            {saved ? (
              <span>
                Heruntergeladen: <span className="font-mono break-all">{saved}</span>
              </span>
            ) : (
              <span>
                ZIP mit <span className="font-mono">batch_summary.csv</span>,{" "}
                <span className="font-mono">batch_line_items.csv</span>,{" "}
                <span className="font-mono">batch_files.csv</span> und einer{" "}
                <span className="font-mono">README.txt</span>, die die drei Bewertungsgruppen
                erklärt.
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {failure ? <ErrorPanel error={failure} /> : null}
    </div>
  )
}

function Provenance({ job }: { job: BatchAuditJob }) {
  const first = job.files?.find((file) => file.report)?.report
  return (
    <Card>
      <CardContent className="grid grid-cols-2 gap-x-6 gap-y-2 pt-6 text-xs sm:grid-cols-4">
        <div className="min-w-0">
          <div className="text-muted-foreground">Stapel</div>
          {/* Copyable: this id is how the batch is found again after a reload, via the listing
              endpoint or GET /api/v1/padnext/batch/{id}. */}
          <CopyableHash value={job.batch_id} length={32} label="Stapel-ID" />
        </div>
        <div>
          <div className="text-muted-foreground">Dateien</div>
          <div className="font-mono tabular-nums">
            {job.completed_file_count} geprüft / {job.file_count}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">Positionen</div>
          <div className="font-mono tabular-nums">
            {job.aggregate_summary?.position_count ?? 0}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">Katalog</div>
          {/* Taken from a report rather than from the job: catalog identity belongs to the audit,
              and every file in a batch is audited by the same process against the same catalog. */}
          <div className="font-mono break-all">{first?.catalog_version || "—"}</div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Upload a stack of PADnext deliveries, watch them being audited, and read the systemic result.
 *
 * The polling is a `setTimeout` chain rather than a `setInterval`, so a slow response cannot make
 * requests pile up on each other, and a `cancelled` flag rather than an `AbortController` because
 * what has to stop is the *loop*, not one request. Both the terminal status and `POLL_TIMEOUT_MS`
 * end it — the second matters because the engine's `BackgroundTasks` do not survive a restart, so a
 * job really can stay `PROCESSING` forever and the browser must not spin on it.
 */
export function BatchWorkbench() {
  const [job, setJob] = useState<BatchAuditJob | null>(null)
  const [error, setError] = useState<ReviewError | null>(null)
  const [uploading, setUploading] = useState(false)
  const [stalled, setStalled] = useState(false)

  // Held in a ref so the effect that owns the timer is not restarted by every poll's state update.
  const batchIdRef = useRef<string | null>(null)
  const [batchId, setBatchId] = useState<string | null>(null)

  const onSubmit = useCallback(async (files: File[]) => {
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    setJob(null)
    setStalled(false)
    try {
      const result = await uploadBatch(files)
      if (result.kind === "error") {
        setError(result.error)
        setBatchId(null)
        batchIdRef.current = null
        return
      }
      batchIdRef.current = result.accepted.batch_id
      setBatchId(result.accepted.batch_id)
    } finally {
      setUploading(false)
    }
  }, [])

  useEffect(() => {
    if (!batchId) return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const startedAt = Date.now()

    async function tick() {
      if (cancelled || !batchId) return

      const result = await fetchBatch(batchId)
      if (cancelled) return

      if (result.kind === "error") {
        // A single failed poll is not a failed batch — the job is still running on the engine — so
        // the error is shown and the loop keeps going rather than abandoning a job the user cannot
        // then get back to.
        setError(result.error)
      } else {
        setError(null)
        setJob(result.job)
        if (isTerminal(result.job.status)) return
      }

      if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
        setStalled(true)
        return
      }
      timer = setTimeout(() => void tick(), POLL_INTERVAL_MS)
    }

    void tick()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [batchId])

  const summary = job?.aggregate_summary
  const done = job !== null && isTerminal(job.status)

  return (
    <div className="space-y-6">
      <BatchDropzone onSubmit={(files) => void onSubmit(files)} pending={uploading} />

      {error ? <ErrorPanel error={error} /> : null}

      {job ? <BatchProgress job={job} /> : null}

      {stalled ? (
        <Alert variant="destructive">
          <AlertTitle>Der Stapel antwortet nicht mehr</AlertTitle>
          <AlertDescription>
            Seit {POLL_TIMEOUT_MS / 60000} Minuten hat sich der Status nicht auf abgeschlossen
            geändert. Die Engine verarbeitet Stapel in einem FastAPI-BackgroundTask, der einen
            Neustart nicht überlebt — ein unterbrochener Lauf bleibt dauerhaft auf{" "}
            <span className="font-mono">PROCESSING</span> stehen. Die Dateien bitte erneut
            hochladen.
          </AlertDescription>
        </Alert>
      ) : null}

      {job?.status === "FAILED" ? (
        <Alert variant="destructive">
          <AlertTitle>Die Stapelverarbeitung ist fehlgeschlagen</AlertTitle>
          <AlertDescription className="space-y-2">
            <p className="font-mono text-xs break-all">
              {job.error_message ?? "Kein Grund angegeben."}
            </p>
            <p>
              Es wird bewusst <strong>keine</strong> Auswertung angezeigt: eine Summe über Dateien,
              die möglicherweise nie geschrieben wurden, wäre schlechter als gar keine.
            </p>
          </AlertDescription>
        </Alert>
      ) : null}

      {done && job.status === "COMPLETED" ? (
        <>
          <FailedFilesNotice job={job} />

          {summary && hasBucketFields(summary) ? (
            <BucketBoard
              figures={summary}
              counts={aggregateCounts(summary)}
              heading="Systemische Bewertung über alle Rechnungen"
              headingId="batch-buckets-heading"
              totalLabel="berechnet über alle geprüften Dateien"
            />
          ) : (
            <Alert variant="destructive">
              <AlertTitle>Die Auswertung enthält nicht die drei Bewertungsgruppen</AlertTitle>
              <AlertDescription>
                Der Stapel ist abgeschlossen, aber die Zusammenfassung trägt nicht die Felder
                confirmed_fine / confirmed_wrong / unconfirmed. Vermutlich laufen Engine und UI auf
                verschiedenen Contract-Versionen — packages/contracts neu generieren.
              </AlertDescription>
            </Alert>
          )}

          <Provenance job={job} />
          <BatchExport job={job} />
          <BatchFilesTable job={job} />
        </>
      ) : null}

      {job === null && !uploading && error === null ? (
        <Alert>
          <LayersIcon />
          <AlertTitle>Noch kein Stapel geprüft</AlertTitle>
          <AlertDescription>
            Eine einzelne Rechnung beantwortet die Frage „ist diese Rechnung haltbar?“. Ein Stapel
            beantwortet die teurere: „ist unsere Abrechnung systematisch falsch, und wo?“ Die
            Auswertung trennt dabei dieselben drei Gruppen wie die Einzelprüfung — die mittlere
            Spalte ist die Grenze unserer Regelabdeckung, nicht ein Vorwurf gegen die Praxis.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
