/**
 * Types for the batch audit screen. Every shape resolves into `@workspace/contracts`, which is
 * generated from the engine's own OpenAPI document — nothing is duplicated here.
 *
 * The runtime guards exist for the same reason as `isAuditReportShape`: a route handler returns
 * `unknown`, and a version skew between engine and UI has to render as a named error rather than a
 * dashboard of undefineds where the money belongs.
 */

import type {
  BatchAggregateSummary,
  BatchAuditAccepted,
  BatchAuditJob,
  BatchFileResult,
  BatchFileStatus,
  BatchJobStatus,
} from "@workspace/contracts"

import { toReviewError, type ReviewError } from "@/lib/review/types"

export type {
  BatchAggregateSummary,
  BatchAuditAccepted,
  BatchAuditJob,
  BatchFileResult,
  BatchFileStatus,
  BatchJobStatus,
}

export { toReviewError }
export type { ReviewError }

export type BatchUploadResult =
  | { kind: "accepted"; accepted: BatchAuditAccepted }
  | { kind: "error"; error: ReviewError }

export type BatchJobResult =
  | { kind: "job"; job: BatchAuditJob }
  | { kind: "error"; error: ReviewError }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

/** The `202` body: only the handle matters, and it is the only thing checked. */
export function isBatchAcceptedShape(value: unknown): value is BatchAuditAccepted {
  return isRecord(value) && typeof value.batch_id === "string" && value.batch_id.length > 0
}

/**
 * Checks what the screen reads, and only its kind.
 *
 * `aggregate_summary` is deliberately **not** required: it is null for the whole time the job is
 * running, which is most of the polling. What must be present on every tick is the status and the
 * counts the progress indicator divides, so those are what is checked.
 */
export function isBatchJobShape(value: unknown): value is BatchAuditJob {
  if (!isRecord(value)) return false
  if (typeof value.batch_id !== "string") return false
  if (typeof value.status !== "string") return false
  if (!Array.isArray(value.files)) return false
  for (const field of ["file_count", "processed_file_count", "completed_file_count", "failed_file_count"]) {
    if (typeof value[field] !== "number") return false
  }
  return true
}

/**
 * Whether the aggregate carries the three buckets this screen exists to show.
 *
 * Separate from `isBatchJobShape` because it is a different question asked at a different time: an
 * engine old enough to send a single `at_risk_eur` would pass the job check and then render three
 * empty cards. Checked at the moment the dashboard is about to be drawn.
 */
export function hasBucketFields(summary: unknown): summary is BatchAggregateSummary {
  if (!isRecord(summary)) return false
  for (const field of [
    "claimed_total_eur",
    "confirmed_fine_eur",
    "confirmed_wrong_eur",
    "unconfirmed_eur",
  ]) {
    if (typeof summary[field] !== "string") return false
  }
  return typeof summary.coverage_ratio === "number"
}

/** A job that will not change again, so the poll can stop. */
export function isTerminal(status: BatchJobStatus): boolean {
  return status === "COMPLETED" || status === "FAILED"
}
