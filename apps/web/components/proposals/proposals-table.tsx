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
import {
  engineQuery,
  looksLikeProposalId,
  nextHref,
  pageCount,
  type ListParams,
} from "@/lib/lists/params"
import { PROPOSAL_STATUS, statusPresentation } from "@/lib/status"
import { isProposalList, totalOrPageLength } from "@/lib/dashboard/types"
import { timestamp } from "@/lib/review/format"

export const PROPOSALS_PATH = "/proposals"

export const PROPOSAL_COLUMNS = [
  "Vorschlag",
  "Fall",
  "Status",
  "Erstellt",
  "Receipt-Hash",
  "",
] as const

/** The four lifecycle states, in the order the lifecycle visits them. */
const STATUS_OPTIONS: readonly StatusOption[] = [
  { value: null, label: "Alle Status" },
  { value: "DRAFT", label: "Entwurf" },
  { value: "APPROVED", label: "Freigegeben" },
  { value: "REJECTED", label: "Abgelehnt" },
  { value: "EXPORTED", label: "Exportiert" },
]

export const PROPOSAL_STATUS_VALUES = [
  "DRAFT",
  "APPROVED",
  "REJECTED",
  "EXPORTED",
] as const

/**
 * Every billing draft this database holds, filtered and paged.
 *
 * **The search box filters on `case_id`, exactly, and that is a limit of the endpoint rather than a
 * choice.** `GET /api/v1/proposals` takes `status` and `case_id`; it has no `proposal_id` parameter
 * and no substring match. So a pasted `prop_…` matches nothing, and rather than let the empty state
 * read as "no such proposal" — when what happened is "this list cannot search for that" — the shape
 * is recognised and the no-match state says which of the two it was. Closing it properly means one
 * more `where` clause on the engine's list query, and this change adds no backend work.
 *
 * `CopyableHash` for the two identifiers rather than plain truncated text. Both are values that have
 * to *leave* the browser: a `proposal_id` is how a record is found again in a ticket or a `psql`
 * query, and a `receipt_hash` is the evidence that a draft was produced by one exact engine state —
 * catalog, rule tables, logic programs, solver versions and policy. Sixteen characters a reader can
 * only retype by hand made the audit trail technically present and practically unusable.
 *
 * Fetched on the server, so `ENGINE_BASE_URL` stays out of the browser. The response is validated
 * rather than cast: an engine older than the paginated envelope answers this path with a bare JSON
 * array, and `.items.map` on that throws inside a server component and takes the page down.
 */
export async function ProposalsTable({ params }: { params: ListParams }) {
  const toolbar = (
    <ListToolbar
      params={params}
      statuses={STATUS_OPTIONS}
      search={{
        label: "Fall-ID",
        placeholder: "z. B. ENC-2026-0001",
        hint: "Exakte Übereinstimmung. Die Liste kann nicht nach Vorschlags-ID suchen.",
      }}
    />
  )

  // Answered before the fetch, and that ordering is the fix for a defect this had: dropping a
  // `prop_…` term and querying anyway returned the *unfiltered* page, so the screen showed 50 rows
  // that had nothing to do with what was typed. There is no engine call that can answer this, so
  // there is no engine call — the reader is told what the field does instead.
  if (params.query !== null && looksLikeProposalId(params.query)) {
    return (
      <Shell toolbar={toolbar}>
        <NoMatches
          message="Die Liste sucht nach Fall-ID, nicht nach Vorschlags-ID"
          hint={
            `„${params.query}“ sieht wie eine Vorschlags-ID aus. Dieses Feld filtert nach der ` +
            "Fall-ID, die der Aufrufer beim Lösen mitgegeben hat — nach einer Vorschlags-ID kann " +
            "die Engine ihre Liste noch nicht filtern."
          }
          reset={nextHref(PROPOSALS_PATH, params, {
            status: null,
            query: null,
            page: 1,
          })}
        />
      </Shell>
    )
  }

  const result = await callEngine(
    `/api/v1/proposals?${engineQuery({
      page: params.page,
      status: params.status,
      caseId: params.query,
    })}`
  )

  if (!result.ok) {
    return (
      <Shell toolbar={toolbar}>
        <LoadFailed
          headline="Prüfungen konnten nicht geladen werden"
          message={result.failure.message}
        />
      </Shell>
    )
  }

  if (!isProposalList(result.body)) {
    return (
      <Shell toolbar={toolbar}>
        <LoadFailed
          headline="Prüfungen konnten nicht geladen werden"
          message={
            "Die Engine hat auf GET /api/v1/proposals nicht mit einer paginierten Antwort " +
            "geantwortet. Vermutlich läuft eine ältere Engine-Version als dieses Frontend."
          }
        />
      </Shell>
    )
  }

  const items = result.body.items ?? []
  const total = totalOrPageLength(result.body.total, items.length)
  const filtered = params.status !== null || params.query !== null
  const reset = nextHref(PROPOSALS_PATH, params, {
    status: null,
    query: null,
    page: 1,
  })

  if (items.length === 0) {
    return (
      <Shell toolbar={toolbar}>
        {total > 0 ? (
          <PageOutOfRange
            firstPage={nextHref(PROPOSALS_PATH, params, { page: 1 })}
            pages={pageCount(total)}
          />
        ) : filtered ? (
          <NoMatches
            message="Keine Prüfung entspricht diesem Filter"
            hint="Kein Abrechnungsvorschlag in diesem Status oder zu dieser Fall-ID."
            reset={reset}
          />
        ) : (
          <NoRecords
            message="Noch keine Prüfungen vorhanden"
            hint={
              "Ein Abrechnungsvorschlag entsteht in der Prüfung, aus einem synthetischen Fall. " +
              "Er bleibt dauerhaft gespeichert und erscheint danach hier."
            }
            action={{ href: "/review", label: "Zur Prüfung" }}
          />
        )}
        <Pagination
          pathname={PROPOSALS_PATH}
          params={params}
          total={total}
          shown={items.length}
        />
      </Shell>
    )
  }

  return (
    <Shell toolbar={toolbar}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Vorschlag</TableHead>
            <TableHead>Fall</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Erstellt</TableHead>
            <TableHead>Receipt-Hash</TableHead>
            {/* The action column's header is empty rather than "Aktionen": the cell is one link
                whose own label already says what it does, and a header above it is noise a screen
                reader reads on every row. */}
            <TableHead className="w-0">
              <span className="sr-only">Aktionen</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((proposal) => {
            const status = statusPresentation(PROPOSAL_STATUS, proposal.status)
            return (
              <TableRow key={proposal.proposal_id}>
                <TableCell>
                  <CopyableHash
                    value={proposal.proposal_id}
                    length={13}
                    label="Vorschlags-ID"
                  />
                </TableCell>
                <TableCell>
                  {/* A proposal without a `case_id` is normal — it travels on the request and
                      nothing requires the caller to send one — so the absence is labelled. */}
                  {proposal.case_id ? (
                    <span className="font-mono text-xs">
                      {proposal.case_id}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      ohne Fall-ID
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={status.variant}
                    className={cn(status.className)}
                  >
                    {status.label}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground tabular-nums">
                  {timestamp(proposal.created_at)}
                </TableCell>
                <TableCell>
                  <CopyableHash
                    value={proposal.receipt_hash}
                    length={12}
                    label="Receipt-Hash"
                  />
                </TableCell>
                <TableCell className="text-right">
                  <Link
                    href={`/review?id=${encodeURIComponent(proposal.proposal_id)}`}
                    className={cn(
                      buttonVariants({ variant: "outline", size: "sm" })
                    )}
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
        pathname={PROPOSALS_PATH}
        params={params}
        total={total}
        shown={items.length}
      />
    </Shell>
  )
}

/** One card holding the toolbar, a separator and whatever the body turned out to be. */
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
        <div className="border-t border-border pt-2">{children}</div>
      </CardContent>
    </Card>
  )
}
