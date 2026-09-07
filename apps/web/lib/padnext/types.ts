/**
 * Types for the PADnext audit screen. Every shape resolves into `@workspace/contracts`, which is
 * generated from the engine's own OpenAPI document — nothing is duplicated here.
 */

import type {
  PadnextAuditReport,
  PadnextAuditedPosition,
  PadnextFinding,
  PadnextParsedPreview,
  PadnextPositionBucket,
  PadnextValidationIssue,
  PadnextValidationReport,
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

// ------------------------------------------------------------------------------------------
// batched validation
// ------------------------------------------------------------------------------------------

export type {
  PadnextParsedPreview,
  PadnextValidationIssue,
  PadnextValidationReport,
}

/**
 * Pull the batched validation report out of an engine error, or return `null`.
 *
 * The engine's refusal envelope is unchanged — `error_code`, `message`, `details` — and every
 * PADnext refusal now carries the *whole* list of problems under `details`, beside the keys that
 * were already there (`details.line` for malformed XML, `details.violations` for a schema failure,
 * `details.echtdaten_declared` for an undeclared one). See `app/padnext/validation.py`.
 *
 * `null` is the load-bearing return, not an edge case. Three things reach `ErrorPanel` that have
 * no validation report at all: a failure that is not about the delivery (`QUOTA_EXCEEDED`,
 * `RULES_ENGINE_UNAVAILABLE`), a failure from the proxy rather than the engine
 * (`proxy_unreachable`), and an engine deployed before this shape existed. All three must render
 * as the plain error panel they always did, so this guard checks the shape rather than the status
 * — a screen that assumed the list was present would show an empty "0 Fehler" card for a 503.
 *
 * Checks only what the components read, and only its kind, exactly as `isAuditReportShape` does
 * and for the same reason: re-validating a generated contract in the browser duplicates it and
 * then drifts from it.
 */
export function toValidationReport(
  error: ReviewError
): PadnextValidationReport | null {
  const details = error.details
  if (!isRecord(details)) return null
  if (typeof details.status !== "string") return null
  if (!["valid", "validation_failed", "parse_failed"].includes(details.status)) {
    return null
  }
  if (!Array.isArray(details.errors) || !Array.isArray(details.warnings)) {
    return null
  }
  if (typeof details.error_count !== "number") return null
  if (!isRecord(details.parsed_preview)) return null
  return details as unknown as PadnextValidationReport
}

/**
 * The German text for one issue, falling back down the chain the engine guarantees.
 *
 * `message_de` is always populated — the catalog enforces it and a test asserts it — but the
 * reader's own findings arrive with an empty `message_en`, so a component must never reach for the
 * English half first. The final fallback is the code, which is ugly and readable; an empty string
 * would be a card with a badge and nothing in it.
 */
export function issueText(issue: PadnextValidationIssue): string {
  return issue.message_de || issue.message_en || issue.code
}
