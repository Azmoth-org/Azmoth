/**
 * Types for the PADnext audit screen. Every shape resolves into `@workspace/contracts`, which is
 * generated from the engine's own OpenAPI document — nothing is duplicated here.
 */

import type {
  PadnextAuditReport,
  PadnextAuditedPosition,
  PadnextFinding,
  PadnextPositionBucket,
  PadnextVerdict,
} from "@workspace/contracts"

import { toReviewError, type ReviewError } from "@/lib/review/types"

export type {
  PadnextAuditReport,
  PadnextAuditedPosition,
  PadnextFinding,
  PadnextPositionBucket,
  PadnextVerdict,
}

export type PadnextResult =
  | { kind: "report"; report: PadnextAuditReport }
  | { kind: "error"; error: ReviewError }

export { toReviewError }
export type { ReviewError }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

/**
 * Checks only what the screen reads, and only its kind — the same contract as
 * `isProposalShape`, for the same reason: a route handler returns `unknown`, and a version skew
 * between engine and UI must render as a named error rather than an empty table.
 *
 * The three bucket totals are checked explicitly. They are the whole reason this screen exists, and
 * an engine old enough to still be sending `at_risk_eur` would otherwise render every bucket as
 * `undefined` — three dashes where the money should be, with no indication anything was wrong.
 */
export function isAuditReportShape(
  value: unknown
): value is PadnextAuditReport {
  if (!isRecord(value)) return false
  if (!Array.isArray(value.positions)) return false
  if (!Array.isArray(value.findings)) return false
  for (const field of [
    "claimed_total_eur",
    "confirmed_fine_eur",
    "confirmed_wrong_eur",
    "unconfirmed_eur",
  ]) {
    if (typeof value[field] !== "string") return false
  }
  if (typeof value.coverage_ratio !== "number") return false
  return true
}
