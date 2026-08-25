import { Badge } from "@workspace/ui/components/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import { ProofDialog } from "@/components/review/proof-dialog"
import { BLOCKED_REASON_LABEL } from "@/lib/review/format"
import type { Coding } from "@/lib/review/types"

/**
 * Same reasoning as the accepted table: stripes run to the card's edge, text does not.
 *
 * The right gutter is narrower here than on the accepted table. This is the column that gets squeezed
 * by the 3:2 split, and four columns of German medical prose in 440px need every pixel that is not
 * carrying meaning.
 */
const EDGE_PADDING =
  "[&_td:first-child]:pl-6 [&_td:last-child]:pr-4 [&_th:first-child]:pl-6 [&_th:last-child]:pr-4"

/**
 * German medical legend text needs to be allowed to break.
 *
 * "Elektrokardiographische" is twenty-three characters that no amount of column-width negotiation
 * will shorten: without this the longest single word in a cell becomes that column's minimum width,
 * and the table overflows its card at every viewport. `hyphens-auto` does the right thing because
 * the document is `lang="de"`; `break-words` is the fallback for the strings that have no hyphen
 * points, such as a rule id.
 */
const WRAP = "hyphens-auto break-words"


/**
 * Positions the rules removed, and why.
 *
 * `reconciled_with_final_invoice: false` is called out rather than hidden: it means the position's
 * blocker is itself not on the final invoice, so the suppression has lost its basis and the position
 * may well be chargeable after all. The engine reports it instead of silently reinstating it, and a
 * reviewer is exactly who should decide.
 *
 * Each blocked position carries its own `proof`. It used to require joining `audit_trail.per_code`
 * by Ziffer, which meant a client had to know that relationship existed; the engine now publishes
 * the steps on the position itself, built from the same source as the audit entry.
 *
 * ## Three columns
 *
 * Grund is the column a reviewer is here for, so it gets the larger share: the reason label, what
 * displaced the position, the engine's explanation, and — as a footnote under it — the rule id and
 * the paragraph it rests on, which used to be two columns of their own. A rule id is what you quote
 * when you are disputing the suppression, not what you scan a list by.
 *
 * Both text columns carry a `min-w-40` floor, and between roughly 1280px and 1500px that floor is
 * wider than the 2/5 of the page this card gets, so the table scrolls sideways inside its card. That
 * is the intended trade: a GOÄ legend rendered three words to a line is not readable at any width,
 * and collapsing the column away would hide the sentence a reviewer is here to check.
 *
 * The red is deliberately restrained: a tinted Ziffer and a `destructive` badge, not a red table. A
 * blocked position is a normal, correct outcome of the rules — it is not an error, and a wall of red
 * would train a reviewer to dismiss the one row here that genuinely needs them.
 */
export function BlockedPositionsTable({ coding }: { coding: Coding }) {
  const blocked = coding.blocked_codes ?? []

  if (blocked.length === 0) {
    return (
      <p className="text-muted-foreground px-6 text-sm">
        Keine Position wurde durch eine Regel unterdrückt.
      </p>
    )
  }

  return (
    <Table className={EDGE_PADDING}>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Ziffer</TableHead>
          <TableHead className="px-2">Beschreibung</TableHead>
          <TableHead className="px-2">Grund</TableHead>
          {/* A dialog trigger is useless on paper; the whole column goes with it. */}
          <TableHead className="text-right print:hidden">Beweis</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {blocked.map((entry, index) => (
          <TableRow
            key={`${entry.ziffer}-${entry.reason}-${index}`}
            className="odd:bg-muted/30 hover:bg-transparent"
          >
            <TableCell className="text-destructive align-top font-mono font-medium">
              {entry.ziffer}
            </TableCell>
            <TableCell className={`w-2/5 min-w-40 px-2 align-top text-sm whitespace-normal ${WRAP}`}>
              {entry.official_text || "—"}
            </TableCell>
            <TableCell className={`w-3/5 min-w-40 px-2 align-top whitespace-normal ${WRAP}`}>
              <Badge variant="destructive">{BLOCKED_REASON_LABEL[entry.reason]}</Badge>
              {entry.blocked_by ? (
                <div className="text-muted-foreground mt-1 text-xs">
                  verdrängt durch <span className="font-mono">GOÄ {entry.blocked_by}</span>
                </div>
              ) : null}
              {entry.explanation || entry.detail ? (
                <p className="mt-1.5 text-sm">{entry.explanation || entry.detail}</p>
              ) : null}
              {entry.rule_id || entry.legal_basis ? (
                <p className="text-muted-foreground mt-1 text-xs">
                  {entry.rule_id ? <span className="font-mono break-all">{entry.rule_id}</span> : null}
                  {entry.rule_id && entry.legal_basis ? " · " : null}
                  {entry.legal_basis}
                </p>
              ) : null}
              {entry.reconciled_with_final_invoice === false ? (
                <Badge variant="destructive" className="mt-1.5">
                  Sperrgrund entfallen — manuell prüfen
                </Badge>
              ) : null}
            </TableCell>
            <TableCell className="px-1 align-top text-right print:hidden">
              <ProofDialog
                ziffer={entry.ziffer}
                officialText={entry.official_text}
                steps={entry.proof ?? []}
                compact
              />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
