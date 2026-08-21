/**
 * Browser-side calls to the `/api/engine/*` proxy routes.
 *
 * Every function returns a `ReviewResult` — never throws, never returns a half-parsed body. The
 * screen renders one of two things: a proposal it can trust to have the fields it reads, or an
 * error with the raw details attached.
 */

import type { ApprovalRequest, RejectionRequest, SolveRequest } from "@workspace/contracts"

import { isProposalShape, toReviewError, type ReviewResult } from "@/lib/review/types"

async function request(path: string, init?: RequestInit): Promise<ReviewResult> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch (cause) {
    return {
      kind: "error",
      error: {
        error: "proxy_unreachable",
        message:
          "Die Anfrage an /api/engine konnte nicht gesendet werden. Läuft der Next.js-Server noch?",
        details: cause instanceof Error ? cause.message : String(cause),
      },
    }
  }

  const raw = await response.text()

  if (raw.length === 0) {
    return {
      kind: "error",
      error: {
        error: "empty_response",
        message: `Leere Antwort (HTTP ${response.status}).`,
        status: response.status,
      },
    }
  }

  let body: unknown
  try {
    body = JSON.parse(raw)
  } catch {
    return {
      kind: "error",
      error: {
        error: "unparsable_response",
        message: "Die Antwort ist kein gültiges JSON.",
        status: response.status,
        details: raw.slice(0, 4000),
      },
    }
  }

  if (!response.ok) {
    return { kind: "error", error: toReviewError(response.status, body) }
  }

  if (!isProposalShape(body)) {
    // HTTP 200 with a body the screen cannot render. Named explicitly so it is obvious that the
    // engine and this UI disagree about the contract, rather than showing an empty table.
    return {
      kind: "error",
      error: {
        error: "unexpected_response_shape",
        message:
          "Die Engine hat mit HTTP 200 geantwortet, aber der Body entspricht nicht dem erwarteten " +
          "Proposal-Schema. Möglicherweise laufen Engine und UI auf verschiedenen Contract-Versionen — " +
          "packages/contracts neu generieren.",
        status: response.status,
        details: body,
      },
    }
  }

  return { kind: "proposal", proposal: body }
}

export function solveCase(payload: SolveRequest): Promise<ReviewResult> {
  return request("/api/engine/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

export function fetchProposal(proposalId: string): Promise<ReviewResult> {
  return request(`/api/engine/proposals/${encodeURIComponent(proposalId)}`)
}

export function approveProposal(
  proposalId: string,
  payload: ApprovalRequest,
): Promise<ReviewResult> {
  return request(`/api/engine/proposals/${encodeURIComponent(proposalId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

export function rejectProposal(
  proposalId: string,
  payload: RejectionRequest,
): Promise<ReviewResult> {
  return request(`/api/engine/proposals/${encodeURIComponent(proposalId)}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}
