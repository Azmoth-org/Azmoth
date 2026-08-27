"use client"

import { PrinterIcon } from "lucide-react"

import { Button } from "@workspace/ui/components/button"

/**
 * Print the proposal.
 *
 * `window.print()` rather than a generated PDF, deliberately. The screen is already the document —
 * the print stylesheet in `@workspace/ui` drops the navigation, restores the light palette so a
 * dark-mode reader does not print white on white, and opens every collapsed section — so the browser
 * has everything it needs, and a reader who wants a file uses "Als PDF sichern" in the same dialog.
 * A second rendering path would be a second place for the money to be wrong.
 *
 * The export button beside it is a different thing and stays: that produces the engine's own signed
 * JSON, which is the machine-readable record. This produces the sheet a physician signs.
 */
export function PrintButton() {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => window.print()}
      className="print:hidden"
    >
      <PrinterIcon />
      Drucken
    </Button>
  )
}
