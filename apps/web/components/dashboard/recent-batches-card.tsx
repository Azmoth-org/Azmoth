import { ArrowRightIcon } from "lucide-react"
import Link from "next/link"

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

import { ActivityRow } from "@/components/dashboard/activity-row"
import { EmptyState, ErrorState } from "@/components/dashboard/card-states"
import { callEngine } from "@/lib/engine"
import { BATCH_STATUS, fileCount, statusPresentation } from "@/lib/dashboard/format"
import { isBatchAuditJobList, totalOrPageLength } from "@/lib/dashboard/types"

export const RECENT_BATCHES_TITLE = "Letzte Stapelprüfungen"

const LIMIT = 5

/**
 * The five newest batch runs, and how many there are in total.
 *
 * **This card is the reason the batch listing endpoint exists at all.** A `batch_id` is issued once,
 * in the `202`, and the browser holds it in memory — so before the listing, a page reload orphaned a
 * finished batch whose roll-up was still sitting in Postgres with nothing able to ask for it. Until
 * now the listing had no reader. This is it.
 *
 * It is also where a run the engine's startup recovery closed becomes visible: those rows come back
 * `FAILED`, which is why `FAILED` is the one status here painted `destructive`. A reader scanning for
 * "did my upload finish" must not mistake an interrupted run for a completed one.
 *
 * Rows are headers without their files — the listing model has no `files` field to misread — so
 * `limit=5` here is a fraction of the payload the proposals card asks for. It is five for symmetry
 * with that card rather than out of necessity.
 */
export async function RecentBatchesCard() {
  const result = await callEngine(`/api/v1/padnext/batch?limit=${LIMIT}`)

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardTitle className="text-base">{RECENT_BATCHES_TITLE}</CardTitle>
        <CardDescription>
          <Body result={result} />
        </CardDescription>
        {/*
          The way out of "5 von 214". A card that states a total it cannot show the rest of is a
          dead end, so the header carries the link to the full, filterable list.
        */}
        <CardAction>
          <Link
            href="/padnext/batch/history"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs transition-colors"
          >
            Stapel-Historie
            <ArrowRightIcon className="size-3" aria-hidden />
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent className="flex-1">
        <Rows result={result} />
      </CardContent>
    </Card>
  )
}

function Body({ result }: { result: Awaited<ReturnType<typeof callEngine>> }) {
  if (!result.ok || !isBatchAuditJobList(result.body)) {
    return <>PADnext-Stapel, neueste zuerst.</>
  }
  const page = result.body.jobs?.length ?? 0
  const total = totalOrPageLength(result.body.total, page)
  if (total === 0) return <>PADnext-Stapel, neueste zuerst.</>
  return (
    <>
      <span className="tabular-nums">{page}</span> von{" "}
      <span className="tabular-nums">{total}</span> Stapeln, neueste zuerst.
    </>
  )
}

function Rows({ result }: { result: Awaited<ReturnType<typeof callEngine>> }) {
  if (!result.ok) {
    return (
      <ErrorState
        headline="Stapelprüfungen konnten nicht geladen werden"
        message={result.failure.message}
      />
    )
  }

  if (!isBatchAuditJobList(result.body)) {
    return (
      <ErrorState
        headline="Stapelprüfungen konnten nicht geladen werden"
        message="Die Engine hat auf GET /api/v1/padnext/batch keine Stapelliste geantwortet."
      />
    )
  }

  const jobs = result.body.jobs ?? []
  if (jobs.length === 0) {
    return (
      <EmptyState
        message="Noch keine Stapelprüfungen vorhanden"
        hint="Ein Stapel entsteht in der Stapelprüfung, aus mehreren PADnext-Lieferungen."
      />
    )
  }

  return (
    <ul className="divide-border divide-y">
      {jobs.map((job) => (
        <ActivityRow
          key={job.batch_id}
          row={{
            id: job.batch_id,
            href: `/padnext/batch?id=${encodeURIComponent(job.batch_id)}`,
            // Progress rather than the bare total while a run is unfinished: "3 von 10 geprüft" is
            // the one thing a listing row has to be able to say, and the counts come from
            // `batch_files` so they are honest about a job with no roll-up yet.
            detail: batchDetail(job),
            createdAt: job.created_at,
          }}
          status={statusPresentation(BATCH_STATUS, job.status)}
        />
      ))}
    </ul>
  )
}

function batchDetail(job: { file_count?: number; processed_file_count?: number }): string {
  const total = job.file_count ?? 0
  const processed = job.processed_file_count ?? 0
  if (total > 0 && processed < total) {
    return `${processed} von ${total} geprüft`
  }
  return fileCount(total)
}
