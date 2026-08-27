/**
 * `POST /api/engine/rules/{ruleId}/review`
 *   → `POST {ENGINE_BASE_URL}/api/v1/rules/{ruleId}/review`
 *
 * A billing expert's verdict on one machine-extracted rule. The engine stores it in Postgres and
 * merges it into the running rule store before answering, so the coverage in the response is what
 * the next audit will actually use — see the engine route for why that matters.
 *
 * The CSVs in `data/rules/` are never written by this path. They are versioned source data.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function POST(
  request: Request,
  { params }: { params: Promise<{ ruleId: string }> }
): Promise<Response> {
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
