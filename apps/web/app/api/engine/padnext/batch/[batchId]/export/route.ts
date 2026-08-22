/**
 * `POST /api/engine/padnext/batch/{batchId}/export`
 *   → `POST {ENGINE_BASE_URL}/api/v1/padnext/batch/{batchId}/export`
 *
 * Answers with `batch_{batchId}_export.zip`, or a `409` when the batch has not completed. No body
 * on the way in: a batch export is read-only and attributed to nobody, unlike a proposal export
 * — see the engine route for why the two differ.
 */

import { proxyEngineDownload } from "@/lib/engine"

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ batchId: string }> },
): Promise<Response> {
  const { batchId } = await params
  return proxyEngineDownload(
    `/api/v1/padnext/batch/${encodeURIComponent(batchId)}/export`,
    { method: "POST" },
  )
}
