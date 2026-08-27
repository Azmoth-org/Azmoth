/**
 * `GET /api/engine/padnext/batch/{batchId}` → `GET {ENGINE_BASE_URL}/api/v1/padnext/batch/{batchId}`
 *
 * The polling endpoint. Answers with progress while the batch runs and with the roll-up plus every
 * file's report once it is done — which is why the response is deliberately not cached anywhere:
 * `callEngine` sends `cache: "no-store"`, and a poll served from a cache would show a batch frozen
 * at the moment of its first tick.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ batchId: string }> }
): Promise<Response> {
  const { batchId } = await params
  return proxyResponse(
    await callEngine(`/api/v1/padnext/batch/${encodeURIComponent(batchId)}`)
  )
}
