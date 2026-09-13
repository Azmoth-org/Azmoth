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

/** `"1 Beweiszeile"` / `"6 Beweiszeilen"` — never a bare, unlabelled count like `"(6)"`. */
export function proofLineCountLabel(count: number): string {
  return `${count} ${count === 1 ? "Beweiszeile" : "Beweiszeilen"}`
}

/**
 * The proof tree for one position — the machine-checkable answer to "why is this on my bill?".
 *
 * Every step carries the Datalog rule that produced it, the rule id joining back to the exact CSV
 * row, and the paragraph of the GOÄ it rests on. The steps are rendered as a list *and* as raw JSON:
 * the list is what a reviewer reads, the JSON is what an auditor copies, and neither is derived from
 * the other.
 *
 * The trigger used to be an icon plus a bare `(6)` — a count with nothing to say what it counted,
 * discoverable only by a screen reader reading an `aria-label` a sighted user never saw. It now
 * reads `"6 Beweiszeilen"` for anyone looking at the screen, in `compact` position tables too: the
 * word costs the column some width, but a control nobody notices is worth less than the width it
 * saved. Zero steps renders no dialog at all — there is nothing to open — but still names what is
 * missing, `"Keine Beweiszeilen für diesen Eintrag."`, rather than a disabled, silent button.
 */
export function ProofDialog({
  ziffer,
  officialText,
  steps,
  compact = false,
}: {
  ziffer: string
  officialText?: string
  steps: readonly ProofStep[]
  compact?: boolean
}) {
  if (steps.length === 0) {
    return (
      <span className="text-xs text-muted-foreground">
        Keine Beweiszeilen für diesen Eintrag.
      </span>
    )
  }

  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="xs"
            className={compact ? "px-1.5" : undefined}
          >
            <FileSearchIcon />
            <span className="tabular-nums">
              {proofLineCountLabel(steps.length)}
            </span>
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
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {index + 1}.
                  </span>
                  <span className="font-mono text-sm font-medium">
                    {step.rule}
                  </span>
                  {step.rule_id ? (
                    <Badge variant="outline" className="font-mono">
                      {step.rule_id}
                    </Badge>
                  ) : null}
                  {step.legal_basis ? (
                    <Badge variant="secondary">{step.legal_basis}</Badge>
                  ) : null}
                </div>
                {step.detail ? (
                  <div className="mt-1 font-mono text-xs break-words text-muted-foreground">
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
