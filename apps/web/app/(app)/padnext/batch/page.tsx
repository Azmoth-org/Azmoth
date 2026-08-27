import type { Metadata } from "next"
import Link from "next/link"

import { BatchWorkbench } from "@/components/padnext/batch-workbench"
import { SyntheticDataBanner } from "@/components/review/synthetic-data-banner"
import { readDeepLinkId, type RawSearchParams } from "@/lib/deep-link"

export const metadata: Metadata = {
  title: "PADnext-Stapelprüfung",
  description:
    "Mehrere PADnext-Lieferungen auf einmal prüfen und das systemische Risiko über alle Rechnungen bewerten. Nur synthetische Daten.",
}

/**
 * `/padnext/batch` — audit many deliveries at once.
 *
 * A server component shell, like `/padnext` and `/review`: the banner and the explanation of what
 * the three buckets mean at batch scale must render even if the client bundle fails, and only the
 * upload and the polling below are interactive.
 *
 * ## `?id=batch_…`
 *
 * The dashboard's "Letzte Stapelprüfungen" card and every row of the Stapel-Historie link here with
 * an id. It is read here and handed down; the workbench polls it through the `/api/engine` proxy,
 * exactly as it polls a batch this tab uploaded. That is the whole reason the batch listing endpoint
 * exists — a `batch_id` is issued once, in the `202`, so before this a finished roll-up sitting in
 * Postgres had no route back to a screen.
 *
 * **A visit without the parameter is untouched:** `deepLinkId` is `null` and the upload interface
 * renders exactly as before.
 */
export default async function PadnextBatchPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>
}) {
  const deepLinkId = readDeepLinkId(await searchParams)

  return (
    <>
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          PADnext-Stapel prüfen
        </h1>
        <p className="text-sm text-muted-foreground">
          Mehrere bereits kodierte PADnext-Lieferungen auf einmal. Jede Datei
          durchläuft dieselbe Prüfung wie in der{" "}
          <Link href="/padnext" className="underline">
            Einzelprüfung
          </Link>{" "}
          — dieselben Datalog-Regeln, derselbe versionierte Katalog — und die
          Ergebnisse werden anschließend über alle Rechnungen zusammengefasst.
        </p>
        <p className="text-sm text-muted-foreground">
          Die Zusammenfassung behält die drei Gruppen der Einzelprüfung bei,
          statt sie zu einer Summe „strittig“ zu verrechnen. Das ist im Stapel
          wichtiger als in der Einzelprüfung: über ein Jahr Rechnungen summiert
          wäre <strong>unbestätigt</strong> ein sechsstelliger Vorwurf gegen
          eine Praxis, die möglicherweise korrekt abrechnet — dabei ist es die
          Grenze unserer eigenen Regelabdeckung.
        </p>
      </header>

      <SyntheticDataBanner />
      <BatchWorkbench deepLinkId={deepLinkId} />
    </>
  )
}
