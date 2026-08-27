/**
 * `GET /api/engine/proposals/{id}` → `GET {ENGINE_BASE_URL}/api/v1/proposals/{id}`
 *
 * Proposals are persisted by the engine, so a `404` here now means what it says: no proposal was
 * ever stored under this id. It used to be the routine consequence of an engine restart, which is
 * why the UI's hint for `proposal_not_found` changed with it.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params
  return proxyResponse(
    await callEngine(`/api/v1/proposals/${encodeURIComponent(id)}`)
  )
}
