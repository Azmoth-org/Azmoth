import { AlertTriangleIcon, InfoIcon, OctagonAlertIcon, TimerOffIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from "@workspace/ui/components/empty"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@workspace/ui/components/item"

import { SEVERITY_LABEL, bySeverity, isProminentWarning } from "@/lib/review/format"
import type { EngineWarning, WarningSeverity } from "@/lib/review/types"

const SEVERITY_BADGE_VARIANT: Record<WarningSeverity, "destructive" | "secondary" | "outline"> = {
  error: "destructive",
  warning: "secondary",
  info: "outline",
}

function SeverityIcon({ severity, timeout }: { severity: WarningSeverity; timeout: boolean }) {
  if (timeout) return <TimerOffIcon className="text-destructive" />
  if (severity === "error") return <OctagonAlertIcon className="text-destructive" />
  if (severity === "warning") return <AlertTriangleIcon className="text-amber-600" />
  return <InfoIcon className="text-muted-foreground" />
}

/**
 * Every warning the engine emitted, in order of how much a reviewer needs to see it.
 *
 * `solver_timeout_partial` is the one that must never be scrolled past: it means the optimiser was
 * cancelled and the returned model is the best found so far, not a proven optimum. Every hard rule
 * still held — but the choice among equally lawful alternatives may not be the best one.
 *
 * Rendered with the shared `Item`, which is what this list was reimplementing: a media slot for the
 * icon, a title row for the badges and a description for the message, aligned the same way in every
 * row. The prominent ones keep their tinted border, because "in order of severity" is only half the
 * signal — a reader scanning eleven rows needs the two that matter to be visibly different, not
 * merely first.
 */
export function WarningsPanel({ warnings }: { warnings: readonly EngineWarning[] }) {
  if (warnings.length === 0) {
    return (
      <Empty className="border">
        <EmptyMedia variant="icon">
          <InfoIcon />
        </EmptyMedia>
        <EmptyTitle>Keine Hinweise</EmptyTitle>
        <EmptyDescription>
          Die Engine hat zu diesem Vorschlag nichts angemerkt. Das ist kein Freigabesignal — es
          bedeutet nur, dass keine der durchgesetzten Regeln etwas zu melden hatte.
        </EmptyDescription>
      </Empty>
    )
  }

  const sorted = [...warnings].sort(bySeverity)

  return (
    <ItemGroup className="gap-2">
      {sorted.map((warning, index) => {
        const prominent = isProminentWarning(warning.type, warning.severity)
        const timeout = warning.type === "solver_timeout_partial"

        return (
          <Item
            key={`${warning.type}-${warning.ziffer ?? ""}-${index}`}
            variant="outline"
            size="sm"
            className={prominent ? "border-destructive/40 bg-destructive/5" : undefined}
          >
            <ItemMedia variant="icon">
              <SeverityIcon severity={warning.severity} timeout={timeout} />
            </ItemMedia>
            <ItemContent>
              <ItemTitle className="flex flex-wrap items-center gap-2">
                <Badge variant={SEVERITY_BADGE_VARIANT[warning.severity]}>
                  {SEVERITY_LABEL[warning.severity]}
                </Badge>
                <span className="font-mono text-xs font-normal">{warning.type}</span>
                {warning.ziffer ? (
                  <Badge variant="outline" className="font-mono">
                    GOÄ {warning.ziffer}
                  </Badge>
                ) : null}
                {warning.legal_basis ? (
                  <span className="text-muted-foreground text-xs font-normal">
                    {warning.legal_basis}
                  </span>
                ) : null}
                {warning.rule_id ? (
                  <span className="text-muted-foreground font-mono text-xs font-normal">
                    {warning.rule_id}
                  </span>
                ) : null}
              </ItemTitle>
              <ItemDescription
                className={prominent ? "text-foreground line-clamp-none font-medium" : "line-clamp-none"}
              >
                {warning.message}
              </ItemDescription>
            </ItemContent>
          </Item>
        )
      })}
    </ItemGroup>
  )
}
