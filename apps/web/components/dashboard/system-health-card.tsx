import { SystemStatus } from "@/components/home/system-status"
import { callEngine } from "@/lib/engine"
import type { HealthResponse, RuleCoverage } from "@/lib/dashboard/types"

/**
 * The System Health card's data, fetched on the server.
 *
 * A thin async wrapper around `SystemStatus`, which already renders everything this card has to
 * say — engine status, catalog version, Soufflé and Clingo, and "X von 894 Regeln verifiziert" with
 * its bar. It is not reimplemented here. The two figures it shows decide how much every other
 * screen's output is worth, and a second component computing "verified share" from the same two
 * counts is exactly how a dashboard and a workbench come to disagree about the same number.
 *
 * What is new is the boundary. Fetching moved out of the page and into the card, so the two reads
 * this card needs are awaited inside its own `Suspense` subtree: the header, the banner and the two
 * activity cards render without waiting for the engine's health endpoint, and a slow health check
 * delays one card instead of the screen.
 *
 * Both calls in parallel — they are independent, and the slower one should not be waited for twice.
 * `callEngine` resolves to a described failure rather than throwing, so an engine that is down
 * renders as `SystemStatus`'s degraded alert and not as this page's error boundary.
 */
export async function SystemHealthCard() {
  const [coverageResult, healthResult] = await Promise.all([
    callEngine("/api/v1/rules/coverage"),
    callEngine("/api/v1/health"),
  ])

  const coverage = coverageResult.ok ? (coverageResult.body as RuleCoverage) : null
  const health = healthResult.ok ? (healthResult.body as HealthResponse) : null

  return <SystemStatus coverage={coverage} health={health} />
}
