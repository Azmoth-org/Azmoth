/**
 * How many records are in a given state — the four figures the dashboard's metric row is made of.
 *
 * ## Why this is a `total` and not a `length`
 *
 * Both list endpoints answer with `{ items | jobs, limit, offset, total }`, and `total` counts every
 * row matching the request's filters rather than the page. That field is the entire reason these
 * tiles can exist: a count is a one-request read (`?status=DRAFT&limit=1`) instead of a walk over
 * every page, and the number is honest about a backlog far larger than anything the screen shows.
 *
 * `limit=1` rather than `limit=0`, because the engine's schema puts a `minimum: 1` on it — a zero is
 * a `422`, not an empty page. One row is the cheapest legal request, and on `/proposals` "cheapest"
 * is not a figure of speech: a row there is a full `Proposal` carrying its whole `solver_result` and
 * every proof tree, which is why the activity card already asks for five rather than the default
 * fifty.
 *
 * ## An unavailable count is `null`, never `0`
 *
 * This is the load-bearing decision in the module. The dashboard's job is to say whether anything is
 * waiting; a failed read rendered as `0` says *nothing is waiting*, which is the one wrong answer a
 * status screen must not give. So a call that failed, or answered with a body that is not the
 * envelope, resolves to `null` — and `MetricCard` paints that as an em dash.
 *
 * The guards are the dashboard's own (`isProposalList`, `isBatchAuditJobList`), for the reason they
 * were written: an engine older than the paginated envelope answers these paths with a bare JSON
 * array, and reading `.total` off that yields `undefined` rather than throwing — a tile that would
 * silently print an em dash forever instead of a count. Validating first means the failure is the
 * described one.
 */

import { callEngine } from "@/lib/engine"
import {
  isBatchAuditJobList,
  isProposalList,
  totalOrPageLength,
} from "@/lib/dashboard/types"

/** The cheapest page the engine will sell. See the note above on `minimum: 1`. */
const ONE_ROW = "limit=1"

/**
 * How many proposals are in `status`, or `null` if the engine did not say.
 *
 * `status` is a `Proposal["status"]` rather than a string so a typo is a build failure here instead
 * of a `422` rendered as an em dash — the engine validates this value against a closed enum.
 */
export async function countProposals(
  status: "DRAFT" | "APPROVED" | "REJECTED" | "EXPORTED"
): Promise<number | null> {
  const result = await callEngine(
    `/api/v1/proposals?status=${status}&${ONE_ROW}`
  )
  if (!result.ok || !isProposalList(result.body)) return null
  return totalOrPageLength(result.body.total, result.body.items?.length ?? 0)
}

/** How many batch runs are in `status`, or `null` if the engine did not say. */
export async function countBatches(
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED"
): Promise<number | null> {
  const result = await callEngine(
    `/api/v1/padnext/batch?status=${status}&${ONE_ROW}`
  )
  if (!result.ok || !isBatchAuditJobList(result.body)) return null
  return totalOrPageLength(result.body.total, result.body.jobs?.length ?? 0)
}

/**
 * Whether this organisation has ever had anything to show — across every status, not one at a
 * time. `null` when either read failed, exactly like every other count in this module: a broken
 * engine call must not be read as "this is a fresh organisation" and steer a signed-in reader into
 * the first-run cards instead of the ordinary (if currently broken) dashboard.
 *
 * Unfiltered, unlike `countProposals` / `countBatches` above — this is the one place the dashboard
 * asks "anything at all", so a single `DRAFT` or `PENDING` count would answer the wrong question
 * for an organisation whose only proposal has already been approved.
 */
export async function hasAnyDeliveries(): Promise<boolean | null> {
  const [proposals, batches] = await Promise.all([
    callEngine(`/api/v1/proposals?${ONE_ROW}`),
    callEngine(`/api/v1/padnext/batch?${ONE_ROW}`),
  ])

  if (!proposals.ok || !isProposalList(proposals.body)) return null
  if (!batches.ok || !isBatchAuditJobList(batches.body)) return null

  const proposalTotal = totalOrPageLength(
    proposals.body.total,
    proposals.body.items?.length ?? 0
  )
  const batchTotal = totalOrPageLength(
    batches.body.total,
    batches.body.jobs?.length ?? 0
  )
  return proposalTotal > 0 || batchTotal > 0
}

/**
 * Two counts into one, keeping "unknown" contagious.
 *
 * The "Stapel in Arbeit" tile is queued *plus* running, which is two requests, and the arithmetic
 * matters: if either read failed, the sum is not a smaller number, it is an unknown one. Adding a
 * `null` as zero would print a figure that is quietly missing half its input — the same lie as a
 * failed read rendering as `0`, one level up.
 */
export function sumOrUnknown(...counts: (number | null)[]): number | null {
  return counts.some((count) => count === null)
    ? null
    : counts.reduce((total: number, count) => total + (count ?? 0), 0)
}
