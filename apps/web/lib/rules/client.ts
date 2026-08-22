/**
 * Browser-side calls to the rule review proxy.
 *
 * Same contract as every other client here: never throws, never returns a half-parsed body. The
 * screen renders either data whose fields it can trust, or a named error with the raw details.
 *
 * Every shape resolves into `@workspace/contracts`, generated from the engine's own OpenAPI
 * document — nothing is duplicated.
 */

import type {
  ReviewableRule,
  RuleCoverage,
  RuleKind,
  RuleReviewQueue,
  RuleReviewRequest,
  RuleReviewResult,
} from "@workspace/contracts"

import { toReviewError, type ReviewError } from "@/lib/review/types"

export type {
  ReviewableRule,
  RuleCoverage,
  RuleKind,
  RuleReviewQueue,
  RuleReviewRequest,
  RuleReviewResult,
}
export type { ReviewError }

export type QueueResult =
  | { kind: "queue"; queue: RuleReviewQueue }
  | { kind: "error"; error: ReviewError }

export type CoverageResult =
  | { kind: "coverage"; coverage: RuleCoverage }
  | { kind: "error"; error: ReviewError }

export type ReviewResult =
  | { kind: "reviewed"; result: RuleReviewResult }
  | { kind: "error"; error: ReviewError }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

async function readJson(
  response: Response,
): Promise<{ ok: true; body: unknown } | { ok: false; error: ReviewError }> {
  const raw = await response.text()

  if (raw.length === 0) {
    return {
      ok: false,
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
      ok: false,
      error: {
        error: "unparsable_response",
        message: "Die Antwort ist kein gültiges JSON.",
        status: response.status,
        details: raw.slice(0, 4000),
      },
    }
  }

  if (!response.ok) return { ok: false, error: toReviewError(response.status, body) }
  return { ok: true, body }
}

function unreachable(cause: unknown): { kind: "error"; error: ReviewError } {
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

function skew(status: number, body: unknown, what: string): { kind: "error"; error: ReviewError } {
  return {
    kind: "error",
    error: {
      error: "unexpected_response_shape",
      message:
        `Die Engine hat geantwortet, aber der Body enthält ${what}. Möglicherweise laufen ` +
        "Engine und UI auf verschiedenen Contract-Versionen — packages/contracts neu generieren.",
      status,
      details: body,
    },
  }
}

/**
 * Checks the counts the dashboard divides by, and nothing else.
 *
 * `total_constraint_rules` in particular: a progress bar built on an absent denominator renders
 * `NaN%`, which reads as a broken tool rather than as a version skew.
 */
function isQueueShape(value: unknown): value is RuleReviewQueue {
  if (!isRecord(value)) return false
  if (!Array.isArray(value.rules)) return false
  for (const field of [
    "total_constraint_rules",
    "verified_rule_count",
    "review_verified_rule_count",
    "rejected_rule_count",
    "pending_rule_count",
  ]) {
    if (typeof value[field] !== "number") return false
  }
  return true
}

function isCoverageShape(value: unknown): value is RuleCoverage {
  return (
    isRecord(value) &&
    typeof value.enforced_rule_count === "number" &&
    typeof value.unverified_rule_count === "number" &&
    typeof value.total_constraint_rule_count === "number"
  )
}

export async function fetchReviewQueue(
  options: { kind?: RuleKind | null; limit?: number } = {},
): Promise<QueueResult> {
  const params = new URLSearchParams()
  if (options.kind) params.set("kind", options.kind)
  if (options.limit) params.set("limit", String(options.limit))
  const query = params.toString()

  let response: Response
  try {
    response = await fetch(`/api/engine/rules/review-queue${query ? `?${query}` : ""}`, {
      cache: "no-store",
    })
  } catch (cause) {
    return unreachable(cause)
  }

  const parsed = await readJson(response)
  if (!parsed.ok) return { kind: "error", error: parsed.error }
  if (!isQueueShape(parsed.body)) {
    return skew(response.status, parsed.body, "keine lesbare Prüfliste")
  }
  return { kind: "queue", queue: parsed.body }
}

export async function fetchRuleCoverage(): Promise<CoverageResult> {
  let response: Response
  try {
    response = await fetch("/api/engine/rules/coverage", { cache: "no-store" })
  } catch (cause) {
    return unreachable(cause)
  }

  const parsed = await readJson(response)
  if (!parsed.ok) return { kind: "error", error: parsed.error }
  if (!isCoverageShape(parsed.body)) {
    return skew(response.status, parsed.body, "keine lesbare Regelabdeckung")
  }
  return { kind: "coverage", coverage: parsed.body }
}

export async function submitRuleReview(
  ruleId: string,
  payload: RuleReviewRequest,
): Promise<ReviewResult> {
  let response: Response
  try {
    response = await fetch(`/api/engine/rules/${encodeURIComponent(ruleId)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  } catch (cause) {
    return unreachable(cause)
  }

  const parsed = await readJson(response)
  if (!parsed.ok) return { kind: "error", error: parsed.error }
  if (!isRecord(parsed.body) || !isRecord(parsed.body.rule)) {
    return skew(response.status, parsed.body, "keine bewertete Regel")
  }
  return { kind: "reviewed", result: parsed.body as RuleReviewResult }
}
