"use client"

import { ChevronDownIcon, ShieldCheckIcon, TriangleAlertIcon } from "lucide-react"
import * as React from "react"

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
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"
import { cn } from "@workspace/ui/lib/utils"

import { ProofDialog } from "@/components/review/proof-dialog"
import {
  CARDS_ONLY,
  CLAMP_2,
  EDGE_PADDING,
  HEAD,
  ROW,
  TABLE_ONLY,
  WRAP,
} from "@/components/review/table-style"
import { BLOCKED_REASON_LABEL, BLOCKED_REASON_SHORT } from "@/lib/review/format"
import type { BlockedCode, Coding } from "@/lib/review/types"

/** A stable key for one suppression. Ziffer alone is not unique — a position can lose twice. */
function keyOf(entry: BlockedCode, index: number): string {
  return `${entry.ziffer}-${entry.reason}-${index}`
}

/**
 * Everything about a suppression that is not its Ziffer, its legend or its reason badge.
 *
 * Shared by the table's detail row and the card below `lg`, so the two cannot say different things —
 * and rendered unconditionally on paper, because "the reviewer had not clicked this row" is not a
 * reason for a printed proposal to omit why a position was removed.
 */
function BlockedDetail({ entry }: { entry: BlockedCode }) {
  return (
    <div className={cn("space-y-2 text-sm", WRAP)}>
      <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="text-foreground font-medium">{BLOCKED_REASON_LABEL[entry.reason]}</span>
        {entry.blocked_by ? (
          <span>
            · verdrängt durch <span className="font-mono">GOÄ {entry.blocked_by}</span>
          </span>
        ) : null}
      </div>

      {entry.explanation || entry.detail ? <p>{entry.explanation || entry.detail}</p> : null}

      {entry.rule_id || entry.legal_basis ? (
        <p className="text-muted-foreground text-xs">
          {entry.rule_id ? <span className="font-mono break-all">{entry.rule_id}</span> : null}
          {entry.rule_id && entry.legal_basis ? " · " : null}
          {entry.legal_basis}
        </p>
      ) : null}

      {/*
        The blocker is itself not on the final invoice, so the suppression has lost its basis and the
        position may well be chargeable after all. The engine reports it instead of silently
        reinstating it, and a reviewer is exactly who should decide — so it is never behind the
        disclosure alone: the badge is also on the collapsed row.
      */}
      {entry.reconciled_with_final_invoice === false ? (
        <Badge variant="destructive" className="gap-1">
          <TriangleAlertIcon />
          Sperrgrund entfallen — manuell prüfen
        </Badge>
      ) : null}

      <div className="print:hidden">
        <ProofDialog
          ziffer={entry.ziffer}
          officialText={entry.official_text}
          steps={entry.proof ?? []}
        />
      </div>
    </div>
  )
}

/**
 * Positions the rules removed, and why.
 *
 * ## Grund is a badge, not a paragraph
 *
 * This column used to hold four things at once — the reason, what displaced the position, the
 * engine's prose explanation, and the rule id with its paragraph — stacked in a cell 440px wide. It
 * was the column a reviewer is here for and the one they could not read: seven rows of it is a wall
 * of German legal text with no two rows distinguishable at a glance.
 *
 * So the collapsed row carries exactly the distinction between one suppression and the next: the
 * short reason as a badge, plus the one flag that changes what a reviewer must do
 * (`reconciled_with_final_invoice: false`). Everything else — the full reason label with its
 * paragraph, the displacing Ziffer, the explanation, the rule id and the proof tree — is one click
 * away, in the row's own detail.
 *
 * **Expanded unconditionally on paper.** Whether a reader had clicked a row is a property of a
 * browsing session, not of the document; a printed proposal that omitted the reason a position was
 * suppressed would be exactly the misleading record this screen exists not to produce.
 *
 * The red stays restrained: a tinted Ziffer and a `destructive` badge, not a red table. A blocked
 * position is a normal, correct outcome of the rules — it is not an error, and a wall of red would
 * train a reviewer to dismiss the one row here that genuinely needs them.
 */
export function BlockedPositionsTable({ coding }: { coding: Coding }) {
  const blocked = coding.blocked_codes ?? []
  const detailId = React.useId()
  const [open, setOpen] = React.useState<ReadonlySet<string>>(() => new Set())

  function toggle(key: string) {
    setOpen((current) => {
      const next = new Set(current)
      if (!next.delete(key)) next.add(key)
      return next
    })
  }

  if (blocked.length === 0) {
    return (
      <Empty className="mx-6 border">
        <EmptyMedia variant="icon">
          <ShieldCheckIcon />
        </EmptyMedia>
        <EmptyTitle>Keine Position unterdrückt</EmptyTitle>
        <EmptyDescription>
          Keine der durchgesetzten Regeln hat eine Position entfernt. Bei unvollständiger
          Regelabdeckung heißt das nicht, dass keine zu entfernen gewesen wäre.
        </EmptyDescription>
      </Empty>
    )
  }

  return (
    <>
      <div className={TABLE_ONLY}>
        <Table className={EDGE_PADDING}>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className={HEAD}>Ziffer</TableHead>
              <TableHead className={cn(HEAD, "px-2")}>Beschreibung</TableHead>
              {/* Bounded, so the legend beside it gets every pixel the badges do not need. */}
              <TableHead className={cn(HEAD, "w-44 px-2")}>Grund</TableHead>
              <TableHead className={cn(HEAD, "w-10 text-right print:hidden")}>
                <span className="sr-only">Details</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {blocked.map((entry, index) => {
              const key = keyOf(entry, index)
              const expanded = open.has(key)
              const rowId = `${detailId}-${index}`

              return (
                <React.Fragment key={key}>
                  <TableRow
                    onClick={() => toggle(key)}
                    className={cn(
                      ROW,
                      "even:bg-muted/30 hover:bg-muted/60 cursor-pointer",
                      expanded && "bg-muted/60 even:bg-muted/60",
                    )}
                  >
                    <TableCell className="text-destructive align-middle font-mono text-sm font-medium">
                      {entry.ziffer}
                    </TableCell>
                    <TableCell className="w-full min-w-40 px-2 align-middle whitespace-normal">
                      <div className={cn("text-sm", CLAMP_2, WRAP)}>{entry.official_text || "—"}</div>
                    </TableCell>
                    <TableCell className="w-44 px-2 align-middle whitespace-normal">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="destructive">{BLOCKED_REASON_SHORT[entry.reason]}</Badge>
                        {entry.reconciled_with_final_invoice === false ? (
                          <Badge variant="destructive" className="gap-1">
                            <TriangleAlertIcon />
                            Sperrgrund entfallen
                          </Badge>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="px-2 text-right align-middle print:hidden">
                      {/*
                        No `onClick` of its own: a click here bubbles to the row, which owns the
                        toggle, and a keyboard Enter or Space on a button dispatches exactly that
                        click. Handling it in both places would toggle twice and appear to do nothing.
                      */}
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-controls={rowId}
                        aria-label={`Details zu GOÄ ${entry.ziffer} ${expanded ? "schließen" : "öffnen"}`}
                        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring cursor-pointer rounded p-1 focus-visible:ring-2 focus-visible:outline-none"
                      >
                        <ChevronDownIcon
                          aria-hidden
                          className={cn("size-4 transition-transform", expanded && "rotate-180")}
                        />
                      </button>
                    </TableCell>
                  </TableRow>

                  <TableRow
                    id={rowId}
                    className={cn(
                      "hover:bg-transparent",
                      expanded ? "bg-muted/30" : "hidden print:table-row",
                    )}
                  >
                    <TableCell colSpan={4} className="pt-0 pb-4 whitespace-normal">
                      <BlockedDetail entry={entry} />
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              )
            })}
          </TableBody>
        </Table>
      </div>

      <ul className={cn(CARDS_ONLY, "space-y-3 px-6")}>
        {blocked.map((entry, index) => (
          <li key={keyOf(entry, index)} className="border-destructive/30 rounded-2xl border p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-destructive font-mono text-sm font-medium">{entry.ziffer}</span>
              <Badge variant="destructive">{BLOCKED_REASON_SHORT[entry.reason]}</Badge>
            </div>
            <p className={cn("mt-2 text-sm", WRAP)}>{entry.official_text || "—"}</p>
            <div className="mt-3 border-t pt-3">
              <BlockedDetail entry={entry} />
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}
