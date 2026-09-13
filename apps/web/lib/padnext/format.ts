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
  return amount === null || amount === undefined || amount === ""
    ? "—"
    : `${amount} €`
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

/**
 * The five fields any presentation of the three buckets needs, and nothing else.
 *
 * `PadnextAuditReport` (one invoice) and `BatchAggregateSummary` (a whole upload) both satisfy it
 * structurally, which is the point: the batch dashboard renders the *same* cards as the single-file
 * view rather than a second set that could word the amber bucket more aggressively. Written as a
 * standalone type rather than as `Pick<PadnextAuditReport, …>` so it is obvious that the aggregate
 * is not a report and is not being treated as one.
 *
 * The four amounts are exact decimal strings from the engine and stay strings. Only
 * `coverage_ratio` is a number, because the engine publishes it as one precisely so a client never
 * has to divide money.
 */
export type BucketFigures = {
  claimed_total_eur: string
  confirmed_fine_eur: string
  confirmed_wrong_eur: string
  unconfirmed_eur: string
  coverage_ratio: number
}

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
    action:
      "Handlungsbedarf: Diese Positionen sind so nicht berechnungsfähig. Rückforderung wahrscheinlich.",
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
 * because the system is otherwise monochrome and defines no success or warning token. Each is a
 * single light-mode palette: this application renders on one theme, so a bucket colour has exactly
 * one ground to be legible on, and the `dark:` halves these used to carry went with the theme.
 */
export const BUCKET_TONE_CLASS: Record<
  BucketTone,
  { text: string; badge: string; bar: string }
> = {
  wrong: {
    text: "text-destructive",
    badge: "bg-destructive/10 text-destructive",
    bar: "bg-destructive",
  },
  fine: {
    text: "text-emerald-700",
    badge: "bg-emerald-500/10 text-emerald-700",
    bar: "bg-emerald-600",
  },
  unknown: {
    text: "text-amber-700",
    badge: "bg-amber-500/10 text-amber-700",
    bar: "bg-amber-500",
  },
}

function toPositiveNumber(amount: string | null | undefined): number {
  const parsed = Number(amount)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/**
 * The coverage bar's fill, as a percentage of the track — or `null` when there is nothing to fill
 * at all, which must render as an empty track rather than a fill of 0.
 *
 * The fill used to be sized from the three bucket amounts (`unconfirmed`'s share of the claimed
 * total), which is a different number from `coverage_ratio` and can disagree with it: an invoice
 * where nothing has been judged puts 100 % of the money in `unconfirmed`, so the bar rendered
 * filled edge-to-edge in amber under a label reading "Prüfabdeckung 0.0 %" — and a bar filled
 * edge-to-edge reads as 100 % regardless of which colour fills it. There is no independent
 * computation here any more: the fill *is* `coverage_ratio`, clamped so a stale or malformed value
 * from the engine cannot overflow the track in either direction.
 *
 * `null` covers two cases the caller must render identically: a missing/non-numeric ratio (the
 * engine sending something a stale client cannot interpret), and a claim with no usable
 * denominator (`claimed_total_eur` not a positive number) — the ratio would be `0.0` in that case
 * too, per the engine's own convention, but there is nothing to show a fill *against*.
 */
export function coverageFillPercent(
  ratio: number | null | undefined,
  claimedTotalEur: string | null | undefined
): number | null {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return null
  if (toPositiveNumber(claimedTotalEur) <= 0) return null
  return clamp(ratio * 100, 0, 100)
}

/**
 * How the coverage fill splits between the two verdicts it is made of.
 *
 * Sized against `confirmed_wrong_eur` and `confirmed_fine_eur` directly, in proportion to each
 * other, and then scaled so the two segments always sum to exactly `fillPercent` — never a
 * fraction of the *whole claim* that could round to something other than the number printed above
 * the bar. `unconfirmed` has no segment here: it is the gap, and the gap is the untouched part of
 * the track, not a third colour painted over it.
 */
export function coverageVerdictWidths(
  figures: Pick<BucketFigures, "confirmed_wrong_eur" | "confirmed_fine_eur">,
  fillPercent: number
): { wrong: number; fine: number } {
  const wrong = toPositiveNumber(figures.confirmed_wrong_eur)
  const fine = toPositiveNumber(figures.confirmed_fine_eur)
  const total = wrong + fine
  if (total <= 0) return { wrong: 0, fine: 0 }
  return {
    wrong: (wrong / total) * fillPercent,
    fine: (fine / total) * fillPercent,
  }
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
  // A percentage Zuschlag (e.g. Nummer 441/5298) — in the catalog, priced by law as a share of
  // another Ziffer's fee rather than its own Punktzahl, so there is nothing here to have missed.
  // Distinct from `unknown_ziffer` on purpose; see the verdict field's docstring in
  // apps/engine/app/schemas/padnext.py.
  surcharge_not_modelled: "Zuschlag nicht abgebildet",
}

export const SEVERITY_LABEL: Record<"info" | "warning" | "error", string> = {
  info: "Hinweis",
  warning: "Warnung",
  error: "Fehler",
}

const SEVERITY_ORDER: Record<string, number> = { error: 0, warning: 1, info: 2 }

export function bySeverity(
  a: { severity: string },
  b: { severity: string }
): number {
  return (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3)
}
