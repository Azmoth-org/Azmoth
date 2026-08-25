import { FileTextIcon, ShieldCheckIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
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
  ItemTitle,
} from "@workspace/ui/components/item"

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

      <ItemGroup className="gap-2">
        {entries.map((entry, index) => (
          <Item key={`${entry.ziffer}-${index}`} variant="outline" size="sm">
            <ItemContent>
              <ItemTitle className="flex flex-wrap items-center gap-2">
                <span className="font-mono">GOÄ {entry.ziffer}</span>
                <Badge variant="secondary">angesetzt: {factor(entry.current_factor)}</Badge>
                <Badge variant="outline">
                  nach § 5 Abs. 2 GOÄ möglich: {factor(entry.possible_factor)}
                </Badge>
                {entry.legal_basis ? (
                  <span className="text-muted-foreground text-xs font-normal">
                    {entry.legal_basis}
                  </span>
                ) : null}
              </ItemTitle>
              <ItemDescription className="line-clamp-none">{entry.missing}</ItemDescription>
            </ItemContent>
          </Item>
        ))}
      </ItemGroup>
    </div>
  )
}
