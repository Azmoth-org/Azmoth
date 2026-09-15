import { TriangleAlertIcon } from "lucide-react"

/**
 * The statements a reviewer must see on every load, not once in an onboarding flow.
 *
 * This is not decoration. The output is a draft that a physician remains responsible for, the rule
 * coverage is partial, and the pilot accepts synthetic data only. See
 * `docs/compliance/PRIVATE_DATA_WARNING.md`.
 *
 * ## What this banner used to say, and why it no longer says it
 *
 * It claimed the system "implementiert keine Zugriffskontrolle, keine Protokollierung und keinen
 * § 203 StGB-Workflow". All three were true when they were written and none of them is true now,
 * and a standing notice that overstates the gaps is not a conservative error — it is a false
 * statement about the product, printed on every screen, read by the customer evaluating it.
 *
 *   - **Zugriffskontrolle.** Every screen is behind `requireSession()`, sign-up is behind
 *     `SIGNUP_ALLOWLIST`, and the organisation is enforced rather than merely displayed:
 *     `lib/engine.ts` forwards `activeOrganizationId` on every call, every engine read filters on
 *     it and every write stamps it, and a request carrying none is refused with a `403`
 *     (`apps/engine/app/api/tenancy.py`).
 *   - **Protokollierung.** `audit_events` exists and is append-only by construction — one row per
 *     thing that happened to a proposal, `CREATED`/`VIEWED`/`APPROVED`/`REJECTED`/`EXPORTED`,
 *     written once and never updated (`apps/engine/app/db/models.py`). "Keine Protokollierung" was
 *     simply false.
 *   - **§ 203 StGB.** The workflow the clause is about is *not processing patient data*, and that
 *     is exactly what the pilot does: synthetic deliveries only, `@echtdaten` enforced at the
 *     reader, real data refused.
 *
 * **The logging sentence is scoped to what actually writes a log row, and that took a rewrite.**
 * `audit_events` is keyed to a proposal, so the append-only row is written by the `/review`
 * (Freigabe-)workflow this banner sits above — and *not* by the stateless single PADnext audit
 * (`POST /padnext/audit`, which stores nothing at all; see the module docstring in
 * `apps/engine/app/api/padnext.py`) nor by a batch (`services/batch_audit.py` says so at the point
 * where it would write one). An earlier draft of this sentence said "jede Prüfung schreibt einen
 * Eintrag", which is true of `/review` and was not true of either PADnext path — an overclaim two
 * of this banner's own three mount points would have made false the moment a reader tested it. The
 * wording below says "der Freigabe-Workflow" rather than "jede Prüfung" for exactly that reason:
 * closing the gap for real means giving `audit_events` a delivery-scoped row, which is a schema
 * change and is deferred, not a sentence to word around in the meantime.
 *
 * What survives is the set of constraints that are still real: synthetic data only, the result is a
 * draft and not an invoice, and the rule coverage is partial so a medical review is required. Those
 * three are the whole content of this component and they may get quieter, never shorter in
 * substance.
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
 * Not `role="alert"`. It is a standing notice rather than something that just happened, and a live
 * region that fires on every navigation trains a screen-reader user to tune it out exactly the way
 * the red box trained everyone else. In document order at the top of the page it is read anyway.
 */
export function SyntheticDataBanner() {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950 print:rounded-lg">
      <TriangleAlertIcon
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-amber-600"
      />
      <p className="min-w-0 text-xs leading-relaxed">
        <strong className="font-semibold">
          Dieser Pilotbetrieb arbeitet ausschließlich mit synthetischen
          Testdaten.
        </strong>{" "}
        Ihre Sitzung ist authentifiziert, Ihre Organisation ist isoliert, und
        der Freigabe-Workflow schreibt jeden Schritt in ein
        append-only-Protokoll. Es werden keine Patientendaten verarbeitet.
        Das Ergebnis ist ein{" "}
        <strong>Abrechnungsvorschlag (Entwurf)</strong> und{" "}
        <strong>keine Rechnung</strong>. Die{" "}
        <strong>ärztliche Prüfung ist zwingend erforderlich</strong> — die
        Regelabdeckung ist unvollständig, die Engine ersetzt keine fachliche
        Entscheidung.
      </p>
    </div>
  )
}
