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
import { PROPOSAL_STATUS, statusPresentation } from "@/lib/dashboard/format"
import { isProposalList, totalOrPageLength } from "@/lib/dashboard/types"

export const RECENT_PROPOSALS_TITLE = "Letzte Prüfungen"

/** How many rows the card shows. Five is what fits beside the batch card without a scroll area. */
const LIMIT = 5

/**
 * The five newest billing drafts, and how many there are in total.
 *
 * **This is the card the listing endpoint's `total` was added for.** Five rows on their own would
 * say nothing about whether anything is waiting; "5 von 214" is the sentence a reviewer opening this
 * screen actually needs, and it is the whole backlog rather than the page.
 *
 * `limit=5` is not decoration either. A row in this response is a full `Proposal` — the entire
 * `solver_result`, every proof tree — so the endpoint's default page of fifty would be megabytes to
 * render four lines of text. The engine caps `limit` at 100; this card asks for five.
 *
 * The response is validated rather than cast. An engine older than the paginated envelope answers
 * this path with a bare JSON array, and `(body as ProposalList).items.map` on that would throw
 * inside a server component and take the whole dashboard down — including the two cards that were
 * fine. See `lib/dashboard/types.ts`.
 */
export async function RecentProposalsCard() {
  const result = await callEngine(`/api/v1/proposals?limit=${LIMIT}`)

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardTitle className="text-base">{RECENT_PROPOSALS_TITLE}</CardTitle>
        <CardDescription>
          <Body result={result} />
        </CardDescription>
        {/*
          The way out of "5 von 214". A card that states a total it cannot show the rest of is a
          dead end, so the header carries the link to the full, filterable list.
        */}
        <CardAction>
          <Link
            href="/proposals"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Alle Prüfungen
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

/** The one line under the title: how much of the table the rows below are. */
function Body({ result }: { result: Awaited<ReturnType<typeof callEngine>> }) {
  if (!result.ok || !isProposalList(result.body)) {
    return <>Abrechnungsvorschläge, neueste zuerst.</>
  }
  const page = result.body.items?.length ?? 0
  const total = totalOrPageLength(result.body.total, page)
  if (total === 0) return <>Abrechnungsvorschläge, neueste zuerst.</>
  return (
    <>
      <span className="tabular-nums">{page}</span> von{" "}
      <span className="tabular-nums">{total}</span> Abrechnungsvorschlägen,
      neueste zuerst.
    </>
  )
}

function Rows({ result }: { result: Awaited<ReturnType<typeof callEngine>> }) {
  if (!result.ok) {
    return (
      <ErrorState
        headline="Prüfungen konnten nicht geladen werden"
        message={result.failure.message}
      />
    )
  }

  if (!isProposalList(result.body)) {
    // A 200 whose body is not the envelope. Almost certainly an engine older than the paginated
    // response, so the fix is named rather than reported as an unspecified error.
    return (
      <ErrorState
        headline="Prüfungen konnten nicht geladen werden"
        message={
          "Die Engine hat auf GET /api/v1/proposals nicht mit einer paginierten Antwort " +
          "geantwortet. Vermutlich läuft eine ältere Engine-Version als dieses Frontend."
        }
      />
    )
  }

  const items = result.body.items ?? []
  if (items.length === 0) {
    return (
      <EmptyState
        message="Noch keine Prüfungen vorhanden"
        hint="Ein Abrechnungsvorschlag entsteht in der Prüfung, aus einem synthetischen Fall."
      />
    )
  }

  return (
    <ul className="divide-y divide-border">
      {items.map((proposal) => (
        <ActivityRow
          key={proposal.proposal_id}
          row={{
            id: proposal.proposal_id,
            href: `/review?id=${encodeURIComponent(proposal.proposal_id)}`,
            // A proposal without a `case_id` is normal — it travels on the request, and nothing
            // requires the caller to send one — so the absence is labelled rather than left blank.
            detail: proposal.case_id
              ? `Fall ${proposal.case_id}`
              : "ohne Fall-ID",
            createdAt: proposal.created_at,
          }}
          status={statusPresentation(PROPOSAL_STATUS, proposal.status)}
        />
      ))}
    </ul>
  )
}
