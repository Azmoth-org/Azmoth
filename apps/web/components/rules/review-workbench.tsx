"use client"

import * as React from "react"
import { ClockIcon, Loader2Icon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import { ErrorPanel } from "@/components/review/error-panel"
import { CoverageHeader } from "@/components/rules/coverage-header"
import { ReviewDialog } from "@/components/rules/review-dialog"
import {
  fetchReviewQueue,
  fetchRuleCoverage,
  submitRuleReview,
  type ReviewableRule,
  type ReviewError,
  type RuleCoverage,
  type RuleKind,
  type RuleReviewQueue,
} from "@/lib/rules/client"
import { KIND, KIND_ORDER, REVIEW_STATUS_LABEL } from "@/lib/rules/format"

/** One page of the queue. The backlog is 859 rules with a full GOÄ sentence each. */
const PAGE_SIZE = 100

/**
 * The rule review screen.
 *
 * Nothing here is optimistic. A decision changes what every future audit concludes about somebody's
 * invoice, so the table is rebuilt from what the engine returns rather than from what the click
 * hoped for — the same rule `/review` follows, and for a stronger reason.
 */
export function RuleReviewWorkbench() {
  const [queue, setQueue] = React.useState<RuleReviewQueue | null>(null)
  const [coverage, setCoverage] = React.useState<RuleCoverage | null>(null)
  const [error, setError] = React.useState<ReviewError | null>(null)
  const [kind, setKind] = React.useState<RuleKind | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [selected, setSelected] = React.useState<ReviewableRule | null>(null)
  const [decided, setDecided] = React.useState<string | null>(null)

  const load = React.useCallback(async (forKind: RuleKind | null) => {
    setLoading(true)
    const [queueResult, coverageResult] = await Promise.all([
      fetchReviewQueue({ kind: forKind, limit: PAGE_SIZE }),
      fetchRuleCoverage(),
    ])

    if (queueResult.kind === "error") {
      setError(queueResult.error)
    } else {
      setQueue(queueResult.queue)
      setError(null)
    }
    if (coverageResult.kind === "coverage") setCoverage(coverageResult.coverage)
    setLoading(false)
  }, [])

  React.useEffect(() => {
    void load(kind)
  }, [load, kind])

  async function decide(
    rule: ReviewableRule,
    status: "VERIFIED" | "REJECTED" | "PENDING",
    reviewedBy: string,
    notes: string,
  ) {
    setSaving(true)
    const result = await submitRuleReview(rule.rule_id, {
      status,
      reviewed_by: reviewedBy,
      review_notes: notes,
    })
    setSaving(false)

    if (result.kind === "error") {
      setError(result.error)
      return
    }

    setError(null)
    setCoverage(result.result.coverage)
    setSelected(null)
    setDecided(`${rule.rule_id} · ${REVIEW_STATUS_LABEL[status] ?? status}`)
    // Reload rather than splice the row out locally: a PENDING decision *keeps* the rule in the
    // queue with a changed badge, and encoding that rule in two places is how the two drift apart.
    await load(kind)
  }

  const rules = queue?.rules ?? []

  return (
    <div className="space-y-6">
      {coverage ? (
        <CoverageHeader coverage={coverage} pendingCount={queue?.pending_rule_count} />
      ) : null}

      {error ? <ErrorPanel error={error} /> : null}

      <Card>
        <CardContent className="flex flex-wrap items-center gap-2 pt-6">
          <span className="text-muted-foreground mr-1 text-sm">Filter:</span>
          <Button
            size="sm"
            variant={kind === null ? "default" : "outline"}
            onClick={() => setKind(null)}
          >
            Alle
          </Button>
          {KIND_ORDER.map((option) => (
            <Button
              key={option}
              size="sm"
              variant={kind === option ? "default" : "outline"}
              onClick={() => setKind(option)}
            >
              {KIND[option].label}
            </Button>
          ))}
          {decided ? (
            <span className="text-muted-foreground ml-auto text-xs">
              Zuletzt entschieden: <span className="font-mono">{decided}</span>
            </span>
          ) : null}
        </CardContent>
      </Card>

      {kind === "zielleistung" ? (
        <Alert>
          <AlertTitle>Zielleistungsregeln zuerst — und am sorgfältigsten</AlertTitle>
          <AlertDescription>
            Eine falsch verifizierte Zielleistungsregel entfernt eine Position, die die Praxis
            berechnen durfte. Von allen Regeltypen hier ist das der teuerste Fehler: er macht aus
            Umsatz einen falschen Befund.
          </AlertDescription>
        </Alert>
      ) : null}

      <section className="space-y-3" aria-labelledby="rules-queue-heading">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="rules-queue-heading" className="text-lg font-semibold tracking-tight">
            Prüfliste
          </h2>
          {queue ? (
            <span className="text-muted-foreground text-xs tabular-nums">
              {rules.length} angezeigt
              {queue.truncated ? ` · ${queue.pending_rule_count} insgesamt offen` : ""}
            </span>
          ) : null}
        </div>

        {loading && !queue ? (
          <Card>
            <CardContent className="text-muted-foreground flex items-center gap-2 pt-6 text-sm">
              <Loader2Icon className="size-4 animate-spin" aria-hidden />
              Prüfliste wird geladen…
            </CardContent>
          </Card>
        ) : rules.length === 0 ? (
          <Card>
            <CardContent className="pt-6 text-sm">
              {kind
                ? `Keine offenen Regeln vom Typ „${KIND[kind].label}“.`
                : "Keine offenen Regeln mehr — jede Regel ist verifiziert oder abgelehnt."}
            </CardContent>
          </Card>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Regel-ID</TableHead>
                <TableHead>Typ</TableHead>
                <TableHead>Ziffern</TableHead>
                <TableHead>Rechtsgrundlage</TableHead>
                <TableHead>Quelltext</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((rule) => (
                <TableRow
                  key={rule.rule_id}
                  className="hover:bg-muted/50 cursor-pointer"
                  onClick={() => setSelected(rule)}
                >
                  <TableCell className="font-mono text-xs">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {rule.rule_id}
                      {rule.review_status === "PENDING" ? (
                        <Badge variant="outline" className="gap-1 text-[0.7rem]">
                          <ClockIcon className="size-3" aria-hidden />
                          zurückgestellt
                        </Badge>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge className={KIND[rule.kind].className}>{KIND[rule.kind].label}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs whitespace-nowrap">
                    {(rule.ziffern ?? []).join(` ${KIND[rule.kind].connector} `.replace(/\s+/g, " "))}
                  </TableCell>
                  <TableCell className="max-w-[14rem] truncate text-xs">
                    {rule.legal_basis || "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-md truncate text-xs">
                    {rule.quote || "—"}
                  </TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={(event) => {
                        event.stopPropagation()
                        setSelected(rule)
                      }}
                    >
                      Prüfen
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {queue?.truncated ? (
          <p className="text-muted-foreground text-xs">
            Es werden {PAGE_SIZE} von {queue.pending_rule_count} offenen Regeln angezeigt. Die Liste
            füllt sich nach, sobald Regeln entschieden sind.
          </p>
        ) : null}
      </section>

      <ReviewDialog
        rule={selected}
        open={selected !== null}
        pending={saving}
        onOpenChange={(next) => {
          if (!next) setSelected(null)
        }}
        onDecide={decide}
      />
    </div>
  )
}
