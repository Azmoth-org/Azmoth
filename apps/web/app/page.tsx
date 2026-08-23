import { ArrowRightIcon } from "lucide-react"
import type { Metadata } from "next"
import Link from "next/link"

import { Badge } from "@workspace/ui/components/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"
import type { HealthResponse, RuleCoverage } from "@workspace/contracts"

import { SystemStatus } from "@/components/home/system-status"
import { NAV_ITEMS } from "@/components/layout/nav"
import { SyntheticDataBanner } from "@/components/review/synthetic-data-banner"
import { callEngine } from "@/lib/engine"

export const metadata: Metadata = {
  title: "Übersicht",
  description:
    "Einstieg in die GOÄ-Prüfung: Abrechnungsvorschläge prüfen, PADnext-Rechnungen einzeln oder " +
    "im Stapel auditieren, und die maschinell extrahierten Regeln freigeben.",
}

/**
 * Rendered per request, never prerendered.
 *
 * Two reasons, and the second is the load-bearing one. The figures below are live — a rule verified
 * a minute ago has to show here — and, more importantly, `next build` runs inside `docker build`
 * where no engine exists. A statically generated dashboard would either fail the image build or
 * bake in "Engine nicht erreichbar" and serve it forever.
 */
export const dynamic = "force-dynamic"

/**
 * `/` — the entry point.
 *
 * It replaces the project scaffold ("Project ready! You may now add components and start
 * building."), which was the first screen anyone opening this application saw. The four workbenches
 * were reachable only by typing their URLs.
 *
 * A server component, so the engine is called from the server and `ENGINE_BASE_URL` stays out of the
 * browser — the same rule every other engine call in this app follows.
 */
export default async function HomePage() {
  // Both in parallel: two independent reads, and the slower one should not be waited for twice.
  // `callEngine` never throws — it resolves to a described failure — so a dead engine renders as a
  // degraded status card rather than as this page's error boundary.
  const [coverageResult, healthResult] = await Promise.all([
    callEngine("/api/v1/rules/coverage"),
    callEngine("/api/v1/health"),
  ])

  const coverage = coverageResult.ok ? (coverageResult.body as RuleCoverage) : null
  const health = healthResult.ok ? (healthResult.body as HealthResponse) : null

  return (
    <>
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">GOÄ-Prüfung und Rechnungsaudit</h1>
        <p className="text-muted-foreground max-w-3xl text-sm">
          Die Kodierung ist deterministisch und symbolisch: ein Datalog-Programm entscheidet, was
          sicher berechnungsfähig ist, ein ASP-Programm löst die verbleibenden Wahlmöglichkeiten,
          eine unabhängige Validierung rechnet nach. Jede Position trägt einen Beweisbaum, jedes
          Ergebnis einen Receipt-Hash über Katalog, Regeltabellen, Logikprogramme, Solver-Versionen
          und Eingabe. Es läuft kein Modell in diesem System.
        </p>
      </header>

      <SyntheticDataBanner />

      <SystemStatus coverage={coverage} health={health} />

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Arbeitsbereiche</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            return (
              <Card key={item.href} className="hover:border-foreground/20 transition-colors">
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    <Icon className="size-4 shrink-0" aria-hidden />
                    {item.label}
                    {item.internal ? <Badge variant="secondary">Intern</Badge> : null}
                  </CardTitle>
                  {/* The screen's own metadata description, so the card and the tab agree. */}
                  <CardDescription>{item.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <Link
                    href={item.href}
                    className="text-sm font-medium underline underline-offset-4"
                  >
                    <span className="inline-flex items-center gap-1.5">
                      Öffnen
                      <ArrowRightIcon className="size-3.5" aria-hidden />
                    </span>
                  </Link>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </section>
    </>
  )
}
