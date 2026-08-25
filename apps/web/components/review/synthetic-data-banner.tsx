import { TriangleAlertIcon } from "lucide-react"

/**
 * The statements a reviewer must see on every load, not once in an onboarding flow.
 *
 * This is not decoration. The engine has no access control, no audit logging and no PHI handling,
 * and its output is a draft that a physician remains responsible for. See
 * `docs/compliance/PRIVATE_DATA_WARNING.md`.
 *
 * ## Why it is amber, and one third the height
 *
 * It was a red `Alert` with a three-item bulleted list, and it was the largest and loudest thing
 * above the fold on every screen in the product. Two things were wrong with that.
 *
 * **Red is for something that has gone wrong.** Nothing has: this is the standing configuration of
 * the build, true on every load, and it will be true on the next one. Red is spent here on a
 * constant, which leaves nothing to say it with when a position is actually suppressed or the
 * solver actually times out. Amber is the right register — unresolved, not broken.
 *
 * **A warning nobody can avoid reading is a warning nobody reads.** Sixteen lines of red at the top
 * of every screen is trained past within a day, and the training generalises: the next red box gets
 * skipped too. One compact amber strip in the reader's peripheral vision, present every single
 * time, survives longer than a wall does.
 *
 * **Every statement survived.** The bullets are one sentence each and are all still here, in the
 * same order and with the same emphasis — the list markup went, the content did not. That is the
 * whole constraint on this component: it may get quieter, it may not get shorter in substance.
 *
 * Not `role="alert"`. It is a standing notice rather than something that just happened, and a live
 * region that fires on every navigation trains a screen-reader user to tune it out exactly the way
 * the red box trained everyone else. In document order at the top of the page it is read anyway.
 */
export function SyntheticDataBanner() {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100 print:rounded-lg">
      <TriangleAlertIcon
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400"
      />
      <p className="min-w-0 text-xs leading-relaxed">
        <strong className="font-semibold">Nur synthetische Demodaten — kein Echtbetrieb.</strong> Es
        dürfen <strong>ausschließlich synthetische Testdaten</strong> verarbeitet werden: keine
        Patientendaten, keine echten Rechnungen. Das System implementiert keine Zugriffskontrolle,
        keine Protokollierung und keinen § 203 StGB-Workflow. Das Ergebnis ist ein{" "}
        <strong>Abrechnungsvorschlag (Entwurf)</strong> und <strong>keine Rechnung</strong>. Die{" "}
        <strong>ärztliche Prüfung ist zwingend erforderlich</strong> — die Regelabdeckung ist
        unvollständig, die Engine ersetzt keine fachliche Entscheidung.
      </p>
    </div>
  )
}
