/**
 * `GET /api/engine/billing/plans` → `GET {ENGINE_BASE_URL}/api/v1/billing/plans`
 *
 * The plans this practice could move to, cheapest first. Superseded revisions are not listed: a
 * price is never edited, only replaced, so a practice on an older revision keeps its terms while
 * only the current one can be newly chosen. Their own plan is in `/billing/usage` and may well be a
 * code that no longer appears here.
 *
 * Behind the session even though a price list is not tenant data — before launch it is commercially
 * sensitive, and the marketing site is where a public one belongs.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function GET(): Promise<Response> {
  return proxyResponse(await callEngine("/api/v1/billing/plans"))
}
