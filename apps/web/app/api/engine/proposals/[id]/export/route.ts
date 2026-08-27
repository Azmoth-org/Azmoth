/**
 * `POST /api/engine/proposals/{id}/export` → `POST {ENGINE_BASE_URL}/api/v1/proposals/{id}/export`
 *
 * The engine answers with the export document as an attachment, and with a `409` when the proposal
 * is not `APPROVED`. Both are passed through untouched: the `409` body carries the current status,
 * which is what the screen shows the reviewer.
 *
 * The body — `{ exported_by, note }` — is forwarded as given. `exported_by` is required by the
 * engine and recorded in the audit log; it is not authenticated here or anywhere else yet.
 */

import { proxyEngineDownload } from "@/lib/engine"

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
        error: "unreadable_request_body",
        message:
          "Der Export benötigt einen JSON-Body mit dem Feld exported_by.",
      },
      { status: 400 }
    )
  }

  return proxyEngineDownload(
    `/api/v1/proposals/${encodeURIComponent(id)}/export`,
    {
      method: "POST",
      body,
    }
  )
}
