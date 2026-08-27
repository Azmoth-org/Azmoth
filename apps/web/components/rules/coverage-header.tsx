"use client"

import { CircleCheckIcon, CircleHelpIcon, CircleSlashIcon } from "lucide-react"

import { Card, CardContent } from "@workspace/ui/components/card"

import { progressPercent } from "@/lib/rules/format"
import type { RuleCoverage } from "@/lib/rules/client"

/**
 * "X von 894 Regeln verifiziert", and what the rest of them are.
 *
 * The bar has three segments rather than one, and that is the honest shape of the work: verified
 * (enforced), rejected (decided, and correctly never enforced), and undecided (the backlog). A
 * single "progress" bar would count a rejection as progress towards enforcement, which it is not —
 * and would count it as *nothing*, which it also is not. It is a decision that shrank the queue.
 *
 * The denominator excludes Analogansatz candidates. They are offers under § 6 Abs. 2 GOÄ and can
 * never remove a position from an invoice, so there is nothing for a reviewer to make safe and
 * padding the backlog with them would misstate how much work is left.
 */
export function CoverageHeader({
  coverage,
  pendingCount,
}: {
  coverage: RuleCoverage
  /** The live queue length. Falls back to the coverage's own figure before the first load. */
  pendingCount?: number
}) {
  const total = coverage.total_constraint_rule_count ?? 0
  const verified = coverage.enforced_rule_count ?? 0
  const rejected = coverage.rejected_rule_count ?? 0
  const pending = pendingCount ?? coverage.unverified_rule_count ?? 0

  const verifiedWidth = progressPercent(verified, total)
  const rejectedWidth = progressPercent(rejected, total)

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-sm font-medium">
            <span className="text-lg font-semibold tabular-nums">
              {verified}
            </span>
            <span className="text-muted-foreground">
              {" "}
              / {total} Regeln verifiziert
            </span>
          </span>
          <span className="text-xs text-muted-foreground tabular-nums">
            davon {coverage.review_verified_rule_count ?? 0} über diese
            Prüfliste
          </span>
        </div>

        <div
          className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted"
          role="img"
          aria-label={
            `${verified} von ${total} Regeln verifiziert, ${rejected} abgelehnt, ` +
            `${pending} noch offen.`
          }
        >
          {verifiedWidth > 0 ? (
            <div
              className="bg-emerald-600 dark:bg-emerald-500"
              style={{ width: `${verifiedWidth}%` }}
            />
          ) : null}
          {rejectedWidth > 0 ? (
            <div
              className="bg-muted-foreground/50"
              style={{ width: `${rejectedWidth}%` }}
            />
          ) : null}
        </div>

        <div className="grid grid-cols-1 gap-4 text-xs sm:grid-cols-3">
          <Figure
            icon={CircleCheckIcon}
            tone="text-emerald-700 dark:text-emerald-400"
            value={verified}
            label="durchgesetzt"
            hint="Können eine Position entfernen. Die verifizierten CSV-Regeln plus alles, was hier freigegeben wurde."
          />
          <Figure
            icon={CircleHelpIcon}
            tone="text-amber-700 dark:text-amber-400"
            value={pending}
            label="offen"
            hint="Maschinell aus dem Verordnungstext extrahiert und von niemandem geprüft. Blockieren nichts — und sind der Grund für die Gruppe „unbestätigt“ in jeder Prüfung."
          />
          <Figure
            icon={CircleSlashIcon}
            tone="text-muted-foreground"
            value={rejected}
            label="abgelehnt"
            hint="Von einem Menschen gelesen und verworfen. Werden unter keiner Policy durchgesetzt — auch nicht unter „block“."
          />
        </div>

        <p className="text-xs text-muted-foreground">
          Jede hier verifizierte Regel verschiebt in künftigen Prüfungen Beträge
          aus <strong>unbestätigt</strong> in eine Gruppe, zu der die Engine
          eine Aussage treffen kann. Genau dafür ist diese Liste da.
          Analogkandidaten (§ 6 Abs. 2 GOÄ) sind nicht enthalten: sie sind ein
          Angebot und können nie eine Position entfernen.
        </p>
      </CardContent>
    </Card>
  )
}

function Figure({
  icon: Icon,
  tone,
  value,
  label,
  hint,
}: {
  icon: typeof CircleCheckIcon
  tone: string
  value: number
  label: string
  hint: string
}) {
  return (
    <div className="space-y-1">
      <div className={`flex items-center gap-1.5 font-medium ${tone}`}>
        <Icon className="size-3.5 shrink-0" aria-hidden />
        <span className="text-base tabular-nums">{value}</span>
        <span>{label}</span>
      </div>
      <p className="text-muted-foreground">{hint}</p>
    </div>
  )
}
