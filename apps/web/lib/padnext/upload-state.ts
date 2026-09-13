/**
 * Whether the "PADnext-Datei prüfen" button may be pressed, and what to tell the reader when it
 * cannot be.
 *
 * A pure function rather than inline JSX conditionals so the three states — no file, file but
 * unconfirmed, ready — are one thing to get right and one thing to test, instead of three `disabled`
 * expressions that can drift from the three reason strings beside them.
 */
export type PruefenButtonState = {
  disabled: boolean
  /** `null` when enabled, or while pending — the spinner label already says what is happening. */
  reason: string | null
}

export function pruefenButtonState({
  hasFile,
  confirmed,
  pending,
}: {
  hasFile: boolean
  confirmed: boolean
  pending: boolean
}): PruefenButtonState {
  if (pending) return { disabled: true, reason: null }
  if (!hasFile) return { disabled: true, reason: "Bitte PADnext-Datei auswählen." }
  if (!confirmed) return { disabled: true, reason: "Bitte Anonymisierung bestätigen." }
  return { disabled: false, reason: null }
}
