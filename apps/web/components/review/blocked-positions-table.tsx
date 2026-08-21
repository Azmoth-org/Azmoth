import { Badge } from "@workspace/ui/components/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import { ProofDialog } from "@/components/review/proof-dialog"
import { BLOCKED_REASON_LABEL } from "@/lib/review/format"
import type { AuditTrail, Coding } from "@/lib/review/types"

/**
 * Positions the rules removed, and why.
 *
 * `reconciled_with_final_invoice: false` is called out rather than hidden: it means the position's
 * blocker is itself not on the final invoice, so the suppression has lost its basis and the position
 * may well be chargeable after all. The engine reports it instead of silently reinstating it, and a
 * reviewer is exactly who should decide.
 *
 * A blocked position's proof comes from the audit trail's `per_code` entries, which cover charged
 * *and* blocked Ziffern — `blocked_codes` itself carries no proof array.
 */
export function BlockedPositionsTable({
  coding,
  auditTrail,
}: {
  coding: Coding
  auditTrail: AuditTrail
}) {
  const blocked = coding.blocked_codes ?? []
  const proofByZiffer = new Map(
    (auditTrail.per_code ?? []).map((entry) => [entry.ziffer, entry.steps ?? []]),
  )

  if (blocked.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        Keine Position wurde durch eine Regel unterdrückt.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Ziffer</TableHead>
            <TableHead>Grund</TableHead>
            <TableHead>Erläuterung</TableHead>
            <TableHead>Regel-ID</TableHead>
            <TableHead>Rechtsgrundlage</TableHead>
            <TableHead className="text-right">Beweis</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {blocked.map((entry, index) => (
            <TableRow key={`${entry.ziffer}-${entry.reason}-${index}`}>
              <TableCell className="align-top font-mono font-medium">
                <div>{entry.ziffer}</div>
                {entry.official_text ? (
                  <div
                    className="text-muted-foreground mt-1 line-clamp-2 max-w-[16rem] font-sans text-xs"
                    title={entry.official_text}
                  >
                    {entry.official_text}
                  </div>
                ) : null}
              </TableCell>
              <TableCell className="align-top">
                <Badge variant="secondary">{BLOCKED_REASON_LABEL[entry.reason]}</Badge>
                {entry.blocked_by ? (
                  <div className="text-muted-foreground mt-1 text-xs">
                    verdrängt durch{" "}
                    <span className="font-mono">GOÄ {entry.blocked_by}</span>
                  </div>
                ) : null}
                {entry.reconciled_with_final_invoice === false ? (
                  <Badge variant="destructive" className="mt-1">
                    Sperrgrund entfallen — manuell prüfen
                  </Badge>
                ) : null}
              </TableCell>
              <TableCell className="max-w-md align-top text-sm">
                {entry.explanation || entry.detail || "—"}
              </TableCell>
              <TableCell className="align-top font-mono text-xs">{entry.rule_id || "—"}</TableCell>
              <TableCell className="align-top text-xs">{entry.legal_basis || "—"}</TableCell>
              <TableCell className="align-top text-right">
                <ProofDialog
                  ziffer={entry.ziffer}
                  officialText={entry.official_text}
                  steps={proofByZiffer.get(entry.ziffer) ?? []}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
