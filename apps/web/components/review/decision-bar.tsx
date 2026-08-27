"use client"

import { Badge } from "@workspace/ui/components/badge"

import { PrintButton } from "@/components/review/print-button"
import { PROPOSAL_STATUS_LABEL, eur } from "@/lib/review/format"
import type { Proposal, ProposalStatus } from "@/lib/review/types"

const STATUS_VARIANT: Record<
  ProposalStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  DRAFT: "secondary",
  APPROVED: "default",
  REJECTED: "destructive",
  EXPORTED: "outline",
}

/**
 * What the reader is deciding, and the decision — kept on screen while they scroll.
 *
 * The actions used to sit in a card between the header and the tables, which meant that by the time
 * a reviewer had read the ninth position, the buttons, the status and the amount were all several
 * screens above them. Approving meant scrolling back up, and the thing being approved was no longer
 * visible at the moment of approval. On a screen whose entire purpose is a human approval boundary,
 * that is the wrong shape.
 *
 * So it is `sticky` under the top bar, and it carries the three things that have to be true at the
 * moment of the click: **which** proposal, **what** it comes to, and **what state** it is in.
 *
 * ## The amount is the hero, and it is on the left
 *
 * It was 20px, tucked beside a proposal id, and it lost every contest for attention on this screen
 * to the section headings around it. It is the number the physician is signing under and the only
 * figure on the page a reader can be said to have *come for*, so it is now 48px, bold, first in
 * reading order, and labelled — a bare figure that large is ambiguous about what it counts.
 *
 * Repeating it in the details card below is the one repetition on this screen that earns itself:
 * this copy is the one that has to be legible from the button at the moment of the decision, and it
 * is the only one still on screen once the reader has scrolled to the positions.
 *
 * ## Three tiers, not four equal buttons
 *
 * These were four buttons of the same size in two welded `ButtonGroup`s, and the welding was the
 * problem: approve and reject *are* one decision with two outcomes, but rendering them as two
 * halves of one control said they were equally likely, and an irreversible approval should not look
 * like a coin flip. So the group is gone and the weight carries the meaning instead.
 *
 * **Freigeben** is `lg` and filled blue — the only blue control on the screen. **Ablehnen** is `lg`
 * and a red outline: available, deliberate, visibly not the default. **Exportieren** and **Drucken**
 * are `sm` ghosts, because they are what you do *after* a decision rather than part of making one.
 * A rule between the two groups was the first version and it was redundant: a ghost control beside a
 * filled one is already visibly a different tier, and the hairline was one more mark on a bar whose
 * whole job is to stay out of the way of the number beside it.
 *
 * `ButtonGroup` also could not wrap — it is `w-fit` — so four buttons in it pushed the document 92px
 * past a 390px viewport. Plain flex rows wrap.
 *
 * Hidden from print. A sheet of paper has no buttons, and `position: sticky` is reprinted at the top
 * of every page by some engines.
 */
export function DecisionBar({
  proposal,
  decision,
  children,
}: {
  proposal: Proposal
  /** Approve and reject — one decision, two outcomes. */
  decision: React.ReactNode
  /** Everything that is not the decision: export. */
  children: React.ReactNode
}) {
  const status = proposal.status ?? "DRAFT"
  const total = proposal.solver_result.coding.total

  return (
    <div className="sticky top-14 z-10 -mx-4 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/80 sm:-mx-6 sm:px-6 print:hidden">
      <div className="flex min-h-20 flex-wrap items-center gap-x-8 gap-y-3 py-3">
        <div className="min-w-0">
          <div className="text-xs font-medium text-muted-foreground">
            Gesamtbetrag
          </div>
          <div className="mt-1 text-4xl leading-none font-bold tracking-tight tabular-nums sm:text-5xl">
            {eur(total?.amount_eur)}
          </div>
        </div>

        {/*
          Three siblings rather than two nested groups, and `ml-auto` on both of the trailing ones.
          On a wide screen the identity and the buttons are flushed right together, which is where
          they belong — the amount is the subject, they are what you do about it. On a phone the
          badge stays on the amount's own line instead of dragging the buttons up with it, and only
          the buttons wrap: four of them do not fit 390px and never will, but three stacked rows of
          sticky chrome above a scrolling invoice is most of the screen.
        */}
        <div className="ml-auto flex min-w-0 items-center gap-2">
          {/* Hidden on a phone: the amount and the status are what the button needs beside it. */}
          <span className="hidden truncate font-mono text-xs text-muted-foreground sm:inline">
            {proposal.proposal_id}
          </span>
          <Badge variant={STATUS_VARIANT[status]}>
            {PROPOSAL_STATUS_LABEL[status]}
          </Badge>
        </div>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
          <div className="flex items-center gap-1">
            {children}
            <PrintButton />
          </div>
          <div className="flex items-center gap-2">{decision}</div>
        </div>
      </div>
    </div>
  )
}
