import { InfoIcon } from "lucide-react"

/**
 * What this engine cannot do about time, said before the upload rather than after it.
 *
 * Every audit prices against one catalog edition, and that edition is the current GOÄ — the only
 * one in `data/catalogs/` holding real numbers, the rest being synthetic fixtures. So an invoice
 * for a treatment two years ago is measured against a fee schedule that did not apply on the day
 * of treatment. Most positions are unaffected; the ones that are not produce a finding that looks
 * exactly like a correct one.
 *
 * The engine already says this on the report — `pilot_warnings`, rendered by `PilotWarningsPanel`
 * — but a warning that arrives with the result arrives after the work. A partner exporting a
 * decade of invoices from their PVS makes that decision here, at the point where they choose what
 * to export, and this is the only place the product can reach them before they do.
 *
 * ## Why blue, and why not amber
 *
 * `SyntheticDataBanner` directly above is amber, and it is amber for something the reader must not
 * do. This is neither a prohibition nor a warning about their data — it is a recommendation about
 * scope, and it will be equally true on every load. Amber twice in a column trains a reader past
 * both; blue reads as information rather than as a second thing gone wrong, and keeps the amber
 * strip meaning what it means.
 *
 * Not `role="alert"`, for the reason `SyntheticDataBanner` gives at length: a standing notice that
 * fires a live region on every navigation is one a screen-reader user learns to tune out. In
 * document order above the picker it is read anyway.
 */
export function CatalogScopeNotice() {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-sky-300 bg-sky-50 px-3 py-2 text-sky-950 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100 print:rounded-lg">
      <InfoIcon
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400"
      />
      <p className="min-w-0 text-xs leading-relaxed">
        <strong className="font-semibold">Pilot-Hinweis:</strong> Diese Engine
        verwendet den <strong>aktuellen GOÄ-Katalog</strong>. Wir empfehlen die
        Prüfung von Rechnungen mit Leistungsdatum aus den letzten 12 Monaten, um
        abweichende Regelwerke älterer Katalogeditionen zu vermeiden. Ältere
        Lieferungen werden weiterhin geprüft — der Bericht weist dann gesondert
        darauf hin.
      </p>
    </div>
  )
}
