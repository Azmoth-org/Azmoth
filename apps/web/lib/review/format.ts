/**
 * Display-only formatting.
 *
 * **No monetary arithmetic happens in this app.** Every amount, factor and rate the engine returns
 * is an exact decimal string (the engine uses `Decimal` end to end and serialises to a string
 * precisely so that a JavaScript client cannot round it). These helpers therefore only ever *append*
 * or *label* — they never parse an amount into a number, never add, and never re-round. The original
 * string always reaches the DOM.
 */

import type {
  BlockedReason,
  FactorBasis,
  ProposalStatus,
  WarningSeverity,
} from "@/lib/review/types"

/** `"130.39"` → `"130.39 €"`. The digits are untouched. */
export function eur(amount: string | null | undefined): string {
  return amount === null || amount === undefined || amount === ""
    ? "—"
    : `${amount} €`
}

/**
 * `"2.6"` → `"2.6-fach"`.
 *
 * The decimal separator is deliberately **not** localised to a comma. Every number on this screen is
 * covered by the receipt hash, and a reviewer who copies a figure into a dispute letter must copy
 * exactly what the engine emitted. Mixing `2,6-fach` with `24.25 €` on one audit screen is worse
 * than either convention applied consistently, so the engine's own string wins everywhere.
 */
export function factor(value: string | null | undefined): string {
  if (!value) return "—"
  return `${value}-fach`
}

/** `"0.25"` → `"0.25"`. Kept as the engine wrote it; the label says what it means. */
export function rate(value: string | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : value
}

export function shortHash(
  hash: string | null | undefined,
  length = 16
): string {
  if (!hash) return "—"
  return hash.length <= length ? hash : `${hash.slice(0, length)}…`
}

export function timestamp(value: string | null | undefined): string {
  if (!value) return "—"
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString("de-DE", {
    dateStyle: "medium",
    timeStyle: "medium",
  })
}

// ------------------------------------------------------------------------------------------
// closed unions from the contract — exhaustive, so a new value fails the build
// ------------------------------------------------------------------------------------------

export const PROPOSAL_STATUS_LABEL: Record<ProposalStatus, string> = {
  DRAFT: "Entwurf",
  APPROVED: "Freigegeben",
  REJECTED: "Abgelehnt",
  EXPORTED: "Exportiert",
}

export const BLOCKED_REASON_LABEL: Record<BlockedReason, string> = {
  exclusion: "Ausschluss",
  mutual_exclusion: "Wechselseitiger Ausschluss",
  zielleistung: "Zielleistung (§ 4 Abs. 2a GOÄ)",
  less_specific: "Weniger spezifisch",
  unknown_ziffer: "Ziffer nicht im Katalog",
  inactive_ziffer: "Ziffer nicht aktiv",
  conflict_lost: "Arbitrierung verloren",
}

export const SEVERITY_LABEL: Record<WarningSeverity, string> = {
  info: "Hinweis",
  warning: "Warnung",
  error: "Fehler",
}

// ------------------------------------------------------------------------------------------
// open strings from the contract — labelled where known, passed through where not
// ------------------------------------------------------------------------------------------

/**
 * `factor_basis` is a closed union in the contract, so this mapping is exhaustive: TypeScript fails
 * the build if the engine adds a basis and nobody labels it. It used to be an open `string` with a
 * fallback that printed the raw identifier at a reviewer.
 */
const FACTOR_BASIS_LABEL: Record<FactorBasis, string> = {
  einfachsatz: "Einfachsatz",
  schwellenwert: "Schwellenwert",
  ueber_schwellenwert: "über Schwellenwert",
  hoechstsatz: "Höchstsatz",
  capped: "Leistungslegende begrenzt",
}

export function factorBasis(value: FactorBasis | null | undefined): string {
  if (!value) return "—"
  return FACTOR_BASIS_LABEL[value]
}

const LINE_STATUS_LABEL: Record<string, string> = {
  billable: "berechnungsfähig",
  billable_analog: "Analogansatz (§ 6 Abs. 2 GOÄ)",
}

export function lineStatus(value: string | null | undefined): string {
  if (!value) return "—"
  return LINE_STATUS_LABEL[value] ?? value
}

/**
 * Warning types the engine emits that a reviewer must not scroll past. Everything else is rendered
 * in the normal severity order.
 */
export const PROMINENT_WARNING_TYPES = new Set<string>([
  "solver_timeout_partial",
  "analog_collision",
  "blocking_basis_removed",
  "justification_missing",
  "factor_above_hoechstsatz",
  "factor_above_leistungslegende_cap",
  "unknown_ziffer",
  "inactive_ziffer",
  "mapping_references_unknown_ziffer",
])

export function isProminentWarning(
  type: string,
  severity: WarningSeverity
): boolean {
  return severity === "error" || PROMINENT_WARNING_TYPES.has(type)
}

const SEVERITY_ORDER: Record<WarningSeverity, number> = {
  error: 0,
  warning: 1,
  info: 2,
}

export function bySeverity<
  T extends { severity: WarningSeverity; type: string },
>(a: T, b: T): number {
  const prominence =
    Number(isProminentWarning(b.type, b.severity)) -
    Number(isProminentWarning(a.type, a.severity))
  if (prominence !== 0) return prominence
  return SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
}

/**
 * The same seven reasons, short enough to be a badge.
 *
 * `BLOCKED_REASON_LABEL` is the full sentence — "Zielleistung (§ 4 Abs. 2a GOÄ)" — and it is what a
 * reader needs once they are looking at *one* suppression. It is not what they need while scanning
 * a column of them: at that moment the paragraph reference is the same width as the reason and
 * carries none of the distinction between rows. So the badge in the Grund column is the short form,
 * and the full label plus the legal basis is in the row's expanded detail, where it is being read
 * rather than scanned.
 *
 * Exhaustive over the same closed union, so a new reason still fails the build in both places.
 */
export const BLOCKED_REASON_SHORT: Record<BlockedReason, string> = {
  exclusion: "Ausschluss",
  mutual_exclusion: "Wechselausschluss",
  zielleistung: "Zielleistung",
  less_specific: "Weniger spezifisch",
  unknown_ziffer: "Unbekannte Ziffer",
  inactive_ziffer: "Ziffer inaktiv",
  conflict_lost: "Arbitrierung",
}

/**
 * A scannable German title for each warning type the engine emits.
 *
 * `warning.type` is an identifier — `factor_above_leistungslegende_cap` — and a column of those is
 * unreadable at a glance even though every character of it is meaningful. The map gives the row a
 * title a reader can scan; the identifier itself stays in the expanded detail, because it is what
 * you quote in a bug report and what joins this row to the engine's own logs.
 *
 * Deliberately **not** exhaustive and deliberately not a closed union: `type` is an open string in
 * the contract, the engine adds types without a frontend release, and an unlabelled one must render
 * as itself rather than as "Unbekannt". `warningTitle` falls back to the raw identifier.
 */
const WARNING_TYPE_LABEL: Record<string, string> = {
  advisory_rules_present: "Beratende Regeln vorhanden",
  analog_collision: "Analog-Kollision",
  analog_uncovered: "Analogansatz ohne Regeldeckung",
  analogansatz_requires_human_review: "Analogansatz muss geprüft werden",
  blocking_basis_removed: "Sperrgrund entfallen",
  catalog_text_quality: "Textqualität im Katalog",
  exclusion_chain_detected: "Ausschlusskette erkannt",
  factor_above_hoechstsatz: "Faktor über Höchstsatz",
  factor_above_leistungslegende_cap: "Faktor über Legendengrenze",
  inactive_ziffer: "Ziffer nicht aktiv",
  justification_missing: "Begründung fehlt",
  justification_target_not_billable: "Begründung ohne berechnete Position",
  justification_target_unknown: "Begründung auf unbekannte Ziffer",
  low_extraction_confidence: "Extraktion unsicher",
  mapping_references_inactive_ziffer: "Mapping auf inaktive Ziffer",
  mapping_references_unknown_ziffer: "Mapping auf unbekannte Ziffer",
  minderung_applied: "Minderung nach § 6a GOÄ",
  rule_coverage_incomplete: "Regelabdeckung unvollständig",
  solver_timeout_partial: "Solver abgebrochen",
  unknown_ziffer: "Ziffer nicht im Katalog",
}

export function warningTitle(type: string): string {
  return WARNING_TYPE_LABEL[type] ?? type
}
