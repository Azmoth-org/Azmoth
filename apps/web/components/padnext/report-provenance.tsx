import { Card, CardContent } from "@workspace/ui/components/card"

import { CopyableHash } from "@/components/common/copyable-hash"
import { eur } from "@/lib/padnext/format"
import type { PadnextAuditReport } from "@/lib/padnext/types"

/**
 * What this report was computed from, and what it recomputed.
 *
 * Extracted from `AuditWorkbench`, where it lived as a private component, once the public demo
 * needed the same block. Shared rather than copied on purpose: the provenance strip is the part of
 * the screen that makes a verdict checkable — catalog edition, the recomputed total, the receipt
 * hash — and two copies of it would be two places for the fields to drift apart. A prospect on
 * `/demo` and a reviewer on `/padnext` must be looking at the same evidence in the same order,
 * because the demo's whole claim is that it is the product rather than a picture of it.
 *
 * A server component: nothing here is interactive except `CopyableHash`, which brings its own
 * client boundary.
 */
export function ReportProvenance({ report }: { report: PadnextAuditReport }) {
  return (
    <Card>
      <CardContent className="grid grid-cols-2 gap-x-6 gap-y-2 pt-6 text-xs sm:grid-cols-4">
        <div>
          <div className="text-muted-foreground">Datei</div>
          <div className="font-mono break-all">{report.source_name || "—"}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Nachrichtentyp</div>
          <div className="font-mono">{report.nachrichtentyp || "—"}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Setting (§ 6a)</div>
          <div className="font-mono">{report.setting}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Katalog</div>
          <div className="font-mono break-all">
            {report.catalog_version || "—"}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">nachgerechnet</div>
          <div className="font-mono tabular-nums">
            {eur(report.recomputed_total_eur)}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">Rechendifferenz</div>
          <div className="font-mono tabular-nums">
            {eur(report.arithmetic_delta_eur)}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">nicht nachrechenbar</div>
          <div className="font-mono tabular-nums">
            {eur(report.unpriceable_claimed_eur)}
          </div>
        </div>
        <div className="min-w-0">
          <div className="text-muted-foreground">Receipt</div>
          <CopyableHash value={report.receipt_hash} label="Receipt-Hash" />
        </div>
      </CardContent>
    </Card>
  )
}
