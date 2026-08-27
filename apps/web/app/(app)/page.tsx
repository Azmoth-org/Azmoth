import { ArrowRightIcon } from "lucide-react"
import type { Metadata } from "next"
import Link from "next/link"
import { Suspense } from "react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

import { CardSkeleton } from "@/components/dashboard/card-states"
import {
  RECENT_BATCHES_TITLE,
  RecentBatchesCard,
} from "@/components/dashboard/recent-batches-card"
import {
  RECENT_PROPOSALS_TITLE,
  RecentProposalsCard,
} from "@/components/dashboard/recent-proposals-card"
import { SystemHealthCard } from "@/components/dashboard/system-health-card"
import { WORKSPACE_ITEMS } from "@/components/layout/nav"
import { SyntheticDataBanner } from "@/components/review/synthetic-data-banner"

export const metadata: Metadata = {
  title: "Übersicht",
  description:
    "Systemstatus, die letzten Abrechnungsvorschläge und die letzten Stapelprüfungen auf einen Blick.",
}

/**
 * Rendered per request, never prerendered.
 *
 * Two reasons, and the second is the load-bearing one. Everything below is live — a rule verified a
 * minute ago, a batch that finished while the tab was open — and, more importantly, `next build` runs
 * inside `docker build` where no engine exists. A statically generated dashboard would either fail
 * the image build or bake in "Engine nicht erreichbar" and serve it forever.
 */
export const dynamic = "force-dynamic"

/**
 * `/` — the dashboard.
 *
 * It answers three questions in the order somebody opening this application asks them: *is the
 * engine sound and how much of the rule set is actually enforced*, *what has been proposed lately*,
 * and *what has been audited lately*. The two activity cards are new; before them the only route
 * back to a stored record was a `proposal_id` or `batch_id` a reader still happened to have in a
 * scrollback, which meant that in practice a finished batch became unreachable on reload even though
 * its roll-up was sitting in Postgres.
 *
 * **Each card fetches its own data, inside its own `Suspense` boundary.** That is the whole reason
 * the fetching is not in this function. The shell, the header and the disclaimer stream immediately;
 * each card resolves when its engine call does, and a slow or dead endpoint degrades exactly one
 * card. The previous version awaited two calls here before rendering anything, so a hanging health
 * check was a blank page.
 *
 * Failure never reaches an error boundary, because `callEngine` resolves to a described failure
 * rather than throwing, and each card renders that description itself. A dashboard whose engine is
 * down is three cards saying so — not a stack trace.
 *
 * A server component, so the engine is called from the server and `ENGINE_BASE_URL` stays out of the
 * browser — the same rule every other engine call in this app follows.
 */
export default function DashboardPage() {
  return (
    <>
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Übersicht</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Die Kodierung ist deterministisch und symbolisch: ein Datalog-Programm
          entscheidet, was sicher berechnungsfähig ist, ein ASP-Programm löst
          die verbleibenden Wahlmöglichkeiten, eine unabhängige Validierung
          rechnet nach. Jede Position trägt einen Beweisbaum, jedes Ergebnis
          einen Receipt-Hash über Katalog, Regeltabellen, Logikprogramme,
          Solver-Versionen und Eingabe. Es läuft kein Modell in diesem System.
        </p>
      </header>

      <SyntheticDataBanner />

      <Suspense fallback={<CardSkeleton title="Systemstatus" rows={2} />}>
        <SystemHealthCard />
      </Suspense>

      {/*
        The two activity cards side by side above `lg`, stacked below. They are siblings in one grid
        rather than nested, so a card whose engine call is slow does not shift the other one: the
        skeleton it is replaced by occupies the same cell.
      */}
      <section className="grid gap-4 lg:grid-cols-2">
        <Suspense fallback={<CardSkeleton title={RECENT_PROPOSALS_TITLE} />}>
          <RecentProposalsCard />
        </Suspense>
        <Suspense fallback={<CardSkeleton title={RECENT_BATCHES_TITLE} />}>
          <RecentBatchesCard />
        </Suspense>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">
          Arbeitsbereiche
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {/*
            `WORKSPACE_ITEMS`, not `NAV_ITEMS`: the dashboard is now a nav entry, and a card here
            linking to the page it is on would be a link to nowhere.
          */}
          {WORKSPACE_ITEMS.map((item) => {
            const Icon = item.icon
            return (
              <Card
                key={item.href}
                className="transition-colors hover:border-foreground/20"
              >
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    <Icon className="size-4 shrink-0" aria-hidden />
                    {item.label}
                    {item.internal ? (
                      <Badge variant="secondary">Intern</Badge>
                    ) : null}
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
