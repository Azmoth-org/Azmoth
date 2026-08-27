"use client"

import { DownloadIcon, LayersIcon, Loader2Icon } from "lucide-react"
import { useRouter } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"
import { Skeleton } from "@workspace/ui/components/skeleton"

import { CopyableHash } from "@/components/common/copyable-hash"
import { BatchDropzone } from "@/components/padnext/batch-dropzone"
import { BatchFilesTable } from "@/components/padnext/batch-files-table"
import {
  BatchProgress,
  FailedFilesNotice,
} from "@/components/padnext/batch-progress"
import {
  BucketBoard,
  type BucketCounts,
} from "@/components/padnext/bucket-summary"
import { ErrorPanel } from "@/components/review/error-panel"
import {
  isRetryable,
  isWellFormedId,
  malformedIdError,
  toDeepLinkError,
} from "@/lib/deep-link"
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
          <Button
            variant="outline"
            onClick={() => void download()}
            disabled={pending}
          >
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
          <div className="min-w-0 text-xs text-muted-foreground">
            {saved ? (
              <span>
                Heruntergeladen:{" "}
                <span className="font-mono break-all">{saved}</span>
              </span>
            ) : (
              <span>
                ZIP mit <span className="font-mono">batch_summary.csv</span>,{" "}
                <span className="font-mono">batch_line_items.csv</span>,{" "}
                <span className="font-mono">batch_files.csv</span> und einer{" "}
                <span className="font-mono">README.txt</span>, die die drei
                Bewertungsgruppen erklärt.
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
          <div className="font-mono break-all">
            {first?.catalog_version || "—"}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * What a deep-linked batch looks like while its first poll is in flight.
 *
 * Bars only, and no counter shape: this screen renders euro figures per bucket, and a placeholder a
 * reader could take for a rendered `0,00 €` is the one thing a loading state must never draw.
 */
function BatchSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <span className="sr-only" role="status">
          Stapelprüfung wird geladen …
        </span>
        <Skeleton className="h-5 w-56" />
        <Skeleton className="h-2 w-full" />
        <div className="grid gap-3 sm:grid-cols-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
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
 *
 * ## `deepLinkId` — arriving at a batch that already exists
 *
 * `/padnext/batch?id=batch_…` is what the dashboard's "Letzte Stapelprüfungen" card and every row of
 * the Stapel-Historie link to. It needs almost nothing new here: an id is exactly what this
 * component already holds after an upload, so a deep link seeds `batchId` and the existing poll
 * picks it up. A run that is still `PROCESSING` therefore keeps updating on the same two-second
 * tick as one that was uploaded in this tab — which is the point of linking to it at all.
 *
 * The **poll had to learn to stop**, though. A failed poll used to be treated as transient on the
 * grounds that the job is still running on the engine, which is right for a batch this tab uploaded
 * and wrong for one it was linked to: a `404` from a mistyped id is a permanent answer, and the old
 * loop would have asked for it every two seconds for fifteen minutes. See the poll effect below.
 */
export function BatchWorkbench({
  deepLinkId = null,
}: {
  deepLinkId?: string | null
}) {
  const [job, setJob] = useState<BatchAuditJob | null>(null)
  const [error, setError] = useState<ReviewError | null>(null)
  const [uploading, setUploading] = useState(false)
  const [stalled, setStalled] = useState(false)

  const router = useRouter()

  /**
   * A link whose id cannot be one this engine issued, refused without a request.
   *
   * Derived rather than stored, for the same reason as on the review screen: it is a pure function
   * of the URL, and holding it in state would need an effect to keep the two in step — a
   * synchronous `setState` in an effect body, which is a cascading render and a lint warning.
   */
  const malformedError = useMemo(
    () =>
      deepLinkId !== null && !isWellFormedId("batch", deepLinkId)
        ? malformedIdError("batch", deepLinkId)
        : null,
    [deepLinkId]
  )

  // Held in a ref so the effect that owns the timer is not restarted by every poll's state update.
  const batchIdRef = useRef<string | null>(null)
  // Seeded from the link. That is the whole of the deep-link mechanism on this screen: an id is
  // already what this component holds after an upload, so the existing poll picks it up and a run
  // still in `PROCESSING` keeps ticking exactly as one uploaded in this tab does.
  const [batchId, setBatchId] = useState<string | null>(
    deepLinkId !== null && isWellFormedId("batch", deepLinkId)
      ? deepLinkId
      : null
  )
  // Bumped by "Erneut versuchen"; part of the request key, so a retry restarts the poll.
  const [reloads, setReloads] = useState(0)
  // The request whose first poll has already answered, as `<id>#<attempt>`. Written only after an
  // `await`, and compared against the current one to derive the loading state.
  const [resolvedRequest, setResolvedRequest] = useState<string | null>(null)

  const request = batchId !== null ? `${batchId}#${reloads}` : null
  const loading = request !== null && resolvedRequest !== request
  // A malformed link outranks the last poll's error: it is why no poll was started.
  const shownError = malformedError ?? error

  const onSubmit = useCallback(
    async (files: File[]) => {
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
        // The address bar still names the batch this tab was linked to, which is no longer what the
        // screen shows. Dropped for the same reason as on the review screen: a reload would
        // otherwise swap the reader back to the old run.
        if (deepLinkId !== null)
          router.replace("/padnext/batch", { scroll: false })
      } finally {
        setUploading(false)
      }
    },
    [deepLinkId, router]
  )

  useEffect(() => {
    if (batchId === null || request === null) return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const startedAt = Date.now()
    // Only a deep link can point at a batch that does not exist. An upload's id came from the
    // engine's own `202` one tick earlier, so a 404 there is a race worth retrying, not a wrong URL
    // — and its message should stay the engine's rather than becoming "Stapelprüfung nicht
    // gefunden", which would send the reader to check a link they never followed.
    const fromDeepLink = batchId === deepLinkId

    async function tick() {
      if (cancelled || batchId === null) return

      const result = await fetchBatch(batchId)
      if (cancelled) return

      setResolvedRequest(request)

      if (result.kind === "error") {
        const failure = fromDeepLink
          ? toDeepLinkError("batch", result.error)
          : result.error
        setError(failure)
        // A single failed poll is not a failed batch — the job is still running on the engine — so
        // a transient error is shown and the loop keeps going rather than abandoning a job the user
        // cannot then get back to. **A definitive one ends it.** That is new, and it is what a deep
        // link made necessary: a `404` from a mistyped id is a permanent answer, and the old loop
        // would have asked for it every two seconds for fifteen minutes.
        if (!isRetryable(failure)) return
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
  }, [batchId, request, deepLinkId])

  const summary = job?.aggregate_summary
  const done = job !== null && isTerminal(job.status)

  /** Re-run the poll for the same batch. Only reachable from a deep link's error panel. */
  function retry() {
    setError(null)
    setStalled(false)
    setReloads((n) => n + 1)
  }

  return (
    <div className="space-y-6">
      {/*
        Kept on screen for a deep link too, rather than hidden behind the loaded batch. Someone who
        opened a finished run to read it is one of the people most likely to want to audit the next
        stack, and removing the only way to start one would be a worse trade than a little scrolling.
      */}
      <BatchDropzone
        onSubmit={(files) => void onSubmit(files)}
        pending={uploading}
      />

      {shownError ? (
        <ErrorPanel
          error={shownError}
          // Only for a deep link, and only when a second attempt could answer differently. An
          // upload failure is retried by dropping the files again, which the zone above already
          // offers.
          onRetry={
            deepLinkId !== null && isRetryable(shownError) ? retry : undefined
          }
          pending={loading}
        />
      ) : null}

      {loading ? <BatchSkeleton /> : null}

      {job ? <BatchProgress job={job} /> : null}

      {stalled ? (
        <Alert variant="destructive">
          <AlertTitle>Der Stapel antwortet nicht mehr</AlertTitle>
          <AlertDescription>
            Seit {POLL_TIMEOUT_MS / 60000} Minuten hat sich der Status nicht auf
            abgeschlossen geändert. Die Engine verarbeitet Stapel in einem
            FastAPI-BackgroundTask, der einen Neustart nicht überlebt — ein
            unterbrochener Lauf bleibt dauerhaft auf{" "}
            <span className="font-mono">PROCESSING</span> stehen. Die Dateien
            bitte erneut hochladen.
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
              Es wird bewusst <strong>keine</strong> Auswertung angezeigt: eine
              Summe über Dateien, die möglicherweise nie geschrieben wurden,
              wäre schlechter als gar keine.
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
              <AlertTitle>
                Die Auswertung enthält nicht die drei Bewertungsgruppen
              </AlertTitle>
              <AlertDescription>
                Der Stapel ist abgeschlossen, aber die Zusammenfassung trägt
                nicht die Felder confirmed_fine / confirmed_wrong / unconfirmed.
                Vermutlich laufen Engine und UI auf verschiedenen
                Contract-Versionen — packages/contracts neu generieren.
              </AlertDescription>
            </Alert>
          )}

          <Provenance job={job} />
          <BatchExport job={job} />
          <BatchFilesTable job={job} />
        </>
      ) : null}

      {/*
        Unchanged for a plain visit to /padnext/batch — same alert, same words. It only additionally
        stands aside while a deep-linked batch is loading, so a reader who clicked a row is never
        told nothing has been audited before the first poll has answered.
      */}
      {job === null && !uploading && shownError === null && !loading ? (
        <Alert>
          <LayersIcon />
          <AlertTitle>Noch kein Stapel geprüft</AlertTitle>
          <AlertDescription>
            Eine einzelne Rechnung beantwortet die Frage „ist diese Rechnung
            haltbar?“. Ein Stapel beantwortet die teurere: „ist unsere
            Abrechnung systematisch falsch, und wo?“ Die Auswertung trennt dabei
            dieselben drei Gruppen wie die Einzelprüfung — die mittlere Spalte
            ist die Grenze unserer Regelabdeckung, nicht ein Vorwurf gegen die
            Praxis.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
