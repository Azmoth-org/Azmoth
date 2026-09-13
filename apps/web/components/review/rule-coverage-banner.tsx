"use client"

import { ScaleIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"
import { Progress, ProgressLabel } from "@workspace/ui/components/progress"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@workspace/ui/components/tooltip"
import { cn } from "@workspace/ui/lib/utils"

import {
  RULE_COVERAGE_HINT,
  RULE_COVERAGE_LABEL,
  ruleCoverageHeadline,
  timestamp,
  type RuleCoverageTone,
} from "@/lib/review/format"
import type { Proposal } from "@/lib/review/types"

type Tone = RuleCoverageTone

const TONE_COLOR: Record<Tone, string> = {
  enforced: "text-emerald-700",
  advisory: "text-azm-indigo-deep",
  unverified: "text-muted-foreground",
  analog: "text-amber-600",
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
  size = "lg",
}: {
  value: number
  label: string
  hint: string
  tone: Tone
  /** `"sm"` for a count nested under another one — visually a "davon" of the tile above it. */
  size?: "lg" | "sm"
}) {
  return (
    <div className="min-w-0">
      <Tooltip>
        <TooltipTrigger
          render={
            <div className="w-fit cursor-help">
              <div
                className={cn(
                  "font-bold tabular-nums",
                  size === "lg" ? "text-2xl" : "text-lg",
                  TONE_COLOR[tone]
                )}
              >
                {value}
              </div>
              <div className="mt-0.5 text-xs font-medium text-muted-foreground">
                {label}
              </div>
            </div>
          }
        />
        <TooltipContent
          side="bottom"
          className="max-w-xs text-left leading-relaxed"
        >
          {hint}
        </TooltipContent>
      </Tooltip>
      <p className="mt-1 hidden text-xs text-muted-foreground print:block">
        {hint}
      </p>
    </div>
  )
}

/**
 * Rule coverage, stated rather than implied.
 *
 * The distinction this card exists to protect: **only `enforced_rule_count` can suppress a
 * position.** A reader who took the advisory number for "rules that were applied" would believe the
 * invoice had been checked against every rule the engine holds, when it was checked against the
 * enforced subset.
 *
 * `advisory_rule_count` is not a fifth number: it is `suppressed_unverified_rule_count +
 * analog_candidate_count`, by construction on the engine (`rule_coverage.py`). The two are rendered
 * nested under it — "davon" — rather than as peers in the same row, because a flat row of "944 / 9 /
 * 6 / 3" invites adding 9 back into 944 or reading 6 and 3 as disjoint from 9, and both readings are
 * wrong. Nesting them is what makes the sum unrepresentable rather than merely undocumented.
 *
 * The headline metric — "944 von 980 Regeln durchgesetzt" — reads `enforced_rule_count` and
 * `total_constraint_rule_count` directly off `RuleCoverage` rather than through `verified_share`.
 * The engine builds that string as `f"{enforced_rule_count}/{total_constraint_rule_count}"`
 * (`rule_store.py`), so it is the same two counts one indirection removed; reading the fields
 * directly means a future change to the string's shape cannot desynchronise the label from the bar.
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
  const enforced =
    coverage?.enforced_rule_count ?? proposal.enforced_rule_count ?? 0
  const advisory =
    coverage?.advisory_rule_count ?? proposal.advisory_rule_count ?? 0
  const suppressed =
    coverage?.suppressed_unverified_rule_count ??
    proposal.suppressed_unverified_rule_count ??
    0
  const analogCandidates =
    coverage?.analog_candidate_count ?? proposal.analog_candidate_count ?? 0
  const totalConstraintRules = coverage?.total_constraint_rule_count ?? 0
  const policy = coverage?.policy_for_unverified_rules
  const ruleCoverage =
    coverage?.rule_coverage ?? proposal.solver_result.audit_trail.rule_coverage

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-lg font-semibold">
          <ScaleIcon className="size-4 shrink-0 text-muted-foreground" />
          <span>Regelabdeckung</span>
          {ruleCoverage ? (
            <Badge
              variant={ruleCoverage === "full" ? "default" : "destructive"}
            >
              {ruleCoverage === "full"
                ? "vollständig"
                : `unvollständig (${ruleCoverage})`}
            </Badge>
          ) : null}
          {policy ? (
            <Badge variant="outline" className="font-mono">
              policy: {policy}
            </Badge>
          ) : null}
        </CardTitle>
        <CardDescription>
          Durchgesetzte Regeln aus dem aktuellen Regelsatz ·{" "}
          {/* `created_at` is the timestamp the whole proposal — and the rule counts above — were
              produced under; every rule count on this card must carry a visible as-of date. */}
          Stand: {timestamp(proposal.created_at)}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {totalConstraintRules > 0 ? (
          <Progress
            value={(enforced / totalConstraintRules) * 100}
            className="max-w-md"
          >
            <ProgressLabel className="text-xs font-medium text-foreground">
              {ruleCoverageHeadline(enforced, totalConstraintRules)}
            </ProgressLabel>
          </Progress>
        ) : null}

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <Count
            value={enforced}
            label={RULE_COVERAGE_LABEL.enforced}
            hint={RULE_COVERAGE_HINT.enforced}
            tone="enforced"
          />
          <div className="space-y-3">
            <Count
              value={advisory}
              label={RULE_COVERAGE_LABEL.advisory}
              hint={RULE_COVERAGE_HINT.advisory}
              tone="advisory"
            />
            {/*
              "Davon" — a share of the tile above, not two more buckets beside it. Indented and
              rail-marked so the hierarchy survives even where the tooltip and the print paragraph
              (identical text) are not: `advisory` is the sum of exactly these two.
            */}
            <div className="grid grid-cols-2 gap-4 border-l-2 border-border py-0.5 pl-4">
              <Count
                value={suppressed}
                label={RULE_COVERAGE_LABEL.unverified}
                hint={RULE_COVERAGE_HINT.unverified}
                tone="unverified"
                size="sm"
              />
              <Count
                value={analogCandidates}
                label={RULE_COVERAGE_LABEL.analog}
                hint={RULE_COVERAGE_HINT.analog}
                tone="analog"
                size="sm"
              />
            </div>
          </div>
        </div>

        <div className="space-y-2 rounded-2xl border bg-muted/40 p-4 text-sm print:rounded-lg">
          <p>
            <strong>Die Regelabdeckung ist unvollständig.</strong> Die Engine
            setzt eine Teilmenge der GOÄ durch. Die nicht verifizierten Regeln
            wurden automatisch aus dem Verordnungstext extrahiert und sind
            ungeprüft; sie blockieren daher nicht. Ein fehlender Befund bedeutet
            somit <strong>nicht</strong>, dass eine Position geprüft und
            bestätigt wurde.
          </p>
          <p>
            <strong>Die ärztliche Prüfung ist zwingend erforderlich.</strong>{" "}
            Insbesondere das Zielleistungsprinzip (§ 4 Abs. 2a GOÄ) ist nur mit
            wenigen, manuell verifizierten Regelpaaren abgedeckt.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
