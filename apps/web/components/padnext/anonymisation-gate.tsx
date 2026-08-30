"use client"

import { ShieldAlertIcon } from "lucide-react"

import { Checkbox } from "@workspace/ui/components/checkbox"
import { Label } from "@workspace/ui/components/label"

/**
 * The confirmation a pilot user gives before the file picker will open.
 *
 * ## What this is for, and what it is honestly not
 *
 * It is **not** the control that stops real patient data being processed. That control is in the
 * engine: `app/padnext/audit.py` refuses a delivery flagged `echtdaten="true"` with
 * `REAL_DATA_REFUSED`, before a single position is read, and no checkbox on this page can switch
 * that off. A gate whose only enforcement is a tickbox in a browser is not a gate.
 *
 * What it *is* for is the moment before the mistake. The realistic failure in a pilot is not
 * somebody defeating a control — it is somebody exporting from their PVS, forgetting the
 * anonymisation step, and uploading out of habit. A deliberate act placed between "I have a file"
 * and "the picker is open" is the cheapest intervention that addresses that, and it is the same
 * reason `restore-db.sh` makes an operator type the database name rather than offering `--force`.
 *
 * It also does something the engine's refusal cannot: it puts the obligation in writing, in the
 * user's own language, at the moment they accept it. Under § 203 StGB the practice — not us —
 * carries the duty of confidentiality, and "the software told me it was fine" is not a defence
 * either party wants to rely on. This is the sentence that makes the division of responsibility
 * explicit rather than assumed.
 *
 * ## Why it resets on every file
 *
 * The parent clears this after each upload. A confirmation that stayed ticked for a session would
 * be given once, on the first file, and then silently cover the twentieth — which is exactly the
 * upload that will be the un-anonymised one, because by then it is routine. Per file is the only
 * granularity at which the statement is true.
 */
export function AnonymisationGate({
  checked,
  onCheckedChange,
}: {
  checked: boolean
  onCheckedChange: (next: boolean) => void
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-950 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
      <ShieldAlertIcon
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400"
      />
      <div className="min-w-0 space-y-3">
        <div className="flex items-start gap-3">
          <Checkbox
            id="anonymisation-confirmed"
            checked={checked}
            onCheckedChange={(value) => onCheckedChange(value === true)}
            className="mt-0.5 border-amber-600 dark:border-amber-400"
            aria-describedby="anonymisation-consequence"
          />
          <Label
            htmlFor="anonymisation-confirmed"
            className="text-xs leading-relaxed font-normal"
          >
            Ich bestätige, dass ich das Azmoth-Anonymisierungsskript ausgeführt
            habe und die hochgeladene Datei das Attribut{" "}
            <code className="font-mono">echtdaten=&quot;false&quot;</code>{" "}
            enthält. Das Hochladen von echten Patientendaten (
            <code className="font-mono">echtdaten=&quot;true&quot;</code>) ist
            strengstens untersagt und führt zur sofortigen Sperrung.
          </Label>
        </div>

        <p
          id="anonymisation-consequence"
          className="text-xs leading-relaxed text-amber-900/80 dark:text-amber-100/70"
        >
          Diese Bestätigung ersetzt keine technische Prüfung: Die Engine weist
          eine als Echtdaten gekennzeichnete Lieferung ohnehin ab, bevor eine
          einzige Position gelesen wird. Sie steht hier, weil die
          Verantwortung für die Pseudonymisierung bei der Praxis liegt und der
          Zeitpunkt, an dem sie übernommen wird, benannt sein sollte.
        </p>
      </div>
    </div>
  )
}
