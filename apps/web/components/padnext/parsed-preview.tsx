import { FileTextIcon } from "lucide-react"

import type { PadnextParsedPreview } from "@/lib/padnext/types"

/**
 * What the engine managed to read out of the delivery, beside the reasons it was refused.
 *
 * ## Why a refusal screen shows the contents of the file it refused
 *
 * "Everything is broken" and "one attribute is missing from an otherwise complete export" produce
 * very different next actions from the person holding the file, and only one of them is true. A
 * refusal that says nothing else invites the first reading — and the first reading leads to
 * re-exporting from scratch, or to mailing the file to someone.
 *
 * Three invoices and forty-seven positions on the screen says: your data arrived, your export
 * works, change this one field. That is the difference between a support ticket and a two-minute
 * fix, and it costs one recovering parse (`app/padnext/validation.py::build_preview`).
 *
 * ## Compact, and why that is not just taste
 *
 * A two-column definition list, `text-xs`, one row per fact. This card is *context* for the errors
 * above it, and context that occupies more vertical space than the thing it contextualises stops
 * being context. It is deliberately the quietest element on the screen.
 *
 * The grid is `grid-cols-[auto_1fr]` from the first breakpoint rather than stacking on mobile:
 * label-above-value doubles the row count, and at 390 px this card is already the last thing on a
 * long page. `min-w-0` and `break-words` on the value cell are what keep a long container
 * filename from widening the grid past the viewport.
 *
 * ## Nothing here is a number anyone may act on
 *
 * No euro, no verdict, no total. The preview is a description of the *file*, produced by a
 * tolerant parse that trusts nothing and is independent of the audit — the audit recomputes every
 * amount from the versioned catalog. It is shown as counts and dates for exactly that reason: a
 * money figure on this card would look like a finding, and it would be one nobody had checked.
 *
 * `recovered` is called out rather than hidden. When the counts come from a document that does not
 * parse, they are a floor and not the truth, and a reader comparing "2 Rechnungen" here against
 * the 3 they exported has to be told which of the two numbers to doubt.
 */
export function ParsedPreview({ preview }: { preview: PadnextParsedPreview }) {
  const rows: Array<[string, string]> = []

  if (preview.invoice_count) {
    rows.push(["Rechnungen", String(preview.invoice_count)])
  }
  if (preview.position_count) {
    rows.push(["Positionen", String(preview.position_count)])
  }
  if (preview.other_position_count) {
    rows.push([
      "weitere Positionen",
      `${preview.other_position_count} (nicht bewertet)`,
    ])
  }
  if (preview.date_range) {
    rows.push(["Zeitraum", preview.date_range])
  }
  if (preview.first_invoice) {
    const first = preview.first_invoice as Record<string, unknown>
    const art =
      (first.behandlungsart_label as string) ||
      (first.behandlungsart as string) ||
      ""
    rows.push([
      "erste Rechnung",
      [
        (first.invoice_id as string) || "(ohne Nummer)",
        first.position_count ? `${first.position_count} Pos.` : "",
        art,
      ]
        .filter(Boolean)
        .join(" · "),
    ])
  }
  if (preview.nachrichtentyp) {
    rows.push([
      "Nachrichtentyp",
      `${preview.nachrichtentyp}${preview.version ? ` ${preview.version}` : ""}`,
    ])
  }
  if (preview.transfernr) {
    rows.push(["Transfernummer", preview.transfernr])
  }
  rows.push(["echtdaten", preview.echtdaten_declared ?? "— nicht erklärt"])

  // A preview that found nothing is not worth a card: it would say "echtdaten: —" under a heading
  // promising what was read, which reads as a second failure rather than as reassurance. The CLI
  // suppresses its own block on the same condition.
  if (!preview.invoice_count && !preview.position_count) {
    return null
  }

  return (
    <section className="rounded-lg border bg-card/50 p-3">
      <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <FileTextIcon className="size-3.5 shrink-0" aria-hidden />
        Aus der Datei gelesen
      </h3>

      {preview.recovered ? (
        <p className="mb-2 text-xs leading-relaxed text-muted-foreground">
          Beschädigte oder unvollständige Datei — diese Zahlen sind eine{" "}
          <strong className="font-medium">Untergrenze</strong>.
        </p>
      ) : null}

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0 font-medium break-words">{value}</dd>
          </div>
        ))}
      </dl>

      {preview.container_members && preview.container_members.length > 0 ? (
        <p className="mt-2 font-mono text-[10px] break-all text-muted-foreground">
          {preview.container_members.join(" · ")}
        </p>
      ) : null}

      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        Beschreibt die Datei — hier wurde nichts geprüft und nichts bewertet.
        Beträge rechnet die Prüfung selbst gegen den Katalog nach.
      </p>
    </section>
  )
}
