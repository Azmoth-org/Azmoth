/**
 * `POST /api/engine/rules/{ruleId}/review`
 *   → `POST {ENGINE_BASE_URL}/api/v1/rules/{ruleId}/review`
 *
 * A billing expert's verdict on one machine-extracted rule. The engine stores it in Postgres and
 * merges it into the running rule store before answering, so the coverage in the response is what
 * the next audit will actually use — see the engine route for why that matters.
 *
 * The CSVs in `data/rules/` are never written by this path. They are versioned source data.
 *
 * Gated by `RULE_REVIEW_ENABLED`, and this is the one of the two rule proxies where it matters
 * most: a verdict here changes the running rule store, so the next audit any customer runs answers
 * differently. A deployment that does not show the workbench must not accept its writes either.
 */

import { notFound } from "next/navigation"

import { callEngine, proxyResponse } from "@/lib/engine"
import { RULE_REVIEW_ENABLED } from "@/lib/features"

export async function POST(
  request: Request,
  { params }: { params: Promise<{ ruleId: string }> }
): Promise<Response> {
  if (!RULE_REVIEW_ENABLED) notFound()

  const { ruleId } = await params

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json(
      {
        error: "unreadable_request_body",
        message:
          "Die Bewertung benötigt einen JSON-Body mit status und reviewed_by.",
      },
      { status: 400 }
    )
  }

  return proxyResponse(
    await callEngine(`/api/v1/rules/${encodeURIComponent(ruleId)}/review`, {
      method: "POST",
      body,
    })
  )
}
