import {
  ArrowRightIcon,
  CalendarIcon,
  TerminalIcon,
  UploadIcon,
} from "lucide-react"
import Link from "next/link"
import type { ComponentType } from "react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

import { PilotOnlyBanner } from "@/components/dashboard/pilot-only-banner"
import { hasAnyDeliveries } from "@/lib/dashboard/counts"
import { getCalComUrl } from "@/lib/site"

type FirstRunCard = {
  href: string
  external?: boolean
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>
  title: string
  description: string
  action: string
}

/**
 * The three doors out of an empty dashboard, in the order a reader without a delivery of their own
 * should meet them: generate one, upload one, or talk to someone first.
 */
function cards(): FirstRunCard[] {
  return [
    {
      href: "/docs/generator",
      icon: TerminalIcon,
      title: "Synthetische Testlieferung erzeugen",
      description:
        "Ein Kommandozeilenskript ohne Abhängigkeiten schreibt eine PADnext-Testlieferung mit erfundenen GOÄ-Positionen — für den ersten Versuch ohne eigene Daten.",
      action: "Anleitung öffnen",
    },
    {
      href: "/padnext",
      icon: UploadIcon,
      title: "Lieferung hochladen",
      description:
        "Eine PADnext-Lieferung gegen die GOÄ-Regeln prüfen lassen — die eigene, synthetische Testlieferung oder die eben erzeugte.",
      action: "Lieferung prüfen",
    },
    {
      href: getCalComUrl(),
      external: true,
      icon: CalendarIcon,
      title: "30-Minuten-Walkthrough buchen",
      description:
        "Eine gemeinsame Sitzung, um den Pilot einmal live durchzugehen — bevor oder statt des ersten eigenen Versuchs.",
      action: "Termin buchen",
    },
  ]
}

/**
 * The first-run empty state — three cards, shown instead of nothing on an organisation that has
 * never had a proposal or a batch.
 *
 * ## Its own read, deliberately duplicating two calls the cards below already make
 *
 * `RecentProposalsCard` and `RecentBatchesCard` each already ask the engine whether anything
 * exists, but only to render their own per-card empty state — this section decides something
 * different: whether to greet the whole screen as a first run at all. Sharing that answer would
 * mean this section reading state out of a sibling `Suspense` boundary, which the architecture the
 * rest of `(app)/page.tsx` is built on (every card fetches its own data, independently) does not
 * support. Two extra `limit=1` reads is the cost of keeping every card independently resumable.
 *
 * `hasAnyDeliveries()` returning `null` — the engine could not be asked — renders nothing here
 * rather than guessing. An organisation with a genuine backlog must never be told it is empty
 * because a read failed, and the ordinary cards below already say "Engine nicht erreichbar" for
 * that same failure, so the reader is not left with no explanation at all.
 */
export async function FirstRunSection() {
  const hasDeliveries = await hasAnyDeliveries()
  if (hasDeliveries !== false) return null

  return (
    <section className="space-y-4">
      <PilotOnlyBanner />
      <div className="grid gap-4 sm:grid-cols-3">
        {cards().map((card) => {
          const Icon = card.icon
          return (
            <Card key={card.href} className="flex flex-col">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Icon className="size-4 shrink-0" aria-hidden />
                  {card.title}
                </CardTitle>
                <CardDescription>{card.description}</CardDescription>
              </CardHeader>
              <CardContent className="mt-auto">
                <Link
                  href={card.href}
                  target={card.external ? "_blank" : undefined}
                  rel={card.external ? "noopener noreferrer" : undefined}
                  className="inline-flex items-center gap-1.5 text-sm font-medium underline underline-offset-4"
                >
                  {card.action}
                  <ArrowRightIcon className="size-3.5" aria-hidden />
                </Link>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </section>
  )
}
