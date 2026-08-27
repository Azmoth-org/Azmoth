"use client"

import * as React from "react"
import { CheckCircle2Icon, XCircleIcon } from "lucide-react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Badge } from "@workspace/ui/components/badge"
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

import {
  KIND,
  ROLE_LABEL,
  directionLabel,
  sourceLabel,
} from "@/lib/rules/format"
import type { ReviewableRule } from "@/lib/rules/client"

/**
 * The decision dialog: the full rule, and two buttons that mean opposite things.
 *
 * It shows the GOÄ sentence in full and does not truncate it, because that sentence is the entire
 * basis for the decision. A dialog that showed "excl_auto_30_4 · Ausschluss · GOÄ 30 / GOÄ 4" and
 * two buttons would be asking for a rubber stamp, and a rubber-stamped rule enforces against real
 * invoices exactly as hard as a carefully checked one.
 *
 * `reviewed_by` is required for both decisions, for the same reason `approved_by` is on an
 * approval: verifying a rule changes what every future audit concludes about somebody's billing.
 * It is recorded, not authenticated — there is no login in front of any of this.
 */
export function ReviewDialog({
  rule,
  open,
  pending,
  onOpenChange,
  onDecide,
}: {
  rule: ReviewableRule | null
  open: boolean
  pending: boolean
  onOpenChange: (open: boolean) => void
  onDecide: (
    rule: ReviewableRule,
    status: "VERIFIED" | "REJECTED" | "PENDING",
    reviewedBy: string,
    notes: string
  ) => Promise<void>
}) {
  const [reviewedBy, setReviewedBy] = React.useState("")
  const [notes, setNotes] = React.useState("")

  // The name persists between rules on purpose: a reviewer works a queue of hundreds in one
  // sitting, and retyping their own name each time is friction with no integrity benefit. The
  // notes do not — they belong to one rule.
  React.useEffect(() => {
    if (rule) setNotes(rule.review_notes ?? "")
  }, [rule])

  if (!rule) return null

  const presentation = KIND[rule.kind]
  const named = reviewedBy.trim().length > 0
  const busy = pending
  // `detail` is `{ [key: string]: unknown }` in the generated contract — it is deliberately
  // open-ended so a new rule type does not widen the model for every other one. Narrowed here,
  // at the one place that renders it, rather than by loosening the contract.
  const detail = (rule.detail ?? {}) as Record<string, string | undefined>
  const direction = detail.direction
  const maxFactor = detail.max_factor

  async function decide(status: "VERIFIED" | "REJECTED" | "PENDING") {
    if (!rule) return
    if (status !== "PENDING" && !named) return
    await onDecide(rule, status, reviewedBy.trim(), notes.trim())
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm">{rule.rule_id}</span>
            <Badge className={presentation.className}>
              {presentation.label}
            </Badge>
          </DialogTitle>
          <DialogDescription>{presentation.hint}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs sm:grid-cols-3">
            {Object.entries(rule.ziffer_roles ?? {}).map(([role, ziffer]) =>
              ziffer ? (
                <div key={role}>
                  <div className="text-muted-foreground">
                    {ROLE_LABEL[role] ?? role}
                  </div>
                  <div className="font-mono text-sm">GOÄ {ziffer}</div>
                </div>
              ) : null
            )}
            {direction ? (
              <div>
                <div className="text-muted-foreground">Richtung</div>
                <div className="font-mono text-sm">
                  {directionLabel(direction)}
                </div>
              </div>
            ) : null}
            {maxFactor ? (
              <div>
                <div className="text-muted-foreground">Höchstfaktor</div>
                <div className="font-mono text-sm">{maxFactor}</div>
              </div>
            ) : null}
            <div className="col-span-2 sm:col-span-3">
              <div className="text-muted-foreground">Herkunft</div>
              {/* `break-words`, not `break-all`: the value is prose with one token in it, and
                  `break-all` splits "automatisch extrahiert" across lines mid-word. */}
              <div className="font-mono text-sm break-words">
                {sourceLabel(rule.source)}
              </div>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <div className="text-muted-foreground">Rechtsgrundlage</div>
              <div className="text-sm">{rule.legal_basis || "—"}</div>
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">
              Quelltext, aus dem die Regel extrahiert wurde
            </div>
            {/* Never truncated. This sentence is the decision. */}
            <blockquote className="rounded-md border-l-2 border-border bg-muted/40 p-3 text-sm">
              {rule.quote || (
                <span className="text-muted-foreground italic">
                  Kein Quelltext hinterlegt — ohne Beleg lässt sich diese Regel
                  nicht verifizieren.
                </span>
              )}
            </blockquote>
          </div>

          <div className="space-y-2">
            <Label htmlFor="reviewed-by">
              Geprüft von <span className="text-destructive">*</span>
            </Label>
            <Input
              id="reviewed-by"
              value={reviewedBy}
              onChange={(event) => setReviewedBy(event.target.value)}
              placeholder="Name der prüfenden Person"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              Pflichtfeld für Verifizieren und Ablehnen. Der Name wird
              protokolliert, aber technisch nicht überprüft.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="review-notes">
              Notiz (optional, aber sehr erwünscht)
            </Label>
            <Textarea
              id="review-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={3}
              placeholder="z. B. „Anmerkung zu Nr. 4 gelesen — Extraktion trifft zu, Richtung stimmt.“"
            />
          </div>

          <Alert>
            <AlertTitle>
              Eine Verifizierung wirkt sofort auf alle künftigen Prüfungen
            </AlertTitle>
            <AlertDescription>
              Eine verifizierte Regel kann ab sofort Positionen entfernen und
              verschiebt Beträge aus der Gruppe <strong>unbestätigt</strong>.
              Eine abgelehnte Regel wird unter keiner Policy mehr durchgesetzt.
              Beides ist korrigierbar — die Entscheidung kann später geändert
              werden.
            </AlertDescription>
          </Alert>
        </div>

        <DialogFooter className="flex-wrap gap-2">
          <DialogClose
            render={
              <Button type="button" variant="ghost">
                Abbrechen
              </Button>
            }
          />
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => void decide("PENDING")}
          >
            Zurückstellen
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={busy || !named}
            onClick={() => void decide("REJECTED")}
          >
            <XCircleIcon />
            Regel ablehnen
          </Button>
          <Button
            type="button"
            disabled={busy || !named}
            onClick={() => void decide("VERIFIED")}
          >
            <CheckCircle2Icon />
            {busy ? "Wird gespeichert…" : "Regel verifizieren"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
