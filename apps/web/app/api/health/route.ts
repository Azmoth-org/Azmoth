/**
 * Liveness for the web container. Deliberately says nothing about the engine.
 *
 * The container healthcheck has one question — "is this Next.js server able to serve a request?" —
 * and it must not be answered by proxying to the engine. A web process that is perfectly healthy
 * while the engine is restarting would otherwise be reported unhealthy and restarted by the
 * orchestrator, which fixes nothing and loses whatever was in flight.
 *
 * Engine reachability is a *page-level* concern instead: every screen renders the engine's absence
 * as an error panel (see `lib/engine.ts`), and the dashboard on `/` shows it as a degraded status
 * card. That is where a human needs to see it. This route is for the supervisor.
 */

export const dynamic = "force-dynamic"

export function GET() {
  return Response.json(
    { status: "ok", service: "web" },
    { headers: { "Cache-Control": "no-store" } },
  )
}
