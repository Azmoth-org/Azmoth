/**
 * `DELETE /api/engine/settings/api-keys/{keyId}`
 *   → `DELETE {ENGINE_BASE_URL}/api/v1/settings/api-keys/{keyId}`
 *
 * Revoke one key. The row is kept and marked; the engine refuses every later request carrying it.
 *
 * Idempotent, so the UI's confirmation dialog does not have to guard against a double click, and a
 * key belonging to another practice answers `404` rather than `403` — the engine's scoping, not
 * this route's, and the reason is written down there: a `403` would confirm that a guessed key id
 * exists.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ keyId: string }> }
): Promise<Response> {
  const { keyId } = await params

  return proxyResponse(
    await callEngine(`/api/v1/settings/api-keys/${encodeURIComponent(keyId)}`, {
      method: "DELETE",
    })
  )
}
