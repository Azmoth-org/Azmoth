/**
 * `GET /api/engine/rules/review-queue` → `GET {ENGINE_BASE_URL}/api/v1/rules/review-queue`
 *
 * `kind` and `limit` are forwarded as given. They are validated by the engine — a bad `kind` is a
 * `422` there with the allowed values in it, which is a better message than anything this proxy
 * could invent, so nothing is re-checked here.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function GET(request: Request): Promise<Response> {
  const incoming = new URL(request.url).searchParams
  const forwarded = new URLSearchParams()
  for (const name of ["kind", "limit"]) {
    const value = incoming.get(name)
    if (value) forwarded.set(name, value)
  }
  const query = forwarded.toString()
  return proxyResponse(
    await callEngine(`/api/v1/rules/review-queue${query ? `?${query}` : ""}`),
  )
}
