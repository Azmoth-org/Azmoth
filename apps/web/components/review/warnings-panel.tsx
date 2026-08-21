import { AlertTriangleIcon, InfoIcon, OctagonAlertIcon, TimerOffIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"

import { SEVERITY_LABEL, bySeverity, isProminentWarning } from "@/lib/review/format"
import type { EngineWarning, WarningSeverity } from "@/lib/review/types"

const SEVERITY_BADGE_VARIANT: Record<WarningSeverity, "destructive" | "secondary" | "outline"> = {
  error: "destructive",
  warning: "secondary",
  info: "outline",
}

function SeverityIcon({ severity }: { severity: WarningSeverity }) {
  if (severity === "error") return <OctagonAlertIcon className="text-destructive size-4" />
  if (severity === "warning") return <AlertTriangleIcon className="size-4 text-amber-600" />
  return <InfoIcon className="text-muted-foreground size-4" />
}

/**
 * Every warning the engine emitted, in order of how much a reviewer needs to see it.
 *
 * `solver_timeout_partial` is the one that must never be scrolled past: it means the optimiser was
 * cancelled and the returned model is the best found so far, not a proven optimum. Every hard rule
 * still held — but the choice among equally lawful alternatives may not be the best one.
 */
export function WarningsPanel({ warnings }: { warnings: readonly EngineWarning[] }) {
  if (warnings.length === 0) {
    return <p className="text-muted-foreground text-sm">Die Engine hat keine Hinweise erzeugt.</p>
  }

  const sorted = [...warnings].sort(bySeverity)

  return (
    <ul className="space-y-2">
      {sorted.map((warning, index) => {
        const prominent = isProminentWarning(warning.type, warning.severity)
        const timeout = warning.type === "solver_timeout_partial"

        return (
          <li
            key={`${warning.type}-${warning.ziffer ?? ""}-${index}`}
            className={
              prominent
                ? "border-destructive/40 bg-destructive/5 rounded-xl border p-3"
                : "rounded-xl border p-3"
            }
          >
            <div className="flex items-start gap-2">
              {timeout ? (
                <TimerOffIcon className="text-destructive mt-0.5 size-4" />
              ) : (
                <span className="mt-0.5">
                  <SeverityIcon severity={warning.severity} />
                </span>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={SEVERITY_BADGE_VARIANT[warning.severity]}>
                    {SEVERITY_LABEL[warning.severity]}
                  </Badge>
                  <span className="font-mono text-xs">{warning.type}</span>
                  {warning.ziffer ? (
                    <Badge variant="outline" className="font-mono">
                      GOÄ {warning.ziffer}
                    </Badge>
                  ) : null}
                  {warning.legal_basis ? (
                    <span className="text-muted-foreground text-xs">{warning.legal_basis}</span>
                  ) : null}
                  {warning.rule_id ? (
                    <span className="text-muted-foreground font-mono text-xs">
                      {warning.rule_id}
                    </span>
                  ) : null}
                </div>
                <p className={prominent ? "mt-1 text-sm font-medium" : "mt-1 text-sm"}>
                  {warning.message}
                </p>
              </div>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
