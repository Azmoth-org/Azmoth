/**
 * `GET /api/engine/proposals/{id}` → `GET {ENGINE_BASE_URL}/api/v1/proposals/{id}`
 *
 * Proposals live in the engine's memory and do not survive a restart, so a `404` here is expected
 * rather than exceptional — the UI says so instead of implying the proposal was deleted.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params
  return proxyResponse(await callEngine(`/api/v1/proposals/${encodeURIComponent(id)}`))
}
