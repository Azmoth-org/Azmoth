/**
 * `POST /api/engine/billing/upgrade` → `POST {ENGINE_BASE_URL}/api/v1/billing/upgrade`
 *
 * Changes the signed-in practice's plan.
 *
 * **This is the one route in this directory that only a session can reach**, and the engine enforces
 * that rather than trusting this proxy: `/api/v1/billing/upgrade` requires the organisation header
 * and does not accept an API key, because a plan change is a commercial commitment and a bearer
 * token sitting in a PVS vendor's configuration must not be able to escalate its own entitlements.
 *
 * The body is passed through and validated by the engine, which is where the rules live: exactly one
 * of `tier` or `plan_code`, and a `422` when both or neither is given. Duplicating that check here
 * would be a second place for it to disagree.
 *
 * An unparsable body is forwarded as `{}` rather than refused locally, so the caller gets the
 * engine's own German explanation of what to send instead of this proxy's guess at one.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function POST(request: Request): Promise<Response> {
  let body: unknown = {}
  try {
    body = await request.json()
  } catch {
    body = {}
  }

  return proxyResponse(
    await callEngine("/api/v1/billing/upgrade", { method: "POST", body })
  )
}
