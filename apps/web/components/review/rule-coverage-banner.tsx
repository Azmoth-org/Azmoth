"use client"

import { ScaleIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@workspace/ui/components/card"
import {
  Progress,
  ProgressLabel,
  ProgressValue,
} from "@workspace/ui/components/progress"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@workspace/ui/components/tooltip"
import { cn } from "@workspace/ui/lib/utils"

import type { Proposal } from "@/lib/review/types"

/**
 * `verified_share` as a fraction, or null when it is not a fraction.
 *
 * The engine publishes it as a display string — `"30/30"` — and a meter needs a number. Parsed here
 * rather than anywhere near the money: this is a count of *rules a human has reviewed*, not an
 * amount, so deriving a percentage from it invents nothing. Anything that does not match `a/b` with
 * `b > 0` returns null and the meter is not drawn, because a bar at an unknown position is worse
 * than no bar.
 */
function verifiedFraction(share: string | null | undefined): { done: number; total: number } | null {
  if (!share) return null
  const match = /^\s*(\d+)\s*\/\s*(\d+)\s*$/.exec(share)
  if (!match) return null
  const done = Number(match[1])
  const total = Number(match[2])
  if (!Number.isFinite(done) || !Number.isFinite(total) || total <= 0) return null
  return { done, total }
}

type Tone = "enforced" | "advisory" | "unverified" | "analog"

const TONE_COLOR: Record<Tone, string> = {
  enforced: "text-emerald-700 dark:text-emerald-400",
  advisory: "text-blue-700 dark:text-blue-400",
  unverified: "text-muted-foreground",
  analog: "text-amber-600 dark:text-amber-400",
}

/**
 * One figure of the coverage breakdown: the number, its label, and its caveat out of the way.
 *
 * The caveats are the substance of this card — "only these can suppress a position", "these could
 * but deliberately do not" — and they are also four sentences of German legal prose stacked under
 * four numbers, which is what made the previous version a paragraph wearing a grid. They move into a
 * tooltip, and they are rendered unconditionally on paper: a printed proposal that reduced the
 * coverage statement to four bare integers would be worse than one that omitted it.
 */
function Count({
  value,
  label,
  hint,
  tone,
}: {
  value: number
  label: string
  hint: string
  tone: Tone
}) {
  return (
    <div className="min-w-0">
      <Tooltip>
        <TooltipTrigger
          render={
            <div className="w-fit cursor-help">
              <div className={cn("text-2xl font-bold tabular-nums", TONE_COLOR[tone])}>{value}</div>
              <div className="text-muted-foreground mt-0.5 text-xs font-medium">{label}</div>
            </div>
          }
        />
        <TooltipContent side="bottom" className="max-w-xs text-left leading-relaxed">
          {hint}
        </TooltipContent>
      </Tooltip>
      <p className="text-muted-foreground mt-1 hidden text-xs print:block">{hint}</p>
    </div>
  )
}

/**
 * Rule coverage, stated rather than implied.
 *
 * The distinction this card exists to protect: **only `enforced_rule_count` can suppress a
 * position.** A reader who took the advisory number for "rules that were applied" would believe the
 * invoice had been checked against 862 rules when it was checked against 35.
 *
 * The advisory set is published as its two components, so this no longer has to hedge about what is
 * in it. They are advisory for different reasons and the card says which:
 * `suppressed_unverified_rule_count` rules *could* suppress a position and the current policy is not
 * letting them, while `analog_candidate_count` offers under § 6 Abs. 2 GOÄ never could.
 *
 * The counts are never summed here — the engine publishes the total.
 *
 * ## A card, not an alert
 *
 * It was an `Alert`, which is the component for something that has just gone wrong. This has not
 * gone wrong: it is a standing property of the system, present on every proposal, and dressing it as
 * an alert on every single one is how a reader learns to skip it. It is a card like the two beside
 * it, and the part that genuinely is a warning — the two paragraphs at the bottom — keeps a tinted
 * panel of its own.
 */
export function RuleCoverageBanner({ proposal }: { proposal: Proposal }) {
  const coverage = proposal.rule_coverage
  const enforced = coverage?.enforced_rule_count ?? proposal.enforced_rule_count ?? 0
  const advisory = coverage?.advisory_rule_count ?? proposal.advisory_rule_count ?? 0
  const suppressed =
    coverage?.suppressed_unverified_rule_count ?? proposal.suppressed_unverified_rule_count ?? 0
  const analogCandidates = coverage?.analog_candidate_count ?? proposal.analog_candidate_count ?? 0
  const policy = coverage?.policy_for_unverified_rules
  const ruleCoverage = coverage?.rule_coverage ?? proposal.solver_result.audit_trail.rule_coverage
  const verifiedShare = coverage?.verified_share
  const verified = verifiedFraction(verifiedShare)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-lg font-semibold">
          <ScaleIcon className="text-muted-foreground size-4 shrink-0" />
          <span>Regelabdeckung</span>
          {ruleCoverage ? (
            <Badge variant={ruleCoverage === "full" ? "default" : "destructive"}>
              {ruleCoverage === "full" ? "vollständig" : `unvollständig (${ruleCoverage})`}
            </Badge>
          ) : null}
          {policy ? (
            <Badge variant="outline" className="font-mono">
              policy: {policy}
            </Badge>
          ) : null}
          {verifiedShare && !verified ? (
            <Badge variant="outline" className="font-mono">
              verifiziert: {verifiedShare}
            </Badge>
          ) : null}
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-6">
        {/*
          The share of the *manually verified* rule set that has been reviewed — not the share of the
          GOÄ that is covered. Those are different numbers and confusing them is the whole reason
          this card exists, so the label says which one this is.
        */}
        {verified ? (
          <Progress value={(verified.done / verified.total) * 100} className="max-w-md">
            <ProgressLabel className="text-foreground text-xs font-medium">
              Manuell verifizierte Regeln geprüft
            </ProgressLabel>
            {/*
              A render function, because that is what Base UI's `ProgressValue` takes. Its argument
              is the formatted percentage, which is deliberately ignored: "30/30" says how many rules
              a human actually reviewed, and "100 %" would read as a claim about GOÄ coverage — the
              exact confusion this card exists to prevent.
            */}
            <ProgressValue className="text-xs tabular-nums">
              {() => `${verified.done}/${verified.total}`}
            </ProgressValue>
          </Progress>
        ) : null}

        <div className="grid grid-cols-2 gap-6 lg:grid-cols-4">
          <Count
            value={enforced}
            label="durchgesetzt"
            hint="Nur diese Regeln können eine Position unterdrücken."
            tone="enforced"
          />
          <Count
            value={advisory}
            label="nur beratend"
            hint="Unterdrücken keine Position. Summe der beiden folgenden Gruppen."
            tone="advisory"
          />
          <Count
            value={suppressed}
            label="nicht verifiziert"
            hint={
              policy
                ? `Könnten eine Position unterdrücken, tun es unter Policy „${policy}“ aber bewusst nicht: kein Mensch hat sie geprüft.`
                : "Könnten eine Position unterdrücken, tun es aber bewusst nicht: kein Mensch hat sie geprüft."
            }
            tone="unverified"
          />
          <Count
            value={analogCandidates}
            label="Analogkandidaten"
            hint="Angebote nach § 6 Abs. 2 GOÄ. Könnten eine Position nie unterdrücken — unabhängig von der Policy."
            tone="analog"
          />
        </div>

        <div className="bg-muted/40 space-y-2 rounded-2xl border p-4 text-sm print:rounded-lg">
          <p>
            <strong>Die Regelabdeckung ist unvollständig.</strong> Die Engine setzt eine Teilmenge der
            GOÄ durch. Die nicht verifizierten Regeln wurden automatisch aus dem Verordnungstext
            extrahiert und sind ungeprüft; sie blockieren daher nicht. Ein fehlender Befund bedeutet
            somit <strong>nicht</strong>, dass eine Position geprüft und bestätigt wurde.
          </p>
          <p>
            <strong>Die ärztliche Prüfung ist zwingend erforderlich.</strong> Insbesondere das
            Zielleistungsprinzip (§ 4 Abs. 2a GOÄ) ist nur mit wenigen, manuell verifizierten
            Regelpaaren abgedeckt.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
