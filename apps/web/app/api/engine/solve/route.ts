/**
 * `POST /api/engine/solve` → `POST {ENGINE_BASE_URL}/api/v1/solve`
 *
 * The body is forwarded unchanged. The engine owns validation: a typo in the extraction comes back
 * as a `422` naming the field, and this route passes that through rather than trying to pre-empt it.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function POST(request: Request): Promise<Response> {
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json(
      { error: "invalid_request_body", message: "Der Request-Body ist kein gültiges JSON." },
      { status: 400 },
    )
  }

  return proxyResponse(await callEngine("/api/v1/solve", { method: "POST", body }))
}
