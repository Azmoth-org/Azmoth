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
 * engine: `app/padnext/audit.py` refuses the delivery before a single position is read, and no
 * checkbox on this page can switch that off. A gate whose only enforcement is a tickbox in a
 * browser is not a gate.
 *
 * That refusal is three-valued, and the middle case is the one this text has to get right:
 *
 *   - `echtdaten="1"` / `"true"`  → `REAL_DATA_REFUSED`
 *   - `echtdaten="0"` / `"false"` → audited
 *   - anything else, including **absent** → `ECHTDATEN_UNDECLARED`
 *
 * The third row is new and it changes what a user has to do rather than merely what they must not
 * do. Before it, an export that said nothing was audited on the assumption that silence meant
 * synthetic; a file therefore reached a report without anyone having run anything. Now a delivery
 * that cannot declare itself is turned away, so `scripts/anonymize_padnext.py` is a step in the
 * workflow and not a recommendation — and the sentence beside the checkbox has to say that,
 * because a user who ticks a box asserting they ran a script they have never seen is being asked
 * to lie.
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
            Ich bestätige, dass ich diese Datei mit dem
            Azmoth-Anonymisierungsskript{" "}
            <code className="font-mono">scripts/anonymize_padnext.py</code>{" "}
            erzeugt habe und dass sie keine Patientendaten mehr enthält —
            insbesondere keinen Namen, keine Anschrift, kein Geburtsdatum und
            keine Versichertennummer. Das Hochladen echter Patientendaten ist
            untersagt.
          </Label>
        </div>

        <p
          id="anonymisation-consequence"
          className="text-xs leading-relaxed text-amber-900/80 dark:text-amber-100/70"
        >
          Diese Bestätigung ersetzt keine technische Prüfung. Die Engine weist
          eine Lieferung ab, die als Echtdaten gekennzeichnet ist — und ebenso
          eine, die sich gar nicht erklärt: Fehlt das Attribut{" "}
          <code className="font-mono">echtdaten</code> oder trägt es einen Wert
          wie <code className="font-mono">&quot;ja&quot;</code>, wird die Datei
          mit <code className="font-mono">ECHTDATEN_UNDECLARED</code>{" "}
          zurückgewiesen. Eine fehlende Angabe gilt nicht als „Testdaten“. Das
          Skript setzt{" "}
          <code className="font-mono">echtdaten=&quot;false&quot;</code> in der
          Auftragsdatei und in den Nutzdaten und ist damit der übliche Weg, eine
          Datei überhaupt hochladbar zu machen.
        </p>

        <p className="text-xs leading-relaxed text-amber-900/80 dark:text-amber-100/70">
          Das Skript entfernt keinen Freitext. Prüfen Sie die Felder{" "}
          <code className="font-mono">text</code> und{" "}
          <code className="font-mono">begruendung</code> selbst — das Skript
          meldet auffällige Stellen am Ende seines Laufs. Was es genau entfernt
          und warum das Ergebnis nicht mehr unter Art. 9 DSGVO fällt, steht in{" "}
          <code className="font-mono">docs/pilot/ANONYMIZATION_SPEC.md</code>.
        </p>
      </div>
    </div>
  )
}
