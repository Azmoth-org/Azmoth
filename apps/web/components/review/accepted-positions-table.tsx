import { CheckIcon, ReceiptTextIcon, TriangleAlertIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from "@workspace/ui/components/empty"
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import { ProofDialog } from "@/components/review/proof-dialog"
import { eur, factor, factorBasis, lineStatus, rate } from "@/lib/review/format"
import type { Coding } from "@/lib/review/types"

/**
 * Flush the table to the card's edges and keep the text off them.
 *
 * `CardContent` is given `px-0` by the caller so the header row and the zebra stripes run the full
 * width of the card — a stripe that stops short of the edge reads as a box inside a box. The row
 * padding is restored on the first and last cell instead of on the container.
 */
const EDGE_PADDING =
  "[&_td:first-child]:pl-6 [&_td:last-child]:pr-6 [&_th:first-child]:pl-6 [&_th:last-child]:pr-6"

/**
 * Side padding for the three figure columns.
 *
 * `p-3` on each of Punkte, Faktor and Betrag spent 72px of a 730px table on whitespace between
 * numbers that are already right-aligned and therefore already separated. That width belongs to the
 * Leistung column, which is a sentence.
 */
const FIGURE = "px-2 text-right align-top"

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


function JustificationBadge({
  required,
  present,
  justification,
}: {
  required: boolean
  present: boolean
  justification: string | null | undefined
}) {
  if (!required) return null

  if (present) {
    return (
      <div className="mt-1.5 min-w-0 space-y-1">
        <Badge variant="secondary" className="gap-1">
          <CheckIcon />
          begründet
        </Badge>
        {justification ? (
          <p className="text-muted-foreground line-clamp-3 text-xs" title={justification}>
            {justification}
          </p>
        ) : null}
      </div>
    )
  }

  return (
    <Badge variant="destructive" className="mt-1.5 gap-1">
      <TriangleAlertIcon />
      Begründung fehlt (§ 12 Abs. 3 GOÄ)
    </Badge>
  )
}

/**
 * The invoice draft's accepted positions.
 *
 * Every monetary value and every factor is printed exactly as the engine returned it — the engine
 * computes in `Decimal` and serialises to a string so that no client can re-round it. Nothing on
 * this screen adds, multiplies or re-formats a number; the totals row is the engine's own
 * `coding.total`, not a sum computed here.
 *
 * ## Why five columns and not seven
 *
 * This table now sits in a column rather than across the page, so the two cells that were pure prose
 * — the § 12 Abs. 3 justification and the line's status, category and Analogansatz — moved into the
 * Leistung cell they were describing. Nothing was dropped: the same badges, the same text, the same
 * proof tree, one column narrower each. What is left is the shape of an invoice line, which is what
 * a reader is checking: Ziffer, Leistung, Punkte, Faktor, Betrag.
 *
 * `whitespace-normal` on the Leistung cell is a fix, not a style. `TableCell` sets
 * `whitespace-nowrap` for figures, `white-space` inherits, and the official GOÄ text is a sentence —
 * so every description was being laid out on a single line and pushed the amounts off the right edge
 * of the viewport, which is most of why this table needed horizontal scrolling to read at all.
 */
export function AcceptedPositionsTable({ coding }: { coding: Coding }) {
  const lines = coding.proposed_codes ?? []
  const total = coding.total

  if (lines.length === 0) {
    return (
      <Empty className="mx-6 border">
        <EmptyMedia variant="icon">
          <ReceiptTextIcon />
        </EmptyMedia>
        <EmptyTitle>Keine berechnungsfähige Position</EmptyTitle>
        <EmptyDescription>
          Ein gültiges Ergebnis, kein Fehler: die dokumentierten Leistungen ließen sich keiner
          durchsetzbaren Position zuordnen. Die gesperrten Positionen und die Hinweise der Engine
          stehen daneben.
        </EmptyDescription>
      </Empty>
    )
  }

  return (
    <Table className={EDGE_PADDING}>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Ziffer</TableHead>
          <TableHead>Leistung</TableHead>
          <TableHead className="px-2 text-right">Punkte</TableHead>
          <TableHead className="px-2 text-right">Faktor</TableHead>
          <TableHead className="px-2 text-right">Betrag</TableHead>
          {/* A dialog trigger is useless on paper; the whole column goes with it. */}
          <TableHead className="text-right print:hidden">Beweis</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {lines.map((line) => (
          <TableRow
            key={`${line.ziffer}-${line.status ?? ""}`}
            className="odd:bg-muted/30 hover:bg-transparent"
          >
            <TableCell className="align-top font-mono font-medium">
              <div>{line.ziffer}</div>
              {line.is_analog ? (
                <Badge variant="outline" className="mt-1">
                  analog
                </Badge>
              ) : null}
            </TableCell>
            <TableCell className={`w-full min-w-52 align-top whitespace-normal ${WRAP}`}>
              <div className="text-sm">{line.official_text}</div>
              <div className="text-muted-foreground mt-1 flex flex-wrap gap-x-2 text-xs">
                <span>{lineStatus(line.status)}</span>
                {line.category ? <span>· Abschnitt {line.category}</span> : null}
                {line.analog_for ? <span>· analog für {line.analog_for}</span> : null}
                {line.text_quality && line.text_quality !== "ok" ? (
                  <span className="text-destructive">· Textqualität: {line.text_quality}</span>
                ) : null}
              </div>
              <JustificationBadge
                required={line.justification_required ?? false}
                present={line.justification_present ?? false}
                justification={line.justification}
              />
            </TableCell>
            <TableCell className={`${FIGURE} tabular-nums`}>{line.punkte}</TableCell>
            <TableCell className={`${FIGURE} max-w-24 whitespace-normal`}>
              <div className="tabular-nums">{factor(line.factor)}</div>
              <div className="text-muted-foreground text-xs">{factorBasis(line.factor_basis)}</div>
            </TableCell>
            <TableCell className={FIGURE}>
              <div className="font-medium tabular-nums">{eur(line.amount_eur)}</div>
              {line.minderung_applied ? (
                <div className="text-muted-foreground text-xs">
                  vor § 6a: {eur(line.amount_eur_before_minderung)}
                </div>
              ) : null}
            </TableCell>
            <TableCell className="px-2 align-top text-right print:hidden">
              <ProofDialog
                ziffer={line.ziffer}
                officialText={line.official_text}
                steps={line.proof ?? []}
                compact
              />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
      {total ? (
        <TableFooter>
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={2} className="whitespace-normal">
              <div className="font-medium">Gesamt</div>
              <div className="text-muted-foreground text-xs">
                Von der Engine ausgewiesen, nicht im Frontend berechnet.
              </div>
            </TableCell>
            <TableCell className={`${FIGURE} tabular-nums`}>{total.punkte}</TableCell>
            <TableCell className={`${FIGURE} text-muted-foreground text-xs`}>
              Punktwert
              <br />
              {total.punktwert_cent} ct
            </TableCell>
            <TableCell className={`${FIGURE} text-base font-semibold tabular-nums`}>
              {eur(total.amount_eur)}
            </TableCell>
            <TableCell className="print:hidden" />
          </TableRow>
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={5} className="text-muted-foreground whitespace-normal text-xs">
              {total.minderung_applied
                ? `§ 6a Minderung angewendet (Satz ${rate(total.minderung_rate)}) · `
                : ""}
              Rundung {total.rounding_policy}
              {total.rounding_legal_basis ? ` (${total.rounding_legal_basis})` : ""}
            </TableCell>
          </TableRow>
        </TableFooter>
      ) : null}
    </Table>
  )
}
