import { FlaskConicalIcon } from "lucide-react"

/**
 * The standing notice on every public demo screen.
 *
 * Deliberately a *different* statement from `SyntheticDataBanner`, which is shown to a signed-in
 * reviewer and says "you may only put synthetic data into this system". This one says something
 * about the page rather than about the reader's obligations: what is on screen was computed from a
 * file we shipped, and nobody uploaded anything.
 *
 * The distinction matters because the two audiences are different. A pilot reviewer needs to be
 * told what they may do; a visitor evaluating the product needs to be told what they are looking
 * at, so that they do not mistake a fixture for their own numbers — and so that the first question
 * a Datenschutzbeauftragter asks about this page is answered on the page.
 *
 * Blue rather than amber, and that is the whole reason it is a separate component. Amber is the
 * register this application uses for "unresolved" — a partial rule set, a position nothing
 * verified. Nothing here is unresolved: the demo is working exactly as intended, and colouring a
 * correct state as a caution would spend the warning palette on a non-warning and blunt it for the
 * bucket summary further down the same page.
 *
 * Not `role="alert"`, for the reason `SyntheticDataBanner` gives: it is a standing notice, not
 * something that just happened, and a live region firing on every navigation trains a
 * screen-reader user to tune it out.
 */
export function DemoModeBanner() {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-sky-300 bg-sky-50 px-3 py-2 text-sky-950 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100 print:rounded-lg">
      <FlaskConicalIcon
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400"
      />
      <p className="min-w-0 text-xs leading-relaxed">
        <strong className="font-semibold">Demo-Modus:</strong> Es werden{" "}
        <strong>synthetische Testdaten</strong> verarbeitet.{" "}
        <strong>Keine echten Patientendaten.</strong> Die hier geprüfte
        PADnext-Lieferung ist eine mitgelieferte Beispieldatei mit neun bewusst
        eingebauten Fehlern — es wurde nichts hochgeladen, und diese Seite nimmt
        keine Dateien entgegen. Die Prüfung selbst läuft durch dieselbe Engine
        wie im Pilotbetrieb: gleiche Regeln, gleicher Katalog, gleicher
        Receipt-Hash.
      </p>
    </div>
  )
}
