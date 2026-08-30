/**
 * `GET /api/engine/settings/usage` → `GET {ENGINE_BASE_URL}/api/v1/settings/usage`
 *
 * What this practice consumed, for the window the engine chooses (the current calendar month in
 * UTC) unless `since` / `until` say otherwise.
 *
 * The query string is forwarded rather than dropped, so the screen can ask for a different period
 * later without this route changing. It is not validated here: the engine parses the two timestamps
 * and answers `422` with the field-level detail, and a second, weaker opinion in the proxy could
 * only disagree with it.
 *
 * Not cached. A usage figure is the one number where a stale answer is actively misleading — it is
 * what somebody checks an invoice against.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function GET(request: Request): Promise<Response> {
  const query = new URL(request.url).searchParams.toString()
  const path = `/api/v1/settings/usage${query ? `?${query}` : ""}`

  return proxyResponse(await callEngine(path))
}
