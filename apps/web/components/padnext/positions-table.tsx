import { CircleAlertIcon, CircleCheckIcon, CircleHelpIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import {
  BUCKET,
  BUCKET_ORDER,
  BUCKET_TONE_CLASS,
  VERDICT_LABEL,
  eur,
} from "@/lib/padnext/format"
import type {
  PadnextAuditReport,
  PadnextAuditedPosition,
} from "@/lib/padnext/types"

const BUCKET_ICON = {
  confirmed_wrong: CircleAlertIcon,
  confirmed_fine: CircleCheckIcon,
  unconfirmed: CircleHelpIcon,
} as const

function BucketBadge({ bucket }: { bucket: PadnextAuditedPosition["bucket"] }) {
  const presentation = BUCKET[bucket]
  const Icon = BUCKET_ICON[bucket]
  return (
    <Badge className={BUCKET_TONE_CLASS[presentation.tone].badge}>
      <Icon aria-hidden />
      {presentation.label}
    </Badge>
  )
}

/** The rules that bore on a position, with their verification status made explicit. */
function RuleIds({ position }: { position: PadnextAuditedPosition }) {
  const verified = position.verified_rule_ids ?? []
  const advisory = position.advisory_rule_ids ?? []

  if (verified.length === 0 && advisory.length === 0) {
    return (
      <span className="text-xs text-muted-foreground">
        keine Regel anwendbar
      </span>
    )
  }

  return (
    <div className="flex flex-wrap gap-1">
      {verified.map((id) => (
        <Badge
          key={id}
          variant="outline"
          className="font-mono text-[0.7rem]"
          title="verifizierte Regel"
        >
          ✓ {id}
        </Badge>
      ))}
      {advisory.map((id) => (
        <Badge
          key={id}
          variant="outline"
          className="font-mono text-[0.7rem] text-muted-foreground"
          title="nicht verifiziert — blockiert unter der aktuellen Policy nicht"
        >
          ? {id}
        </Badge>
      ))}
    </div>
  )
}

/**
 * Every claimed position, grouped by bucket.
 *
 * Grouped rather than sorted, and in `BUCKET_ORDER`, so the reader's first screen is what needs
 * action. The engine's `verdict` is shown next to the bucket rather than instead of it: they answer
 * different questions, and a position that reads `unbestätigt` / `durch Regel entfernt` is exactly
 * the case this refactor exists to make legible — a rule removed it, but no verified rule did.
 */
export function PositionsTable({ report }: { report: PadnextAuditReport }) {
  const positions = report.positions ?? []

  return (
    <section className="space-y-4" aria-labelledby="padnext-positions-heading">
      <h2
        id="padnext-positions-heading"
        className="text-lg font-semibold tracking-tight"
      >
        Positionen ({positions.length})
      </h2>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-14">Pos</TableHead>
              <TableHead>Ziffer</TableHead>
              <TableHead className="text-right">Faktor</TableHead>
              <TableHead className="text-right">berechnet</TableHead>
              <TableHead className="text-right">nachgerechnet</TableHead>
              <TableHead>Bewertung</TableHead>
              <TableHead>Regelurteil</TableHead>
              <TableHead>Regeln</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {BUCKET_ORDER.flatMap((bucket) =>
              positions
                .filter((position) => position.bucket === bucket)
                .map((position) => (
                  <TableRow key={`${position.positionsnr}-${position.ziffer}`}>
                    <TableCell className="font-mono text-xs">
                      {position.positionsnr}
                    </TableCell>
                    <TableCell>
                      <div className="font-mono text-sm">
                        {position.go} {position.ziffer}
                      </div>
                      {position.official_text ? (
                        <div className="max-w-xs truncate text-xs text-muted-foreground">
                          {position.official_text}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs tabular-nums">
                      {position.claimed_faktor ?? "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs tabular-nums">
                      {eur(position.claimed_amount_eur)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs tabular-nums">
                      {eur(position.recomputed_amount_eur)}
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <BucketBadge bucket={position.bucket} />
                        {position.bucket_reason ? (
                          <p className="max-w-xs text-xs text-muted-foreground">
                            {position.bucket_reason}
                          </p>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs">
                      {VERDICT_LABEL[position.verdict]}
                      {position.blocked_by ? (
                        <div className="font-mono text-[0.7rem] text-muted-foreground">
                          neben {position.blocked_by}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <RuleIds position={position} />
                    </TableCell>
                  </TableRow>
                ))
            )}
          </TableBody>
        </Table>
      </div>

      <p className="text-xs text-muted-foreground">
        <span className="font-mono">✓</span> verifizierte Regel ·{" "}
        <span className="font-mono">?</span> nicht verifiziert, blockiert unter
        der aktuellen Policy nicht. Eine Position ohne verifizierte Regel kann
        nicht als bestätigt gelten, auch wenn an ihr nichts auffällig ist.
      </p>
    </section>
  )
}
