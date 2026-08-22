/**
 * Display-only labelling for the rule review screen.
 *
 * Nothing here computes anything a decision depends on. The one number it derives is a percentage
 * for a progress bar, from two integer counts the engine sends — no money is involved anywhere on
 * this screen, which is the one thing that makes arithmetic here unremarkable.
 */

import type { RuleKind } from "@/lib/rules/client"

export type KindPresentation = {
  label: string
  /** One line on what the rule type does — a reviewer needs it to judge the extraction. */
  hint: string
  /** How the Ziffern relate, read left to right. Rendered between them in the table. */
  connector: string
  className: string
}

/**
 * Exhaustive over the contract's closed union, so a fifth rule type fails this build rather than
 * rendering a raw identifier in a table a billing expert is making decisions from.
 *
 * The order they are offered in is not the order they are declared in — see `KIND_ORDER`.
 */
export const KIND: Record<RuleKind, KindPresentation> = {
  zielleistung: {
    label: "Zielleistung",
    hint: "Die Kindleistung ist methodisch notwendiger Bestandteil der Zielleistung und daher nicht gesondert berechnungsfähig (§ 4 Abs. 2a GOÄ).",
    connector: "enthält",
    className: "bg-destructive/10 text-destructive dark:bg-destructive/20",
  },
  exclusion: {
    label: "Ausschluss",
    hint: "Die eine Leistung ist neben der anderen nicht berechnungsfähig. Richtung prüfen: einseitig oder wechselseitig.",
    connector: "schließt aus",
    className: "bg-amber-500/10 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300",
  },
  specificity: {
    label: "Spezifität",
    hint: "Die spezifischere Ziffer verdrängt die allgemeinere.",
    connector: "vor",
    className: "bg-sky-500/10 text-sky-700 dark:bg-sky-400/15 dark:text-sky-300",
  },
  factor_cap: {
    label: "Faktor-Obergrenze",
    hint: "Die Leistungslegende begrenzt den Steigerungsfaktor unterhalb des § 5 Abs. 1 Höchstsatzes.",
    connector: "",
    className: "bg-emerald-500/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300",
  },
}

/**
 * The order the filter offers the types in, and it is a recommendation about *work*, not taste.
 *
 * Zielleistung first because a wrong Zielleistung rule is the most expensive kind of mistake here:
 * it removes a position a practice was entitled to charge, so verifying a bad one turns revenue
 * into a false finding. Factor caps last because a wrong one only ever lowers a factor.
 */
export const KIND_ORDER: RuleKind[] = ["zielleistung", "exclusion", "specificity", "factor_cap"]

/** `{ from: "30", to: "4" }` → `["Von", "Bis"]`-ish labels a German reviewer reads. */
export const ROLE_LABEL: Record<string, string> = {
  from: "von",
  to: "neben",
  parent: "Zielleistung",
  child: "Bestandteil",
  specific: "spezifisch",
  general: "allgemein",
  ziffer: "Ziffer",
}

export const REVIEW_STATUS_LABEL: Record<string, string> = {
  VERIFIED: "verifiziert",
  REJECTED: "abgelehnt",
  PENDING: "zurückgestellt",
}

/**
 * `direction=mutual` is the difference between "5 schließt 7 aus" and "5 und 7 schließen sich
 * gegenseitig aus", which is exactly what a reviewer is checking the extraction for.
 */
export function directionLabel(direction: string | undefined): string {
  if (direction === "mutual") return "wechselseitig"
  if (direction === "one_way") return "einseitig"
  return direction ?? ""
}

/**
 * Where the rule came from, in words. `auto_extracted:ist_neben` means a regex matched the phrase
 * "ist neben … nicht berechnungsfähig" — a reviewer treats that very differently from a hand-written
 * rule, so the pattern is surfaced rather than hidden behind "automatisch".
 */
export function sourceLabel(source: string): string {
  if (!source) return "unbekannt"
  if (source.startsWith("auto_extracted:")) {
    return `automatisch extrahiert (${source.slice("auto_extracted:".length)})`
  }
  if (source === "manual") return "manuell erfasst"
  return source
}

/** Integer counts to a bar width. No money is involved on this screen. */
export function progressPercent(done: number, total: number): number {
  if (!Number.isFinite(done) || !Number.isFinite(total) || total <= 0) return 0
  return Math.min(100, Math.max(0, (done / total) * 100))
}

/** `0.4482` → `"44.8 %"`. Same helper the audit screens use, kept local to avoid a cross-import. */
export function percent(ratio: number): string {
  if (!Number.isFinite(ratio)) return "—"
  return `${(ratio * 100).toFixed(1)} %`
}
