"use client"

import { Checkbox } from "@workspace/ui/components/checkbox"
import { Label } from "@workspace/ui/components/label"

/**
 * The confirmation a pilot user gives before the file is submitted.
 *
 * ## What this is for, and what it is honestly not
 *
 * It is **not** the control that stops real patient data being processed. That control is in the
 * engine: `app/padnext/audit.py` refuses a delivery flagged `echtdaten="true"` — and one that does
 * not declare itself at all — before a single position is read, and no checkbox in a browser can
 * switch that off. `SyntheticDataNotice`, above the upload card, is the one place this page states
 * that rule; this card exists only to ask for the anonymisation confirmation itself, so the two
 * are not saying the same thing twice.
 *
 * What it *is* for is the moment before the mistake. The realistic failure in a pilot is not
 * somebody defeating a control — it is somebody exporting from their PVS, forgetting the
 * anonymisation step, and uploading out of habit. A deliberate, explicit act next to the submit
 * button is the cheapest intervention that addresses that.
 *
 * ## Why it resets on every file
 *
 * The parent clears this after each upload attempt. A confirmation that stayed ticked would be
 * given once, on the first file, and then silently cover the twentieth — which is exactly the
 * upload that will be the un-anonymised one, because by then it is routine. Per file is the only
 * granularity at which the statement is true.
 */
export function AnonymisationGate({
  checked,
  onCheckedChange,
  disabled,
}: {
  checked: boolean
  onCheckedChange: (next: boolean) => void
  /** True until a file is selected — there is nothing to confirm about yet. */
  disabled?: boolean
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border bg-muted/30 p-3">
      <Checkbox
        id="anonymisation-confirmed"
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onCheckedChange(value === true)}
        className="mt-0.5"
        aria-describedby="anonymisation-helper"
      />
      <div className="min-w-0 space-y-1">
        <Label
          htmlFor="anonymisation-confirmed"
          className="block min-w-0 text-sm leading-relaxed font-normal break-words"
        >
          Ich bestätige, dass diese Datei mit dem Azmoth-Anonymisierungsskript
          erzeugt wurde.
        </Label>
        <p
          id="anonymisation-helper"
          className="text-xs leading-relaxed text-muted-foreground"
        >
          Die Originaldatei bleibt in der Praxis. Das Skript erstellt eine neue
          Testdatei.
        </p>
      </div>
    </div>
  )
}
