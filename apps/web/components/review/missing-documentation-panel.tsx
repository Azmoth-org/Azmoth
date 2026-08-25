import { FileTextIcon, ShieldCheckIcon, TriangleAlertIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from "@workspace/ui/components/empty"

import { ExpandableItem } from "@/components/review/expandable-item"
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
 *
 * The alert above the list stays, and stays first. It is the only thing standing between this panel
 * and being read as "here is how much more you could have charged", and a reader who scrolls past it
 * to the rows has already been given the wrong frame.
 *
 * ## The row says which position; the disclosure says why
 *
 * `GOÄ 3: 2.3-fach → max 3.5-fach` is the whole of what a reader needs to scan the list: which
 * position, what it charges, and what the ceiling would be. The sentence explaining what is missing
 * from the record is the part they read once they have picked a row — and the part that, rendered
 * inline on six entries, turned this panel into six paragraphs. It is unconditionally open on paper.
 *
 * The amber is the panel's only colour and it means "unresolved", not "wrong": a documentation gap is
 * a normal state of a draft, and the § 12 Abs. 3 badge in the positions table is where an actually
 * missing justification is called out in red.
 */
export function MissingDocumentationPanel({ entries }: { entries: readonly MissingDocumentation[] }) {
  if (entries.length === 0) {
    return (
      <Empty className="border">
        <EmptyMedia variant="icon">
          <ShieldCheckIcon />
        </EmptyMedia>
        <EmptyTitle>Keine Dokumentationslücke</EmptyTitle>
        <EmptyDescription>
          Für jede berechnete Position ist der angesetzte Faktor entweder durch die Dokumentation
          gedeckt oder es besteht kein Spielraum nach oben.
        </EmptyDescription>
      </Empty>
    )
  }

  return (
    <div className="space-y-6">
      <Alert>
        <FileTextIcon />
        <AlertTitle>Dokumentationslücken — keine Abrechnungsempfehlung</AlertTitle>
        <AlertDescription>
          <p>
            Abgerechnet wird <strong>immer der angesetzte Faktor</strong>. Der Wert hinter dem Pfeil
            zeigt lediglich die gesetzliche Obergrenze, die eine{" "}
            <strong>schriftliche Begründung nach § 12 Abs. 3 GOÄ</strong> eröffnen würde. Sie ist{" "}
            <strong>kein Vorschlag, den Faktor zu erhöhen</strong>. Ob eine besondere Schwierigkeit,
            ein erhöhter Zeitaufwand oder erschwerende Umstände vorlagen, kann ausschließlich die
            behandelnde Ärztin oder der behandelnde Arzt beurteilen und dokumentieren.
          </p>
        </AlertDescription>
      </Alert>

      <ul className="space-y-2">
        {entries.map((entry, index) => (
          <ExpandableItem
            key={`${entry.ziffer}-${index}`}
            // Amber on the border as well as on the icon. An icon alone is 16px of colour in a list
            // of six identical rows; the edge is what makes the row itself read as unresolved.
            className="border-amber-300 dark:border-amber-500/30"
            icon={<TriangleAlertIcon className="text-amber-600 dark:text-amber-400" />}
            title={
              <span className="tabular-nums">
                <span className="font-mono">GOÄ {entry.ziffer}</span>
                {": "}
                {factor(entry.current_factor)}
                <span className="text-muted-foreground"> → max </span>
                {factor(entry.possible_factor)}
              </span>
            }
            meta={
              entry.legal_basis ? (
                <span className="text-muted-foreground text-xs">{entry.legal_basis}</span>
              ) : null
            }
          >
            <p>
              <span className="text-foreground font-medium">Angesetzt</span>{" "}
              {factor(entry.current_factor)} ·{" "}
              <span className="text-foreground font-medium">nach § 5 Abs. 2 GOÄ möglich</span>{" "}
              {factor(entry.possible_factor)}
            </p>
            <p>{entry.missing}</p>
          </ExpandableItem>
        ))}
      </ul>
    </div>
  )
}
