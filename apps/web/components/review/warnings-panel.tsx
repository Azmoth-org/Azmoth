import {
  AlertTriangleIcon,
  InfoIcon,
  OctagonAlertIcon,
  TimerOffIcon,
} from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from "@workspace/ui/components/empty"

import { ExpandableItem } from "@/components/review/expandable-item"
import {
  SEVERITY_LABEL,
  bySeverity,
  isProminentWarning,
  warningTitle,
} from "@/lib/review/format"
import type { EngineWarning, WarningSeverity } from "@/lib/review/types"

const SEVERITY_BADGE_VARIANT: Record<
  WarningSeverity,
  "destructive" | "secondary" | "outline"
> = {
  error: "destructive",
  warning: "secondary",
  info: "outline",
}

function SeverityIcon({
  severity,
  timeout,
}: {
  severity: WarningSeverity
  timeout: boolean
}) {
  if (timeout) return <TimerOffIcon className="text-destructive" />
  if (severity === "error")
    return <OctagonAlertIcon className="text-destructive" />
  if (severity === "warning") {
    return <AlertTriangleIcon className="text-amber-600 dark:text-amber-400" />
  }
  return <InfoIcon className="text-azm-indigo-deep dark:text-azm-indigo-subdued" />
}

/**
 * Every warning the engine emitted, in order of how much a reviewer needs to see it.
 *
 * `solver_timeout_partial` is the one that must never be scrolled past: it means the optimiser was
 * cancelled and the returned model is the best found so far, not a proven optimum. Every hard rule
 * still held — but the choice among equally lawful alternatives may not be the best one.
 *
 * ## A title, not an identifier
 *
 * Each row used to lead with `warning.type` in monospace — `factor_above_leistungslegende_cap` — and
 * then print the whole message underneath. Eleven of those is a column of snake_case a reader has to
 * parse one character at a time, followed by eleven paragraphs they have to read to find the two
 * that matter. The row now leads with a German title (`warningTitle`) and the Ziffer it concerns,
 * and the message, the identifier, the paragraph and the rule id are in the disclosure.
 *
 * The prominent ones keep their tinted border and stay first, because "in order of severity" is only
 * half the signal — a reader scanning eleven rows needs the two that matter to be visibly different,
 * not merely at the top. Their message is also the one part of the explanation that is *not* hidden:
 * a warning nobody may scroll past is not a warning you have to click.
 */
export function WarningsPanel({
  warnings,
}: {
  warnings: readonly EngineWarning[]
}) {
  if (warnings.length === 0) {
    return (
      <Empty className="border">
        <EmptyMedia variant="icon">
          <InfoIcon />
        </EmptyMedia>
        <EmptyTitle>Keine Hinweise</EmptyTitle>
        <EmptyDescription>
          Die Engine hat zu diesem Vorschlag nichts angemerkt. Das ist kein
          Freigabesignal — es bedeutet nur, dass keine der durchgesetzten Regeln
          etwas zu melden hatte.
        </EmptyDescription>
      </Empty>
    )
  }

  const sorted = [...warnings].sort(bySeverity)

  return (
    <ul className="space-y-2">
      {sorted.map((warning, index) => {
        const prominent = isProminentWarning(warning.type, warning.severity)
        const timeout = warning.type === "solver_timeout_partial"

        return (
          <ExpandableItem
            key={`${warning.type}-${warning.ziffer ?? ""}-${index}`}
            className={
              prominent ? "border-destructive/40 bg-destructive/5" : undefined
            }
            icon={
              <SeverityIcon severity={warning.severity} timeout={timeout} />
            }
            title={warningTitle(warning.type)}
            meta={
              <>
                {warning.ziffer ? (
                  <Badge variant="outline" className="font-mono">
                    GOÄ {warning.ziffer}
                  </Badge>
                ) : null}
                {warning.severity !== "info" ? (
                  <Badge variant={SEVERITY_BADGE_VARIANT[warning.severity]}>
                    {SEVERITY_LABEL[warning.severity]}
                  </Badge>
                ) : null}
                {/*
                  A warning a reader must not scroll past does not get to hide its message behind a
                  click. The disclosure below still holds the identifier, the paragraph and the rule
                  id — the parts you quote rather than read.
                */}
                {prominent ? (
                  <span className="w-full text-sm font-normal text-foreground">
                    {warning.message}
                  </span>
                ) : null}
              </>
            }
          >
            {prominent ? null : (
              <p className="text-foreground">{warning.message}</p>
            )}
            <p className="flex flex-wrap gap-x-2 text-xs">
              <span className="font-mono break-all">{warning.type}</span>
              {warning.legal_basis ? (
                <span>· {warning.legal_basis}</span>
              ) : null}
              {warning.rule_id ? (
                <span className="font-mono break-all">· {warning.rule_id}</span>
              ) : null}
            </p>
          </ExpandableItem>
        )
      })}
    </ul>
  )
}
