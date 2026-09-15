/**
 * `POST /api/engine/rules/proposals`  → `POST {ENGINE_BASE_URL}/api/v1/rules/proposals`
 * `GET  /api/engine/rules/proposals`  → `GET  {ENGINE_BASE_URL}/api/v1/rules/proposals`
 *
 * A pilot's report that a Ziffer has no rule at all — the "Regel fehlt? Ziffer melden" button on an
 * audit report — and the listing that reads those reports back. Unlike
 * `/api/engine/rules/[ruleId]/review`, neither writes to nor reads from the running rule store and
 * neither is gated by `RULE_REVIEW_ENABLED`: this is a feedback channel for every pilot, not part
 * of the internal review workbench.
 *
 * The `GET` here exists for parity with the rest of `/api/engine/*` and for a client component that
 * wants to poll or re-fetch after submitting a report. The page at `/rules/proposals` does not use
 * it — a server component reads the engine directly, the same way `BatchHistoryTable` does — but a
 * route this application's own proxy convention says should exist is worth having rather than
 * leaving as "call the engine directly, this once".
 */

import { NextRequest } from "next/server"

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

export async function GET(request: NextRequest): Promise<Response> {
  const search = request.nextUrl.search
  return proxyResponse(await callEngine(`/api/v1/rules/proposals${search}`))
}
