/**
 * `GET /api/engine/billing/invoices` → `GET {ENGINE_BASE_URL}/api/v1/billing/invoices`
 *
 * The practice's closed billing periods, newest first — one row per period that ended, with the plan
 * it was priced under and every amount in euro cents.
 *
 * `limit` is forwarded when the client sends one and otherwise left to the engine's default. It is
 * not clamped here: the engine declares its own bounds (`ge=1`, `le=120`) and a second, different
 * ceiling in this file would be a limit somebody eventually has to reconcile with that one.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function GET(request: Request): Promise<Response> {
  const limit = new URL(request.url).searchParams.get("limit")
  const path = limit
    ? `/api/v1/billing/invoices?limit=${encodeURIComponent(limit)}`
    : "/api/v1/billing/invoices"

  return proxyResponse(await callEngine(path))
}
