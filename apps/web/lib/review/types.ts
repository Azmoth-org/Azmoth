/**
 * Types for the review screen. Everything resolves into `@workspace/contracts`, which is generated
 * from the engine's own OpenAPI document — no schema is duplicated here.
 *
 * The runtime guards at the bottom exist because a route handler returns `unknown`: the generated
 * types describe what the engine *published*, not what actually arrived. A stale engine, a proxy
 * error body or a version skew must render as a readable error, never as a crash.
 */

import type {
  BlockedCode,
  Coding,
  CodingResponse,
  FactorBasis,
  InvoiceLine,
  MissingDocumentation,
  Proposal,
  ProposalStatus,
  RuleCoverage,
} from "@workspace/contracts"

export type {
  BlockedCode,
  Coding,
  CodingResponse,
  FactorBasis,
  InvoiceLine,
  MissingDocumentation,
  Proposal,
  ProposalStatus,
  RuleCoverage,
}

export type AuditTrail = CodingResponse["audit_trail"]
export type ProofStep = NonNullable<InvoiceLine["proof"]>[number]
export type EngineWarning = NonNullable<Coding["warnings"]>[number]
export type WarningSeverity = EngineWarning["severity"]
export type BlockedReason = BlockedCode["reason"]

/** What the review screen renders instead of a proposal when something went wrong. */
export type ReviewError = {
  error: string
  message: string
  /** HTTP status, when the failure came from a response rather than the browser. */
  status?: number
  /** Anything the engine or the proxy attached. Rendered as raw JSON — never parsed for meaning. */
  details?: unknown
}

export type ReviewResult =
  | { kind: "proposal"; proposal: Proposal }
  | { kind: "error"; error: ReviewError }

// ------------------------------------------------------------------------------------------
// runtime guards
// ------------------------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isStringArrayFriendly(value: unknown): boolean {
  return value === undefined || Array.isArray(value)
}

/**
 * Checks only the fields the screen actually reads, and only their kind.
 *
 * Deliberately not a full schema validation: re-validating the whole contract in the browser would
 * duplicate the generated types and drift from them. This asks "can I render this without throwing?"
 * — anything narrower belongs in the engine, which already validates.
 */
export function isProposalShape(value: unknown): value is Proposal {
  if (!isRecord(value)) return false
  if (typeof value.proposal_id !== "string") return false
  if (typeof value.status !== "string") return false
  if (typeof value.receipt_hash !== "string") return false
  if (typeof value.catalog_version !== "string") return false
  if (typeof value.rules_version !== "string") return false
  if (typeof value.solver_version !== "string") return false

  const result = value.solver_result
  if (!isRecord(result)) return false

  const coding = result.coding
  if (!isRecord(coding)) return false
  if (!isStringArrayFriendly(coding.proposed_codes)) return false
  if (!isStringArrayFriendly(coding.blocked_codes)) return false
  if (!isStringArrayFriendly(coding.warnings)) return false
  if (!isStringArrayFriendly(coding.missing_documentation)) return false
  if (coding.total !== undefined && !isRecord(coding.total)) return false

  if (!isRecord(result.audit_trail)) return false

  return true
}

/** A proxy or engine error body. Both shapes carry `error` + `message`, or FastAPI's `detail`. */
export function toReviewError(status: number, body: unknown): ReviewError {
  if (isRecord(body)) {
    // The proxy's own failures.
    if (typeof body.error === "string" && typeof body.message === "string") {
      return { error: body.error, message: body.message, status, details: body.details }
    }
    // FastAPI: `{"detail": ...}` — either our structured dict or a validation-error array.
    if ("detail" in body) {
      const detail = body.detail
      if (isRecord(detail) && typeof detail.error === "string") {
        return {
          error: detail.error,
          message: typeof detail.message === "string" ? detail.message : `HTTP ${status}`,
          status,
          details: detail,
        }
      }
      return {
        error: status === 422 ? "validation_error" : `http_${status}`,
        message:
          status === 422
            ? "Die Engine hat die Eingabe abgelehnt (Schemaverstoß). Details unten."
            : `Die Engine hat mit HTTP ${status} geantwortet.`,
        status,
        details: detail,
      }
    }
  }

  return {
    error: `http_${status}`,
    message: `Unerwartete Antwort der Engine (HTTP ${status}).`,
    status,
    details: body,
  }
}
