/**
 * `?id=` — the one query parameter that turns a workbench into a permalink.
 *
 * The dashboard cards and both list pages link to `/review?id=prop_…` and `/padnext/batch?id=batch_…`.
 * Those links were emitted before either page read the parameter, so following one opened an empty
 * workbench: the row said "this proposal exists", the screen said "nothing here yet", and the reader
 * had no way to tell which was lying. This module is what the two pages read it with.
 *
 * **Three things live here rather than in the two workbenches**, because two screens inventing their
 * own answer to any of them is how one says "nicht gefunden" and the other says "HTTP 404" for the
 * same dead link:
 *
 * * the shape of an id, so a malformed one is refused before it reaches the engine;
 * * the German copy for a link that no longer resolves;
 * * whether a failure is worth a retry button at all.
 *
 * The parameter is `id` on both routes even though the engine calls them `proposal_id` and
 * `batch_id`. A URL is read by people, the route already says which kind of thing it is, and
 * `/review?proposal_id=…` says it twice.
 */

import type { ReviewError } from "@/lib/review/types"

/** Next hands each key as `string | string[] | undefined`, because `?id=a&id=b` is a legal URL. */
export type RawSearchParams = Record<string, string | string[] | undefined>

/** Which of the two things a deep link points at. Decides the id prefix and the wording. */
export type DeepLinkKind = "proposal" | "batch"

/**
 * The handles the engine issues: `prop_<16 hex>` and `batch_<16 hex>`.
 *
 * Both come from `uuid4().hex[:16]` — see `new_batch_id()` and `Pipeline.propose` — so the shape is
 * the engine's, not a guess. The length is written `{4,}` rather than `{16}` on purpose: a shorter
 * id from an older run is somebody's real record and must still resolve, while `?id=<script>` or a
 * half-copied handle is refused here instead of becoming a 404 the reader has to interpret.
 *
 * This is a *cheap* check, not authorisation. It exists so an obviously malformed link fails with a
 * sentence about the link, and it decides nothing about whether the record may be read — the engine
 * remains the only thing that answers that.
 */
const ID_PATTERN: Record<DeepLinkKind, RegExp> = {
  proposal: /^prop_[0-9a-f]{4,}$/i,
  batch: /^batch_[0-9a-f]{4,}$/i,
}

/** What each kind is called on screen. Nominative — every use below is a subject. */
const NOUN: Record<DeepLinkKind, string> = {
  proposal: "Prüfung",
  batch: "Stapelprüfung",
}

export function isWellFormedId(kind: DeepLinkKind, value: string): boolean {
  return ID_PATTERN[kind].test(value.trim())
}

/**
 * The `?id=` a page was opened with, or `null` for a plain visit.
 *
 * The first value wins when the key repeats — arbitrary but deterministic, which is what matters
 * when the alternative is a different record per request. An empty or whitespace-only `?id=` counts
 * as absent: `/review?id=` is a link somebody built wrong, and the empty workbench is a better
 * answer to it than an error about an id that was never typed.
 */
export function readDeepLinkId(raw: RawSearchParams): string | null {
  const value = raw.id
  const single = Array.isArray(value) ? value[0] : value
  if (typeof single !== "string") return null
  const trimmed = single.trim()
  return trimmed.length > 0 ? trimmed : null
}

/** A link whose id cannot be one this engine issued. Refused without a request. */
export function malformedIdError(kind: DeepLinkKind, value: string): ReviewError {
  return {
    error: kind === "proposal" ? "malformed_proposal_id" : "malformed_batch_id",
    message: `${NOUN[kind]} nicht gefunden`,
    details: {
      angefragte_id: value,
      erwartetes_format: kind === "proposal" ? "prop_<hex>" : "batch_<hex>",
    },
  }
}

/**
 * The engine's answer to a deep link, in the words this screen should use.
 *
 * Only the not-found case is rewritten, and only its `message`. The engine's own 404 text is
 * English — "No proposal prop_…. Proposals are stored durably…" — which is right for an API client
 * reading a log and wrong for the one line a reviewer sees in a red box after clicking a row on the
 * dashboard. The original travels on `details`, so nothing is hidden, and `ErrorPanel` still adds
 * its existing German hint for `proposal_not_found` / `batch_not_found` underneath.
 *
 * Every other failure is passed through untouched. A 500, a version skew or an unreachable proxy
 * already says something specific, and overwriting it with "nicht gefunden" would report a broken
 * engine as a broken link — which sends the reader to look for the wrong problem.
 */
export function toDeepLinkError(kind: DeepLinkKind, error: ReviewError): ReviewError {
  const notFound = kind === "proposal" ? "proposal_not_found" : "batch_not_found"
  if (error.error !== notFound && error.status !== 404) return error
  return {
    ...error,
    error: notFound,
    message: `${NOUN[kind]} nicht gefunden`,
    details: withEngineMessage(error),
  }
}

/**
 * The engine's own sentence, folded into `details` so that replacing `message` above hides nothing.
 *
 * Needed because the engine's error envelope carries the explanation in `message` and sends
 * `details: {}` — so `error.details ?? error.message`, the obvious version, kept the empty object
 * and dropped the only text that named the id. What the panel rendered was a promise of raw detail
 * followed by `{}`.
 */
function withEngineMessage(error: ReviewError): unknown {
  const engine = { engine_message: error.message }
  if (error.details === null || error.details === undefined) return engine
  if (typeof error.details === "object" && !Array.isArray(error.details)) {
    return { ...engine, ...(error.details as Record<string, unknown>) }
  }
  return { ...engine, details: error.details }
}

/**
 * Whether offering "Erneut versuchen" is honest.
 *
 * A retry button on a 404 is a lie: the record is not there, and pressing it a second time asks the
 * same question and gets the same answer. It is offered for the failures that genuinely pass — a
 * dead proxy, an engine still starting, a 5xx — and withheld for the ones where the answer will not
 * change until the URL does.
 *
 * Unknown errors count as retryable. The failure modes are open-ended (a proxy nobody anticipated,
 * a network stack failing in a new way), and an unnecessary button costs a wasted click where a
 * missing one costs a reload of a page the reader may have filled in.
 */
export function isRetryable(error: ReviewError): boolean {
  if (
    error.error === "proposal_not_found" ||
    error.error === "batch_not_found" ||
    error.error === "malformed_proposal_id" ||
    error.error === "malformed_batch_id"
  ) {
    return false
  }
  // A 4xx other than 408/429 is a statement about the request, and the request is the URL.
  if (error.status !== undefined && error.status >= 400 && error.status < 500) {
    return error.status === 408 || error.status === 429
  }
  return true
}
