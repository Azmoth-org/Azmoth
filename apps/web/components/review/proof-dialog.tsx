"use client"

import { FileSearchIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@workspace/ui/components/dialog"

import { RawJson } from "@/components/review/raw-json"
import type { ProofStep } from "@/lib/review/types"

/**
 * The proof tree for one position — the machine-checkable answer to "why is this on my bill?".
 *
 * Every step carries the Datalog rule that produced it, the rule id joining back to the exact CSV
 * row, and the paragraph of the GOÄ it rests on. The steps are rendered as a list *and* as raw JSON:
 * the list is what a reviewer reads, the JSON is what an auditor copies, and neither is derived from
 * the other.
 */
export function ProofDialog({
  ziffer,
  officialText,
  steps,
  triggerLabel = "Beweis",
}: {
  ziffer: string
  officialText?: string
  steps: readonly ProofStep[]
  triggerLabel?: string
}) {
  const hasSteps = steps.length > 0

  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button variant="ghost" size="xs" disabled={!hasSteps}>
            <FileSearchIcon />
            {triggerLabel}
            {hasSteps ? <span className="tabular-nums">({steps.length})</span> : null}
          </Button>
        }
      />
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="font-mono">GOÄ {ziffer}</DialogTitle>
          <DialogDescription>
            {officialText ? officialText : "Beweisbaum der Regel-Engine."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <ol className="space-y-2">
            {steps.map((step, index) => (
              <li
                key={`${step.rule}-${step.detail ?? ""}-${index}`}
                className="rounded-lg border p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-muted-foreground text-xs tabular-nums">{index + 1}.</span>
                  <span className="font-mono text-sm font-medium">{step.rule}</span>
                  {step.rule_id ? (
                    <Badge variant="outline" className="font-mono">
                      {step.rule_id}
                    </Badge>
                  ) : null}
                  {step.legal_basis ? <Badge variant="secondary">{step.legal_basis}</Badge> : null}
                </div>
                {step.detail ? (
                  <div className="text-muted-foreground mt-1 font-mono text-xs break-words">
                    {step.detail}
                  </div>
                ) : null}
              </li>
            ))}
          </ol>

          <RawJson value={steps} label="Rohdaten (proof)" />
        </div>
      </DialogContent>
    </Dialog>
  )
}
