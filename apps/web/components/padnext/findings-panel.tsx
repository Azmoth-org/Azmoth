import { TriangleAlertIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

import { SEVERITY_LABEL, bySeverity } from "@/lib/padnext/format"
import type { PadnextAuditReport } from "@/lib/padnext/types"

/**
 * Everything the audit noticed, most severe first.
 *
 * Findings and buckets are related but not the same thing, and the panel does not pretend
 * otherwise: an `error`-severity finding on an unknown Ziffer is a real problem with the delivery
 * while its euros are still only `unconfirmed`. Severity describes the finding; the bucket describes
 * what we can prove about the money.
 */
export function FindingsPanel({ report }: { report: PadnextAuditReport }) {
  const findings = [...(report.findings ?? [])].sort(bySeverity)

  if (findings.length === 0) {
    return null
  }

  return (
    <section className="space-y-4" aria-labelledby="padnext-findings-heading">
      <h2
        id="padnext-findings-heading"
        className="text-lg font-semibold tracking-tight"
      >
        Befunde ({findings.length})
      </h2>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <TriangleAlertIcon className="size-4 shrink-0" aria-hidden />
            Prüfprotokoll
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {findings.map((finding, index) => (
            <div
              key={`${finding.type}-${finding.positionsnr ?? "delivery"}-${index}`}
              className="space-y-1 border-b border-border pb-3 last:border-0 last:pb-0"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant={
                    finding.severity === "error" ? "destructive" : "outline"
                  }
                >
                  {SEVERITY_LABEL[finding.severity]}
                </Badge>
                <span className="font-mono text-xs text-muted-foreground">
                  {finding.type}
                </span>
                {finding.positionsnr ? (
                  <span className="text-xs text-muted-foreground">
                    Pos {finding.positionsnr}
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">
                    Lieferung
                  </span>
                )}
              </div>
              <p className="text-sm">{finding.message}</p>
              {finding.legal_basis ? (
                <p className="text-xs text-muted-foreground">
                  {finding.legal_basis}
                </p>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </section>
  )
}
