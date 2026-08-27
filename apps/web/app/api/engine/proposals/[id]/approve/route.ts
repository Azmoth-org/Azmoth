/**
 * `POST /api/engine/proposals/{id}/approve` → the engine's approval endpoint.
 *
 * The engine requires `approved_by` and refuses an approval nobody signed with a `422`; a proposal
 * that is not in `DRAFT` comes back as `409 illegal_transition`. Both are passed through.
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
    await callEngine(`/api/v1/proposals/${encodeURIComponent(id)}/approve`, {
      method: "POST",
      body,
    })
  )
}
