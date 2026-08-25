"use client"

import { Badge } from "@workspace/ui/components/badge"
import { ButtonGroup } from "@workspace/ui/components/button-group"

import { PrintButton } from "@/components/review/print-button"
import { PROPOSAL_STATUS_LABEL, eur } from "@/lib/review/format"
import type { Proposal, ProposalStatus } from "@/lib/review/types"

const STATUS_VARIANT: Record<ProposalStatus, "default" | "secondary" | "destructive" | "outline"> = {
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
 * moment of the click: **which** proposal, **what** it comes to, and **what state** it is in. The
 * amount is repeated from the header deliberately — this is the one repetition on the screen that
 * earns itself, because it is the number being signed for and it must be legible from the button.
 *
 * **Two `ButtonGroup`s rather than one, or four loose buttons.** Approve and reject are one decision
 * with two outcomes and belong welded together; export and print are what you do *after* a decision
 * and are a separate control. One group of four was the first version and it does not fit a phone —
 * `ButtonGroup` is `w-fit` and does not wrap, so four buttons pushed the document 92px wider than
 * the viewport at 390px. Two groups wrap onto two lines instead, which is also the truer grouping.
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
    <div className="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-14 z-10 -mx-4 border-b px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 print:hidden">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-baseline gap-3">
          <span className="shrink-0 text-xl font-semibold tabular-nums">
            {eur(total?.amount_eur)}
          </span>
          {/* Hidden on a phone: the amount and the status are what the button needs beside it. */}
          <span className="text-muted-foreground hidden truncate font-mono text-xs sm:inline">
            {proposal.proposal_id}
          </span>
        </div>

        <Badge variant={STATUS_VARIANT[status]}>{PROPOSAL_STATUS_LABEL[status]}</Badge>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <ButtonGroup>{decision}</ButtonGroup>
          <ButtonGroup>
            {children}
            <PrintButton />
          </ButtonGroup>
        </div>
      </div>
    </div>
  )
}
