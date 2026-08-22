/**
 * Display-only formatting for the PADnext audit screen.
 *
 * The same rule as `lib/review/format.ts`: **no monetary arithmetic happens in this app.** Every
 * amount the engine returns is an exact decimal string, and these helpers only label it. The one
 * number treated as a number is `coverage_ratio`, which the engine publishes as a float precisely
 * because it is a display ratio and never money.
 */

import type { PadnextPositionBucket, PadnextVerdict } from "@/lib/padnext/types"

/** `"130.39"` → `"130.39 €"`. The digits are untouched. */
export function eur(amount: string | null | undefined): string {
  return amount === null || amount === undefined || amount === "" ? "—" : `${amount} €`
}

/** `0.4482` → `"44.8 %"`. The engine's own ratio; never recomputed from the amounts. */
export function percent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "—"
  return `${(ratio * 100).toFixed(1)} %`
}

// ------------------------------------------------------------------------------------------
// the three buckets
// ------------------------------------------------------------------------------------------

/**
 * How each bucket is allowed to be presented. Exhaustive over the contract's closed union, so
 * adding a fourth bucket to the engine fails this build rather than rendering a raw identifier.
 *
 * `tone` carries the colour the brief asks for — red for `confirmed_wrong`, green for
 * `confirmed_fine`, amber for `unconfirmed`. Colour is never the only signal: every bucket also
 * carries a label and an icon, because a reviewer with a colour-vision deficiency, a greyscale
 * print of a dispute letter, and a screen reader must all get the same answer.
 */
export type BucketTone = "wrong" | "fine" | "unknown"

export type BucketPresentation = {
  /** The short label on a badge. */
  label: string
  /** What the number means, in one line, for the summary card. */
  headline: string
  /** What the reader is supposed to *do*. The load-bearing half. */
  action: string
  tone: BucketTone
}

export const BUCKET: Record<PadnextPositionBucket, BucketPresentation> = {
  confirmed_wrong: {
    label: "nachweislich falsch",
    headline: "Verifizierte Regel verletzt",
    action: "Handlungsbedarf: Diese Positionen sind so nicht berechnungsfähig. Rückforderung wahrscheinlich.",
    tone: "wrong",
  },
  confirmed_fine: {
    label: "bestätigt korrekt",
    headline: "Gegen verifizierte Regeln geprüft",
    action: "Sicher: Alle anwendbaren Prüfungen bestanden.",
    tone: "fine",
  },
  unconfirmed: {
    label: "unbestätigt",
    headline: "Keine verifizierte Regel anwendbar",
    action:
      "Kein Befund gegen die Praxis: Erfordert menschliche Prüfung oder Verifizierung der Regeln.",
    tone: "unknown",
  },
}

/**
 * Tailwind classes per tone, in one place so the three buckets cannot drift apart.
 *
 * `wrong` uses the design system's `destructive` token; `fine` and `unknown` use literal palettes
 * because the system is otherwise monochrome and defines no success or warning token. Both carry an
 * explicit `dark:` variant — the app is theme-aware and an amber that only works on white would
 * read as a different bucket at night.
 */
export const BUCKET_TONE_CLASS: Record<BucketTone, { text: string; badge: string; bar: string }> = {
  wrong: {
    text: "text-destructive",
    badge: "bg-destructive/10 text-destructive dark:bg-destructive/20",
    bar: "bg-destructive",
  },
  fine: {
    text: "text-emerald-700 dark:text-emerald-400",
    badge: "bg-emerald-500/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300",
    bar: "bg-emerald-600 dark:bg-emerald-500",
  },
  unknown: {
    text: "text-amber-700 dark:text-amber-400",
    badge: "bg-amber-500/10 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300",
    bar: "bg-amber-500",
  },
}

/**
 * Segment widths for the coverage bar, as percentages that sum to 100.
 *
 * This is the **one** function in this app that turns an amount string into a number, and it is
 * confined here so the exception is visible rather than scattered. What it produces is geometry — a
 * CSS width — and it is never rendered as a figure, never rounded back into an amount, and never
 * compared against another amount. The euro values on the screen come from `eur()`, straight from
 * the engine's exact decimal strings.
 *
 * Doing it this way rather than sizing the segments by position count is what keeps the bar honest:
 * the label above it is a share of *money*, and a bar that silently showed a share of *line count*
 * would contradict it — nine positions of wildly different value do not divide a bar into ninths.
 *
 * Falls back to equal-looking zero widths when the total is not a usable positive number, so a
 * zero-total delivery renders an empty track instead of `NaN%`.
 */
export function segmentWidths(
  amounts: readonly string[],
): number[] {
  const values = amounts.map((amount) => {
    const parsed = Number(amount)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
  })
  const total = values.reduce((sum, value) => sum + value, 0)
  if (total <= 0) return values.map(() => 0)
  return values.map((value) => (value / total) * 100)
}

/** The order the buckets are shown in: what to act on, what is safe, what is still open. */
export const BUCKET_ORDER: PadnextPositionBucket[] = [
  "confirmed_wrong",
  "confirmed_fine",
  "unconfirmed",
]

/**
 * The disclaimer the brief requires, kept here rather than inlined so the audit screen, a future
 * export and a print view cannot each word it slightly differently.
 */
export const UNCONFIRMED_DISCLAIMER =
  "Unbestätigte Positionen erfordern menschliche Prüfung oder die Verifizierung von Regeln. " +
  "(Unconfirmed positions require human review or rule verification.)"

// ------------------------------------------------------------------------------------------
// verdicts — the engine's rule-level conclusion, shown alongside the bucket
// ------------------------------------------------------------------------------------------

/** Exhaustive over the closed union, so an added verdict fails the build. */
export const VERDICT_LABEL: Record<PadnextVerdict, string> = {
  chargeable: "berechnungsfähig",
  blocked: "durch Regel entfernt",
  out_of_scope: "andere Gebührenordnung",
  unknown_ziffer: "Ziffer nicht im Katalog",
}

export const SEVERITY_LABEL: Record<"info" | "warning" | "error", string> = {
  info: "Hinweis",
  warning: "Warnung",
  error: "Fehler",
}

const SEVERITY_ORDER: Record<string, number> = { error: 0, warning: 1, info: 2 }

export function bySeverity(
  a: { severity: string },
  b: { severity: string },
): number {
  return (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3)
}
