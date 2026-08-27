/**
 * `POST /api/engine/proposals/{id}/reject` → the engine's rejection endpoint.
 *
 * The engine requires both `rejected_by` and `reason`, and a rejection is terminal.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json(
      {
        error: "invalid_request_body",
        message: "Der Request-Body ist kein gültiges JSON.",
      },
      { status: 400 }
    )
  }

  return proxyResponse(
    await callEngine(`/api/v1/proposals/${encodeURIComponent(id)}/reject`, {
      method: "POST",
      body,
    })
  )
}
