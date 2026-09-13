import { TriangleAlertIcon } from "lucide-react"

/**
 * The one statement on `/padnext` about what Azmoth will and will not accept as input.
 *
 * This page used to carry that message twice: the page-level `SyntheticDataBanner` above the
 * workbench, and a second explanation of the engine's `echtdaten` refusal inside
 * `AnonymisationGate`, beneath the confirmation checkbox. Two banners saying "no real data" in
 * different words is not two safeguards — it is one message read twice and skipped the second
 * time. This is the single copy; `AnonymisationGate` now only asks for the anonymisation
 * confirmation itself.
 *
 * Not `SyntheticDataBanner`, and not exported for reuse: that component's wording is shared with
 * `/review`, `/padnext/batch` and the dashboard, and rewording it here would change those screens
 * too. This one is `/padnext`-specific on purpose.
 */
export function SyntheticDataNotice() {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950 print:rounded-lg">
      <TriangleAlertIcon
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-amber-600"
      />
      <p className="min-w-0 text-xs leading-relaxed">
        <strong className="font-semibold">Nur synthetische Testdaten.</strong>{" "}
        Azmoth nimmt im Pilotbetrieb keine Echtdaten an. Lieferungen mit{" "}
        <code className="font-mono">echtdaten=true</code> oder ohne eindeutige
        Testdaten-Kennzeichnung werden abgelehnt.
      </p>
    </div>
  )
}
