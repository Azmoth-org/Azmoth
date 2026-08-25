"use client"

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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@workspace/ui/components/tooltip"
import { cn } from "@workspace/ui/lib/utils"

import { ProofDialog } from "@/components/review/proof-dialog"
import {
  CARDS_ONLY,
  CLAMP_2,
  EDGE_PADDING,
  FIGURE,
  HEAD,
  HEAD_FIGURE,
  ROW,
  TABLE_ONLY,
  WRAP,
} from "@/components/review/table-style"
import { eur, factor, factorBasis, lineStatus, rate } from "@/lib/review/format"
import type { Coding, InvoiceLine } from "@/lib/review/types"

/**
 * Roughly the length at which a GOÄ legend stops fitting in two lines of the Leistung column.
 *
 * A tooltip that repeats a sentence already fully visible is not a help, it is a flicker under the
 * cursor — so the short legends do not get one. The threshold is generous on purpose: showing the
 * tooltip on a sentence that happened to fit costs a reader nothing, and withholding it from one
 * that was cut off costs them the text.
 */
const TOOLTIP_THRESHOLD = 90

/**
 * A legend, clamped on screen and whole everywhere else.
 *
 * `line-clamp` is a *visual* truncation: the full sentence stays in the DOM, so a screen reader
 * reads all of it and find-in-page still finds it. The tooltip is therefore for sighted mouse users
 * only, which is why nothing here is wired to focus — and why print unclamps rather than
 * substituting a tooltip it cannot show.
 */
function Legend({ text }: { text: string }) {
  const body = <div className={cn("text-sm", CLAMP_2, WRAP)}>{text}</div>
  if (text.length <= TOOLTIP_THRESHOLD) return body

  return (
    <Tooltip>
      <TooltipTrigger render={body} />
      <TooltipContent side="top" className="max-w-sm text-left leading-relaxed">
        {text}
      </TooltipContent>
    </Tooltip>
  )
}

/**
 * § 12 Abs. 3 GOÄ, as a badge rather than as a paragraph.
 *
 * A missing justification is the one thing in this cell that changes what a reviewer has to *do*, so
 * it stays loud. A justification that is present is a tick and nothing more on screen: the text
 * itself is evidence, not a scanning aid, and it is kept for paper — where the reader is checking
 * the record rather than working down the list.
 */
function JustificationBadge({ line }: { line: InvoiceLine }) {
  if (!line.justification_required) return null

  if (!line.justification_present) {
    return (
      <Badge variant="destructive" className="gap-1">
        <TriangleAlertIcon />
        Begründung fehlt (§ 12 Abs. 3 GOÄ)
      </Badge>
    )
  }

  return (
    <>
      <Badge variant="secondary" className="gap-1">
        <CheckIcon />
        begründet
      </Badge>
      {line.justification ? (
        <p className={cn("text-muted-foreground hidden text-xs print:block", WRAP)}>
          {line.justification}
        </p>
      ) : null}
    </>
  )
}

/** Textqualität, only when it is not `ok` — the engine's own flag that a legend may be garbled. */
function TextQualityBadge({ line }: { line: InvoiceLine }) {
  if (!line.text_quality || line.text_quality === "ok") return null
  return (
    <Badge variant="destructive" className="gap-1">
      <TriangleAlertIcon />
      Textqualität: {line.text_quality}
    </Badge>
  )
}

/**
 * Status, Abschnitt and Analogansatz — the line's classification.
 *
 * On screen this is three fragments of small grey text under every single row, which is precisely
 * the kind of uniform detail that makes a table unscannable: it is identical on eight rows out of
 * nine and therefore carries no distinction, while costing each row a third line. It moves onto
 * paper, where the reader is checking a record rather than working down a list, and the row on
 * screen keeps only what differs.
 */
function Classification({ line }: { line: InvoiceLine }) {
  return (
    <div className="text-muted-foreground hidden flex-wrap gap-x-2 text-xs print:flex">
      <span>{lineStatus(line.status)}</span>
      {line.category ? <span>· Abschnitt {line.category}</span> : null}
      {line.analog_for ? <span>· analog für {line.analog_for}</span> : null}
    </div>
  )
}

/** The badges a row only carries when something about it needs acting on. */
function Signals({ line }: { line: InvoiceLine }) {
  const hasSignal = line.justification_required || (line.text_quality && line.text_quality !== "ok")
  if (!hasSignal) return null

  return (
    <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-1.5">
      <TextQualityBadge line={line} />
      <JustificationBadge line={line} />
    </div>
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
 * ## What the row is for
 *
 * Five columns in the shape of an invoice line — Ziffer, Leistung, Punkte, Faktor, Betrag — with the
 * three figures right-aligned and `tabular-nums`, so a column of amounts lines up on its decimal
 * point and a reader can compare them without reading them. That is the whole reason the figures do
 * not sit inline with the prose: an amount you have to *find* is an amount you check one at a time.
 *
 * Rows are 56px rather than 40px and the legend is clamped to two lines. Both are the same decision:
 * a physician working down nine positions is looking for the one that is wrong, and a table whose
 * row height is set by its longest legend gives them nothing to step down. The full sentence is a
 * hover away, and unclamped on paper.
 *
 * ## Below `lg`, a list of cards
 *
 * Five columns do not survive a tablet, let alone a 390px viewport — the previous version scrolled
 * sideways, which means the Betrag and the Ziffer it belongs to are never on screen together. The
 * card form puts them on one line and drops nothing. The table is what prints, always.
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

  // The engine's own footnote about how the total was reached. Built once and rendered twice —
  // under the table and under the mobile total card — so the two cannot drift apart.
  const footnote = total
    ? `${
        total.minderung_applied
          ? `§ 6a Minderung angewendet (Satz ${rate(total.minderung_rate)}) · `
          : ""
      }Rundung ${total.rounding_policy}${
        total.rounding_legal_basis ? ` (${total.rounding_legal_basis})` : ""
      }`
    : null

  return (
    <>
      <div className={TABLE_ONLY}>
        <Table className={EDGE_PADDING}>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className={HEAD}>Ziffer</TableHead>
              <TableHead className={HEAD}>Leistung</TableHead>
              <TableHead className={HEAD_FIGURE}>Punkte</TableHead>
              <TableHead className={HEAD_FIGURE}>Faktor</TableHead>
              <TableHead className={HEAD_FIGURE}>Betrag</TableHead>
              {/* A dialog trigger is useless on paper; the whole column goes with it. */}
              <TableHead className={cn(HEAD, "text-right print:hidden")}>Beweis</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {lines.map((line) => (
              <TableRow
                key={`${line.ziffer}-${line.status ?? ""}`}
                className={cn(ROW, "odd:bg-muted/30 hover:bg-transparent")}
              >
                <TableCell className="align-middle font-mono text-sm font-medium">
                  <div>{line.ziffer}</div>
                  {line.is_analog ? (
                    <Badge variant="outline" className="mt-1">
                      analog
                    </Badge>
                  ) : null}
                </TableCell>
                <TableCell className="w-full min-w-52 align-middle whitespace-normal">
                  <Legend text={line.official_text} />
                  <Classification line={line} />
                  <Signals line={line} />
                </TableCell>
                <TableCell className={FIGURE}>{line.punkte}</TableCell>
                <TableCell className={cn(FIGURE, "max-w-28 whitespace-normal")}>
                  <div>{factor(line.factor)}</div>
                  <div className="text-muted-foreground text-xs">
                    {factorBasis(line.factor_basis)}
                  </div>
                </TableCell>
                <TableCell className={FIGURE}>
                  <div className="font-medium">{eur(line.amount_eur)}</div>
                  {line.minderung_applied ? (
                    <div className="text-muted-foreground text-xs">
                      vor § 6a: {eur(line.amount_eur_before_minderung)}
                    </div>
                  ) : null}
                </TableCell>
                <TableCell className="px-2 text-right align-middle print:hidden">
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
              <TableRow className={cn(ROW, "hover:bg-transparent")}>
                <TableCell colSpan={2} className="whitespace-normal">
                  <div className="text-base font-semibold">Gesamt</div>
                  <div className="text-muted-foreground text-xs font-normal">
                    Von der Engine ausgewiesen, nicht im Frontend berechnet.
                  </div>
                </TableCell>
                <TableCell className={cn(FIGURE, "text-base font-semibold")}>
                  {total.punkte}
                </TableCell>
                <TableCell className={cn(FIGURE, "text-muted-foreground text-xs font-normal")}>
                  Punktwert
                  <br />
                  {total.punktwert_cent} ct
                </TableCell>
                <TableCell className={cn(FIGURE, "text-xl font-bold")}>
                  {eur(total.amount_eur)}
                </TableCell>
                <TableCell className="print:hidden" />
              </TableRow>
              {footnote ? (
                <TableRow className="hover:bg-transparent">
                  <TableCell
                    colSpan={6}
                    className="text-muted-foreground text-xs font-normal whitespace-normal"
                  >
                    {footnote}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableFooter>
          ) : null}
        </Table>
      </div>

      <ul className={cn(CARDS_ONLY, "space-y-3 px-6")}>
        {lines.map((line) => (
          <li key={`${line.ziffer}-${line.status ?? ""}`} className="rounded-2xl border p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <span className="font-mono text-sm font-medium">{line.ziffer}</span>
                {line.is_analog ? <Badge variant="outline">analog</Badge> : null}
              </div>
              <span className="shrink-0 text-lg font-semibold tabular-nums">
                {eur(line.amount_eur)}
              </span>
            </div>

            <p className={cn("mt-2 text-sm", WRAP)}>{line.official_text}</p>

            <dl className="text-muted-foreground mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t pt-3 text-xs">
              <div className="flex gap-1">
                <dt>Punkte</dt>
                <dd className="text-foreground tabular-nums">{line.punkte}</dd>
              </div>
              <div className="flex gap-1">
                <dt>Faktor</dt>
                <dd className="text-foreground tabular-nums">{factor(line.factor)}</dd>
              </div>
              <div className="flex gap-1">
                <dt className="sr-only">Faktorgrundlage</dt>
                <dd>{factorBasis(line.factor_basis)}</dd>
              </div>
            </dl>

            <Signals line={line} />

            <div className="mt-3">
              <ProofDialog
                ziffer={line.ziffer}
                officialText={line.official_text}
                steps={line.proof ?? []}
              />
            </div>
          </li>
        ))}

        {total ? (
          <li className="bg-muted/40 rounded-2xl border p-4">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-base font-semibold">Gesamt</span>
              <span className="text-2xl font-bold tabular-nums">{eur(total.amount_eur)}</span>
            </div>
            <p className="text-muted-foreground mt-1 text-xs">
              {total.punkte} Punkte · Punktwert {total.punktwert_cent} ct · von der Engine
              ausgewiesen, nicht im Frontend berechnet.
            </p>
            {footnote ? <p className="text-muted-foreground mt-1 text-xs">{footnote}</p> : null}
          </li>
        ) : null}
      </ul>
    </>
  )
}
