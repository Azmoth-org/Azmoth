"use client"

import * as React from "react"
import { CheckCircle2Icon } from "lucide-react"

import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"
import { Input } from "@workspace/ui/components/input"
import { Label } from "@workspace/ui/components/label"
import { Textarea } from "@workspace/ui/components/textarea"

import { submitRuleProposal } from "@/lib/rules/client"
import type { ReviewError } from "@/lib/review/types"

//: Matches `MAX_CONTEXT_LENGTH` in the engine's `app/schemas/rule_proposals.py` — kept here rather
//: than imported so the textarea's own counter never depends on a generated contract being current.
const MAX_CONTEXT_LENGTH = 500

/**
 * "Regel fehlt? Ziffer melden" — a pilot reporting that a Ziffer has no rule at all.
 *
 * Deliberately the simplest dialog in this directory. There is no verdict to weigh and no evidence
 * to show, unlike `ReviewDialog`: this is a suggestion box with one required fact (which Ziffer)
 * and one required sentence (what was expected), and the only outcome is a thank-you. It does not
 * touch the running engine, the rule store or the report on screen — see `app.api.rules.propose_rule`.
 *
 * `ziffer` starts prefilled from whichever position the caller opened it from, but stays an
 * editable field: a pilot who noticed a gap while reading a report, rather than at one specific
 * position, still needs somewhere to type the number by hand.
 */
export function ZifferReportDialog({
  open,
  onOpenChange,
  initialZiffer = "",
  receiptHash,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialZiffer?: string
  receiptHash?: string
}) {
  const [ziffer, setZiffer] = React.useState(initialZiffer)
  const [context, setContext] = React.useState("")
  const [pending, setPending] = React.useState(false)
  const [error, setError] = React.useState<ReviewError | null>(null)
  const [done, setDone] = React.useState(false)

  // Reset to a clean form every time the dialog opens — including re-opening it from a different
  // row, which must not show the previous row's context text under a new Ziffer.
  React.useEffect(() => {
    if (!open) return
    setZiffer(initialZiffer)
    setContext("")
    setError(null)
    setDone(false)
  }, [open, initialZiffer])

  const canSubmit =
    !pending && ziffer.trim().length > 0 && context.trim().length > 0

  async function submit() {
    if (!canSubmit) return
    setPending(true)
    setError(null)
    const result = await submitRuleProposal({
      ziffer: ziffer.trim(),
      context: context.trim(),
      receipt_hash: receiptHash ?? null,
    })
    setPending(false)
    if (result.kind === "error") {
      setError(result.error)
      return
    }
    setDone(true)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Regel fehlt? Ziffer melden</DialogTitle>
          <DialogDescription>
            Melden Sie eine GOÄ-Ziffer, für die diese Prüfung noch keine Regel
            kennt. Die Meldung geht an das Team, das die Regelabdeckung
            erweitert.
          </DialogDescription>
        </DialogHeader>

        {done ? (
          <>
            <div className="flex items-start gap-3 py-2">
              <CheckCircle2Icon
                className="mt-0.5 text-green-600 dark:text-green-500"
                aria-hidden
              />
              <p className="text-sm">
                Danke — Ihre Meldung hilft, die Abdeckung zu erweitern.
              </p>
            </div>
            <DialogFooter>
              <DialogClose
                render={<Button type="button">Schließen</Button>}
              />
            </DialogFooter>
          </>
        ) : (
          <>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor="ziffer-report-ziffer">
                  Ziffer <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="ziffer-report-ziffer"
                  value={ziffer}
                  onChange={(event) => setZiffer(event.target.value)}
                  placeholder="z. B. 34"
                  className="max-w-32 font-mono"
                  autoComplete="off"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="ziffer-report-context">
                  Was fehlt? <span className="text-destructive">*</span>
                </Label>
                <Textarea
                  id="ziffer-report-context"
                  value={context}
                  onChange={(event) =>
                    setContext(event.target.value.slice(0, MAX_CONTEXT_LENGTH))
                  }
                  rows={4}
                  placeholder="Was hätte die Prüfung hier erkennen oder verhindern sollen?"
                />
                <p className="text-right text-xs text-muted-foreground">
                  {context.length}/{MAX_CONTEXT_LENGTH}
                </p>
              </div>

              {error ? (
                <p className="text-sm text-destructive">{error.message}</p>
              ) : null}
            </div>

            <DialogFooter>
              <DialogClose
                render={
                  <Button type="button" variant="ghost">
                    Abbrechen
                  </Button>
                }
              />
              <Button
                type="button"
                disabled={!canSubmit}
                onClick={() => void submit()}
              >
                {pending ? "Wird gesendet…" : "Melden"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
