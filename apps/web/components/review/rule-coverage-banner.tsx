import { ScaleIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Badge } from "@workspace/ui/components/badge"

import type { Proposal } from "@/lib/review/types"

function Count({
  value,
  label,
  hint,
  tone,
}: {
  value: number
  label: string
  hint: string
  tone: "enforced" | "advisory" | "unverified"
}) {
  const color =
    tone === "enforced"
      ? "text-foreground"
      : tone === "unverified"
        ? "text-destructive"
        : "text-muted-foreground"

  return (
    <div className="min-w-0">
      <div className={`text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      <div className="text-sm font-medium">{label}</div>
      <div className="text-muted-foreground text-xs">{hint}</div>
    </div>
  )
}

/**
 * Rule coverage, stated rather than implied.
 *
 * The distinction this banner exists to protect: **only `enforced_rule_count` can suppress a
 * position.** A reader who took the advisory number for "rules that were applied" would believe the
 * invoice had been checked against 862 rules when it was checked against 35.
 *
 * The advisory set is now published as its two components, so this no longer has to hedge about
 * what is in it. They are advisory for different reasons and the banner says which:
 * `suppressed_unverified_rule_count` rules *could* suppress a position and the current policy is
 * not letting them, while `analog_candidate_count` offers under § 6 Abs. 2 GOÄ never could.
 *
 * The counts are never summed here — the engine publishes the total.
 */
export function RuleCoverageBanner({ proposal }: { proposal: Proposal }) {
  const coverage = proposal.rule_coverage
  const enforced = coverage?.enforced_rule_count ?? proposal.enforced_rule_count ?? 0
  const advisory = coverage?.advisory_rule_count ?? proposal.advisory_rule_count ?? 0
  const suppressed =
    coverage?.suppressed_unverified_rule_count ?? proposal.suppressed_unverified_rule_count ?? 0
  const analogCandidates =
    coverage?.analog_candidate_count ?? proposal.analog_candidate_count ?? 0
  const policy = coverage?.policy_for_unverified_rules
  const ruleCoverage = coverage?.rule_coverage ?? proposal.solver_result.audit_trail.rule_coverage
  const verifiedShare = coverage?.verified_share

  return (
    <Alert>
      <ScaleIcon />
      <AlertTitle className="flex flex-wrap items-center gap-2">
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
        {verifiedShare ? (
          <Badge variant="outline" className="font-mono">
            verifiziert: {verifiedShare}
          </Badge>
        ) : null}
      </AlertTitle>
      <AlertDescription className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
            tone="advisory"
          />
        </div>

        <div className="text-foreground/80 space-y-2">
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
      </AlertDescription>
    </Alert>
  )
}
