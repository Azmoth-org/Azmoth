/**
 * What the dashboard reads, and the guards that decide whether it actually arrived.
 *
 * The types all resolve into `@workspace/contracts`, which is generated from the engine's own
 * OpenAPI document — no shape is redescribed here.
 *
 * The guards exist because `callEngine` returns `unknown`, and on this screen that matters more than
 * it does elsewhere. The dashboard is the first page anyone opens, it renders three independent
 * cards, and the generated types describe what the engine *published* rather than what a running
 * engine actually sent. An older engine still answers `GET /api/v1/proposals` — it just answers with
 * a bare JSON array, because the paginated envelope is newer than the endpoint. Casting that to
 * `ProposalList` and reading `.items.map` would throw inside a server component and take the whole
 * page down, including the two cards that had nothing wrong with them. So each list is validated to
 * the depth the card renders and no further: is there an array of rows, and does a row carry the
 * fields the row component reads.
 */

import type {
  BatchAuditJobList,
  BatchAuditJobSummary,
  HealthResponse,
  Proposal,
  ProposalList,
  RuleCoverage,
} from "@workspace/contracts"

export type { BatchAuditJobSummary, HealthResponse, Proposal, RuleCoverage }

/**
 * A row on the dashboard, whichever list it came from.
 *
 * The two cards render the same four things — an identifier, a status, one line of context and a
 * timestamp — so they share a row component, and this is what it takes. Written as its own type
 * rather than a union of the two contract models because the row must not be able to reach for a
 * field only one of them has: a listing row is a summary, and the moment it can read
 * `solver_result` somebody will.
 */
export type ActivityRow = {
  /** The public handle — `prop_…` or `batch_…`. Shown truncated, and the whole thing is the link. */
  id: string
  /** Where the row goes. See the note on deep links in `components/dashboard/activity-row.tsx`. */
  href: string
  /** One line of context: the case id, or how many files a batch carries. */
  detail: string
  /** ISO-8601, as the engine wrote it. Formatted for display, never parsed for meaning. */
  createdAt: string | null | undefined
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0
}

/**
 * A `ProposalList` whose rows carry at least what the card renders.
 *
 * `status` is checked as a string rather than against the four known values on purpose. An unknown
 * status is a rendering problem for one badge — `statusPresentation` falls back to the raw value —
 * and not a reason to refuse the whole card and tell the reader the engine is unreachable when it
 * plainly is not.
 */
export function isProposalList(value: unknown): value is ProposalList {
  if (!isRecord(value) || !Array.isArray(value.items)) return false
  return value.items.every(
    (item) =>
      isRecord(item) &&
      isNonEmptyString(item.proposal_id) &&
      isNonEmptyString(item.status)
  )
}

export function isBatchAuditJobList(
  value: unknown
): value is BatchAuditJobList {
  if (!isRecord(value) || !Array.isArray(value.jobs)) return false
  return value.jobs.every(
    (job) =>
      isRecord(job) &&
      isNonEmptyString(job.batch_id) &&
      isNonEmptyString(job.status)
  )
}

/**
 * `total` when the engine sent a usable one, and the page length otherwise.
 *
 * Never `undefined`: the card prints "5 von N", and a missing N there would read as a bug rather
 * than as a missing field. Falling back to the page length understates the table, which is the safe
 * direction — it can only make the card claim *less* than there is.
 */
export function totalOrPageLength(total: unknown, pageLength: number): number {
  return typeof total === "number" &&
    Number.isFinite(total) &&
    total >= pageLength
    ? total
    : pageLength
}
