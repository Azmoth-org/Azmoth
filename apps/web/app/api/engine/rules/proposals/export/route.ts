/**
 * `GET /api/engine/rules/proposals/export`
 *   → `GET {ENGINE_BASE_URL}/api/v1/rules/proposals/export`
 *
 * The organisation's own `Regel fehlt? Ziffer melden` reports as one CSV — everything the listing
 * pages through, in one file. No body on the way in and nothing to attribute: like the batch
 * export beside this one, this is read-only and produces the same bytes on every call.
 */

import { proxyEngineDownload } from "@/lib/engine"

export async function GET(): Promise<Response> {
  return proxyEngineDownload("/api/v1/rules/proposals/export", { method: "GET" })
}
