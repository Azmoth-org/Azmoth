import { Card, CardContent } from "@workspace/ui/components/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import { CopyableHash } from "@/components/common/copyable-hash"
import { Pagination } from "@/components/lists/pagination"
import { LoadFailed, NoRecords } from "@/components/lists/table-states"
import { callEngine } from "@/lib/engine"
import { isRuleProposalList, totalOrPageLength } from "@/lib/dashboard/types"
import { engineQuery, type ListParams } from "@/lib/lists/params"
import { timestamp } from "@/lib/review/format"

export const RULE_PROPOSALS_PATH = "/rules/proposals"

export const RULE_PROPOSAL_COLUMNS = [
  "Ziffer",
  "Anmerkung",
  "Receipt-Hash",
  "Gemeldet am",
] as const

/**
 * Every `Regel fehlt? Ziffer melden` report the calling organisation has filed, newest first.
 *
 * There is no status column and no filter toolbar, unlike `ProposalsTable` and
 * `BatchHistoryTable` beside this component: a report is a data point towards deciding which rule
 * to write next, not a workflow item with a state to narrow on. Pagination is the only control this
 * table needs — see the module docstring of `app.schemas.rule_proposals` on the engine side.
 */
export async function RuleProposalsTable({ params }: { params: ListParams }) {
  const result = await callEngine(
    `/api/v1/rules/proposals?${engineQuery({ page: params.page, status: null })}`
  )

  if (!result.ok) {
    return (
      <Shell>
        <LoadFailed
          headline="Meldungen konnten nicht geladen werden"
          message={result.failure.message}
        />
      </Shell>
    )
  }

  if (!isRuleProposalList(result.body)) {
    return (
      <Shell>
        <LoadFailed
          headline="Meldungen konnten nicht geladen werden"
          message="Die Engine hat auf GET /api/v1/rules/proposals keine passende Liste geantwortet."
        />
      </Shell>
    )
  }

  const items = result.body.items ?? []
  const total = totalOrPageLength(result.body.total, items.length)

  if (items.length === 0) {
    return (
      <Shell>
        <NoRecords
          message="Noch keine Meldungen vorhanden"
          hint={
            "Eine Meldung entsteht über „Regel fehlt? Ziffer melden“ auf einem Prüfbericht. Sie " +
            "erscheint hier, sobald die erste eingegangen ist."
          }
          action={{ href: "/review", label: "Zur Prüfung" }}
        />
      </Shell>
    )
  }

  return (
    <Shell>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Ziffer</TableHead>
            <TableHead>Anmerkung</TableHead>
            <TableHead>Receipt-Hash</TableHead>
            <TableHead>Gemeldet am</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.id}>
              <TableCell className="font-mono text-xs">{item.ziffer}</TableCell>
              <TableCell className="max-w-md text-sm">{item.context}</TableCell>
              <TableCell>
                <CopyableHash value={item.receipt_hash} label="Receipt-Hash" />
              </TableCell>
              <TableCell className="text-xs text-muted-foreground tabular-nums">
                {timestamp(item.created_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Pagination
        pathname={RULE_PROPOSALS_PATH}
        params={params}
        total={total}
        shown={items.length}
      />
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="space-y-4 pt-6">{children}</CardContent>
    </Card>
  )
}
