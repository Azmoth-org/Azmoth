import { FileTextIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Badge } from "@workspace/ui/components/badge"

import { factor } from "@/lib/review/format"
import type { MissingDocumentation } from "@/lib/review/types"

/**
 * Documentation gaps — **not** billing suggestions.
 *
 * This is the panel most capable of doing harm if it is worded loosely, so the wording is deliberate:
 *
 * - `current_factor` is what the invoice *charges*. It is what the engine chose and it stands.
 * - `possible_factor` is the ceiling § 5 Abs. 2 GOÄ would permit **if** a written justification
 *   existed. It is not a recommendation, not a target, and not an amount.
 * - The gap exists because the record documents no particular difficulty. The only lawful way to
 *   close it is for the treating physician to document one, if one genuinely occurred.
 *
 * The engine derives this from decisions it already made (the chosen factor, the § 5 band, the
 * Leistungslegende cap, whether a reason is present). Its optimisation objective is untouched: it
 * does not and must not maximise revenue.
 */
export function MissingDocumentationPanel({ entries }: { entries: readonly MissingDocumentation[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        Keine Dokumentationslücke festgestellt: für jede berechnete Position ist der angesetzte Faktor
        entweder durch die Dokumentation gedeckt oder es besteht kein Spielraum nach oben.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <Alert>
        <FileTextIcon />
        <AlertTitle>Dokumentationslücken — keine Abrechnungsempfehlung</AlertTitle>
        <AlertDescription>
          <p>
            Abgerechnet wird <strong>immer der Spalteninhalt „angesetzt“</strong>. Die Spalte „nach § 5
            Abs. 2 GOÄ möglich“ zeigt lediglich die gesetzliche Obergrenze, die eine{" "}
            <strong>schriftliche Begründung nach § 12 Abs. 3 GOÄ</strong> eröffnen würde. Sie ist{" "}
            <strong>kein Vorschlag, den Faktor zu erhöhen</strong>. Ob eine besondere Schwierigkeit,
            ein erhöhter Zeitaufwand oder erschwerende Umstände vorlagen, kann ausschließlich die
            behandelnde Ärztin oder der behandelnde Arzt beurteilen und dokumentieren.
          </p>
        </AlertDescription>
      </Alert>

      <ul className="space-y-3">
        {entries.map((entry, index) => (
          <li key={`${entry.ziffer}-${index}`} className="rounded-xl border p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono font-medium">GOÄ {entry.ziffer}</span>
              <Badge variant="secondary">angesetzt: {factor(entry.current_factor)}</Badge>
              <Badge variant="outline">
                nach § 5 Abs. 2 GOÄ möglich: {factor(entry.possible_factor)}
              </Badge>
              {entry.legal_basis ? (
                <span className="text-muted-foreground text-xs">{entry.legal_basis}</span>
              ) : null}
            </div>
            <p className="text-muted-foreground mt-2 text-sm">{entry.missing}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
