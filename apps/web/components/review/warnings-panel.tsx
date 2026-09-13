"use client"

import { useState } from "react"

import {
  AlertTriangleIcon,
  InfoIcon,
  OctagonAlertIcon,
  TimerOffIcon,
} from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@workspace/ui/components/collapsible"
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from "@workspace/ui/components/empty"
import { cn } from "@workspace/ui/lib/utils"

import { ExpandableItem } from "@/components/review/expandable-item"
import {
  SEVERITY_LABEL,
  groupWarnings,
  hintCountLabel,
  isProminentWarning,
  warningTitle,
  type WarningGroup,
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
    return <AlertTriangleIcon className="text-amber-600" />
  }
  return <InfoIcon className="text-azm-indigo-deep" />
}

/** The body of a single warning row — its own message, identifier, paragraph and rule id. */
function WarningDetail({ warning }: { warning: EngineWarning }) {
  const prominent = isProminentWarning(warning.type, warning.severity)
  return (
    <>
      {prominent ? null : <p className="text-foreground">{warning.message}</p>}
      <p className="flex flex-wrap gap-x-2 text-xs">
        <span className="font-mono break-all">{warning.type}</span>
        {warning.legal_basis ? <span>· {warning.legal_basis}</span> : null}
        {warning.rule_id ? (
          <span className="font-mono break-all">· {warning.rule_id}</span>
        ) : null}
      </p>
    </>
  )
}

/**
 * A single warning, rendered exactly as before grouping existed — used whenever a type occurs only
 * once, so the common case (no repetition) never pays for the toggle a group needs.
 */
function SingleWarningRow({ warning }: { warning: EngineWarning }) {
  const prominent = isProminentWarning(warning.type, warning.severity)
  const timeout = warning.type === "solver_timeout_partial"

  return (
    <ExpandableItem
      className={
        prominent ? "border-destructive/40 bg-destructive/5" : undefined
      }
      icon={<SeverityIcon severity={warning.severity} timeout={timeout} />}
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
      <WarningDetail warning={warning} />
    </ExpandableItem>
  )
}

/**
 * Every warning of one `type`, folded into one row with a live count — never permanently hidden,
 * only collapsed by default: the toggle's own label says which state it is in, and every message,
 * identifier and rule id is still there, one click below.
 */
function GroupedWarningRow({ group }: { group: WarningGroup }) {
  const [open, setOpen] = useState(false)
  const { type, representative, warnings } = group
  const prominent = isProminentWarning(representative.type, representative.severity)
  const timeout = warnings.some((w) => w.type === "solver_timeout_partial")

  const ziffern = [
    ...new Set(
      warnings.map((w) => w.ziffer).filter((z): z is string => Boolean(z))
    ),
  ]

  return (
    <li
      className={cn(
        "overflow-hidden rounded-2xl border bg-card",
        prominent ? "border-destructive/40 bg-destructive/5" : undefined
      )}
    >
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex w-full items-start gap-3 p-3">
          <span className="mt-0.5 shrink-0 [&_svg]:size-4">
            <SeverityIcon severity={representative.severity} timeout={timeout} />
          </span>
          <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-semibold">
              {warningTitle(type)} · {hintCountLabel(warnings.length)}
            </span>
            {representative.severity !== "info" ? (
              <Badge variant={SEVERITY_BADGE_VARIANT[representative.severity]}>
                {SEVERITY_LABEL[representative.severity]}
              </Badge>
            ) : null}
          </span>
          <CollapsibleTrigger
            className="shrink-0 cursor-pointer self-start text-xs font-medium text-azm-indigo-deep underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            {open ? "Hinweise ausblenden" : "Hinweise anzeigen"}
          </CollapsibleTrigger>
        </div>

        <CollapsibleContent keepMounted data-print="expand">
          <div className="space-y-3 px-3 pt-1 pb-3 pl-10 text-sm text-muted-foreground">
            <div>
              <p className="text-xs font-medium text-foreground">
                Betroffene Ziffern
              </p>
              <div className="mt-1 flex flex-wrap gap-1">
                {ziffern.length > 0 ? (
                  ziffern.map((ziffer) => (
                    <Badge key={ziffer} variant="outline" className="font-mono">
                      GOÄ {ziffer}
                    </Badge>
                  ))
                ) : (
                  <span className="text-xs">Keine Ziffer zugeordnet.</span>
                )}
              </div>
            </div>

            <ul className="space-y-2">
              {warnings.map((warning, index) => (
                <li
                  key={`${warning.type}-${warning.ziffer ?? ""}-${index}`}
                  className="border-t pt-2 first:border-t-0 first:pt-0"
                >
                  <WarningDetail warning={warning} />
                </li>
              ))}
            </ul>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
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
 *
 * ## Repeats fold into one row
 *
 * A proposal that trips the same rule on eleven positions used to print eleven rows that read
 * identically except for a Ziffer. `groupWarnings` folds a repeated `type` into one summary row with
 * a live count; the affected Ziffern and every individual message are still there, expanded — never
 * dropped, just collapsed by default, the way the single-warning rows always were.
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

  const groups = groupWarnings(warnings)

  return (
    <ul className="space-y-2">
      {groups.map((group) =>
        group.warnings.length === 1 ? (
          <SingleWarningRow key={group.type} warning={group.warnings[0]!} />
        ) : (
          <GroupedWarningRow key={group.type} group={group} />
        )
      )}
    </ul>
  )
}
