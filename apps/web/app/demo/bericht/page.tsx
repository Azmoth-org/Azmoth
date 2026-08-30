import type { Metadata } from "next"
import Link from "next/link"
import { ArrowLeftIcon, ArrowRightIcon } from "lucide-react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { buttonVariants } from "@workspace/ui/components/button"
import { cn } from "@workspace/ui/lib/utils"

import { DemoModeBanner } from "@/components/demo/demo-mode-banner"
import { DemoPdfButton } from "@/components/demo/demo-pdf-button"
import { BucketSummary } from "@/components/padnext/bucket-summary"
import { FindingsPanel } from "@/components/padnext/findings-panel"
import { PositionsTable } from "@/components/padnext/positions-table"
import { ReportProvenance } from "@/components/padnext/report-provenance"
import { callPublicEngine } from "@/lib/engine"
import { isAuditReportShape } from "@/lib/padnext/types"

export const metadata: Metadata = {
  title: "Demo-Prüfbericht",
  description:
    "Das Prüfergebnis der synthetischen Beispiellieferung: drei Gruppen nach Belegbarkeit, " +
    "jede Position mit Begründung.",
  robots: { index: false, follow: false },
}

/**
 * `/demo/bericht` — the demo audit, rendered read-only.
 *
 * ## Read-only in the sense that matters: there is nothing here to decide
 *
 * The signed-in review screens carry a decision bar — freigeben, ablehnen, exportieren — because a
 * proposal there is a draft somebody becomes responsible for. This screen has none of that, and not
 * because the buttons are hidden. There is no proposal: the demo audit is computed and returned,
 * never written, so there is no row to approve and no state a visitor could change. Rendering an
 * approval control would be an invitation to act on a fixture, and hiding one that existed would be
 * a control an anonymous visitor could find by other means.
 *
 * The PDF stays, because a printed report is the one artefact a prospect actually takes to a
 * colleague, and it says inside itself that it describes synthetic data.
 *
 * ## Why the report is fetched here rather than passed from the button
 *
 * A server component asking the engine directly. That means the report survives a page reload, a
 * shared link and a browser back-button — all of which would produce an empty screen if the data
 * lived in the client state of the button that navigated here. It costs one extra call, which the
 * engine answers from its memo.
 *
 * `callPublicEngine` attaches no identity, which is what keeps this out of `api_usage_logs`
 * entirely: the engine meters a request only when the context carries a tenant.
 */
export const dynamic = "force-dynamic"

export default async function DemoReportPage() {
  const result = await callPublicEngine("/api/v1/demo/audit")

  if (!result.ok || !isAuditReportShape(result.body)) {
    return (
      <>
        <DemoModeBanner />
        <Alert variant="destructive">
          <AlertTitle>Der Demo-Bericht konnte nicht geladen werden</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>
              {result.ok
                ? "Die Engine hat geantwortet, aber der Bericht hatte nicht die erwartete Form."
                : result.failure.message}
            </p>
            <Link
              href="/demo"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
            >
              <ArrowLeftIcon aria-hidden />
              Zurück zur Demo
            </Link>
          </AlertDescription>
        </Alert>
      </>
    )
  }

  const report = result.body

  return (
    <>
      <DemoModeBanner />

      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Prüfbericht — Beispiellieferung
        </h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Dieselbe Engine, die im Pilotbetrieb echte Exporte prüft, angewandt auf
          eine synthetische Lieferung mit neun bewusst eingebauten Fehlern. Jede
          Position unten trägt ihre Begründung, jede Beanstandung die Regel und
          die Rechtsgrundlage, auf der sie beruht.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 print:hidden">
        <DemoPdfButton />
        <Link
          href="/demo"
          className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}
        >
          <ArrowLeftIcon aria-hidden />
          Zurück zur Übersicht
        </Link>
      </div>

      <BucketSummary report={report} />
      <ReportProvenance report={report} />
      <PositionsTable report={report} />
      <FindingsPanel report={report} />

      <section className="rounded-xl border border-dashed p-5 print:hidden">
        <h2 className="text-sm font-semibold">
          Und mit Ihren eigenen Abrechnungsdaten?
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Der Pilotbetrieb läuft auf pseudonymisierten Exporten: Sie führen unser
          Anonymisierungsskript auf Ihrem eigenen Rechner aus, und erst die
          bereinigte Datei wird geprüft. Dateien mit dem Merkmal{" "}
          <code className="font-mono text-xs">echtdaten=&quot;true&quot;</code>{" "}
          weist das System ab — auch dann, wenn sie versehentlich hochgeladen
          werden. Der Zugang ist derzeit auf freigeschaltete Pilot-Teilnehmer
          beschränkt.
        </p>
        <Link href="/signup" className={cn(buttonVariants(), "mt-4")}>
          Mit eigenen Daten prüfen (Pilot-Zugang anfordern)
          <ArrowRightIcon aria-hidden />
        </Link>
      </section>
    </>
  )
}
