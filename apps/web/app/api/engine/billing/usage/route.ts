/**
 * `GET /api/engine/billing/usage` → `GET {ENGINE_BASE_URL}/api/v1/billing/usage`
 *
 * The open billing period: which plan, how many invoices audited, how much quota is left, what
 * overage has accrued. What the usage meter on `/settings/api-keys` renders.
 *
 * `callEngine` resolves the session and forwards the organisation, so the figures are the signed-in
 * practice's and there is no parameter with which a caller could name another one.
 *
 * **Not the same window as `/api/engine/settings/usage`.** That one reports the current *calendar*
 * month; this one reports the practice's own billing period, which is anchored on the day they were
 * created. Both state the window they used, and the UI prints it — two numbers that differ because
 * they cover different windows are only confusing when neither says so.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function GET(): Promise<Response> {
  return proxyResponse(await callEngine("/api/v1/billing/usage"))
}
