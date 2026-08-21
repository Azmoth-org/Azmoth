import { CheckIcon, TriangleAlertIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import { ProofDialog } from "@/components/review/proof-dialog"
import { eur, factor, factorBasis, lineStatus, rate } from "@/lib/review/format"
import type { Coding } from "@/lib/review/types"

function JustificationCell({
  required,
  present,
  justification,
}: {
  required: boolean
  present: boolean
  justification: string | null | undefined
}) {
  if (!required) {
    return <span className="text-muted-foreground text-xs">nicht erforderlich</span>
  }
  if (present) {
    return (
      <div className="min-w-0 space-y-1">
        <Badge variant="secondary" className="gap-1">
          <CheckIcon />
          begründet
        </Badge>
        {justification ? (
          <p className="text-muted-foreground line-clamp-3 text-xs" title={justification}>
            {justification}
          </p>
        ) : null}
      </div>
    )
  }
  return (
    <Badge variant="destructive" className="gap-1">
      <TriangleAlertIcon />
      Begründung fehlt (§ 12 Abs. 3 GOÄ)
    </Badge>
  )
}

/**
 * The invoice draft's accepted positions.
 *
 * Every monetary value and every factor is printed exactly as the engine returned it — the engine
 * computes in `Decimal` and serialises to a string so that no client can re-round it. Nothing on
 * this screen adds, multiplies or re-formats a number; the totals row is the engine's own
 * `coding.total`, not a sum computed here.
 */
export function AcceptedPositionsTable({ coding }: { coding: Coding }) {
  const lines = coding.proposed_codes ?? []
  const total = coding.total

  if (lines.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        Keine berechnungsfähige Position. Das ist ein gültiges Ergebnis — die dokumentierten
        Leistungen ließen sich keiner durchsetzbaren Position zuordnen. Hinweise und gesperrte
        Positionen stehen in den anderen Reitern.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Ziffer</TableHead>
            <TableHead>Leistung</TableHead>
            <TableHead className="text-right">Punkte</TableHead>
            <TableHead className="text-right">Faktor</TableHead>
            <TableHead className="text-right">Betrag</TableHead>
            <TableHead>Begründung</TableHead>
            <TableHead className="text-right">Beweis</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {lines.map((line) => (
            <TableRow key={`${line.ziffer}-${line.status ?? ""}`}>
              <TableCell className="align-top font-mono font-medium">
                <div>{line.ziffer}</div>
                {line.is_analog ? (
                  <Badge variant="outline" className="mt-1">
                    analog
                  </Badge>
                ) : null}
              </TableCell>
              <TableCell className="max-w-md align-top">
                <div className="text-sm">{line.official_text}</div>
                <div className="text-muted-foreground mt-1 flex flex-wrap gap-x-2 text-xs">
                  <span>{lineStatus(line.status)}</span>
                  {line.category ? <span>· Abschnitt {line.category}</span> : null}
                  {line.analog_for ? <span>· analog für {line.analog_for}</span> : null}
                  {line.text_quality && line.text_quality !== "ok" ? (
                    <span className="text-destructive">· Textqualität: {line.text_quality}</span>
                  ) : null}
                </div>
              </TableCell>
              <TableCell className="align-top text-right tabular-nums">{line.punkte}</TableCell>
              <TableCell className="align-top text-right">
                <div className="tabular-nums">{factor(line.factor)}</div>
                <div className="text-muted-foreground text-xs">
                  {factorBasis(line.factor_basis)}
                </div>
              </TableCell>
              <TableCell className="align-top text-right">
                <div className="tabular-nums">{eur(line.amount_eur)}</div>
                {line.minderung_applied ? (
                  <div className="text-muted-foreground text-xs">
                    vor § 6a: {eur(line.amount_eur_before_minderung)}
                  </div>
                ) : null}
              </TableCell>
              <TableCell className="max-w-xs align-top">
                <JustificationCell
                  required={line.justification_required ?? false}
                  present={line.justification_present ?? false}
                  justification={line.justification}
                />
              </TableCell>
              <TableCell className="align-top text-right">
                <ProofDialog
                  ziffer={line.ziffer}
                  officialText={line.official_text}
                  steps={line.proof ?? []}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
        {total ? (
          <TableFooter>
            <TableRow>
              <TableCell colSpan={2} className="font-medium">
                Gesamt (Angaben der Engine, nicht im Frontend berechnet)
              </TableCell>
              <TableCell className="text-right font-medium tabular-nums">{total.punkte}</TableCell>
              <TableCell className="text-muted-foreground text-right text-xs">
                Punktwert {total.punktwert_cent} ct
              </TableCell>
              <TableCell className="text-right font-medium tabular-nums">
                {eur(total.amount_eur)}
              </TableCell>
              <TableCell colSpan={2} className="text-muted-foreground text-xs">
                {total.minderung_applied
                  ? `§ 6a Minderung angewendet (Satz ${rate(total.minderung_rate)}) · `
                  : ""}
                Rundung {total.rounding_policy}
                {total.rounding_legal_basis ? ` (${total.rounding_legal_basis})` : ""}
              </TableCell>
            </TableRow>
          </TableFooter>
        ) : null}
      </Table>
    </div>
  )
}
