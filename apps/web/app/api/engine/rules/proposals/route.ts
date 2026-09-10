/**
 * `POST /api/engine/rules/proposals`
 *   → `POST {ENGINE_BASE_URL}/api/v1/rules/proposals`
 *
 * A pilot's report that a Ziffer has no rule at all — the "Regel fehlt? Ziffer melden" button on an
 * audit report. Unlike `/api/engine/rules/[ruleId]/review`, this writes nothing into the running
 * rule store and is not gated by `RULE_REVIEW_ENABLED`: it is a feedback channel for every pilot,
 * not part of the internal review workbench.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function POST(request: Request): Promise<Response> {
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json(
      {
        error: "unreadable_request_body",
        message: "Die Meldung benötigt einen JSON-Body mit ziffer und context.",
      },
      { status: 400 }
    )
  }

  return proxyResponse(
    await callEngine("/api/v1/rules/proposals", { method: "POST", body })
  )
}
