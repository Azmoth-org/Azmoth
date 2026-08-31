/**
 * `GET /api/engine/rules/review-queue` → `GET {ENGINE_BASE_URL}/api/v1/rules/review-queue`
 *
 * `kind` and `limit` are forwarded as given. They are validated by the engine — a bad `kind` is a
 * `422` there with the allowed values in it, which is a better message than anything this proxy
 * could invent, so nothing is re-checked here.
 *
 * Gated by `RULE_REVIEW_ENABLED` alongside the screen it serves. A deployment that hides `/rules`
 * but leaves its queue readable has hidden a screen and not the capability, and this endpoint is
 * the half a caller can reach without one.
 *
 * **`/api/engine/rules/coverage` is deliberately not gated.** It is the same URL prefix and a
 * different question: the dashboard's System-Health card and the rule-coverage banner on every
 * audit screen read it to say how much of the catalog the engine can speak to. That number is part
 * of the product's honesty about its own limits, and it must render whether or not this deployment
 * has the tooling to change it.
 */

import { notFound } from "next/navigation"

import { callEngine, proxyResponse } from "@/lib/engine"
import { RULE_REVIEW_ENABLED } from "@/lib/features"

export async function GET(request: Request): Promise<Response> {
  if (!RULE_REVIEW_ENABLED) notFound()

  const incoming = new URL(request.url).searchParams
  const forwarded = new URLSearchParams()
  for (const name of ["kind", "limit"]) {
    const value = incoming.get(name)
    if (value) forwarded.set(name, value)
  }
  const query = forwarded.toString()
  return proxyResponse(
    await callEngine(`/api/v1/rules/review-queue${query ? `?${query}` : ""}`)
  )
}
