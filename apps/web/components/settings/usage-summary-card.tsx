"use client"

import { ActivityIcon } from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"
import { Skeleton } from "@workspace/ui/components/skeleton"

import type { UsageSummary } from "@/lib/settings/client"

/** `1,2 MB` / `847 kB`. Decimal units, which is what a billing figure is quoted in. */
function bytes(value: number): string {
  if (value < 1000) return `${value} B`
  if (value < 1_000_000) return `${(value / 1000).toFixed(0)} kB`
  return `${(value / 1_000_000).toFixed(1).replace(".", ",")} MB`
}

function period(from: string, to: string): string {
  const options: Intl.DateTimeFormatOptions = { dateStyle: "medium" }
  return `${new Date(from).toLocaleDateString("de-DE", options)} – ${new Date(
    to
  ).toLocaleDateString("de-DE", options)}`
}

/**
 * What this practice has consumed in the current billing period.
 *
 * ## Why failed requests get their own figure
 *
 * A count of successes would hide the customer most worth noticing: an integration producing four
 * hundred rejections a day is working badly and nobody has told them. It is shown next to the total
 * rather than folded into it, and it is *not* styled as an error — a handful of `422`s while a
 * vendor is building against the API is normal, and colouring it red would train them to ignore it.
 *
 * ## Why the period is always printed
 *
 * This is the number somebody checks an invoice against. A figure whose window the reader has to
 * infer is one two people compute differently from the same rows.
 */
export function UsageSummaryCard({
  usage,
  loading,
}: {
  usage: UsageSummary | null
  loading: boolean
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ActivityIcon className="size-4" />
          Verbrauch
        </CardTitle>
        <CardDescription>
          {usage
            ? `Abrechnungszeitraum ${period(usage.period_start, usage.period_end)} (UTC)`
            : "Anfragen und übertragene Datenmenge im laufenden Kalendermonat."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-16 w-full" />
        ) : !usage ? (
          <p className="text-sm text-muted-foreground">
            Der Verbrauch konnte nicht geladen werden. Die Schlüsselverwaltung
            darunter funktioniert unabhängig davon.
          </p>
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <dt className="text-xs text-muted-foreground">Anfragen</dt>
                <dd className="text-display-md tabular-nums">
                  {usage.total_requests.toLocaleString("de-DE")}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">davon fehlerhaft</dt>
                <dd className="text-display-md tabular-nums">
                  {usage.failed_requests.toLocaleString("de-DE")}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Übertragen</dt>
                <dd className="text-display-md tabular-nums">
                  {bytes(usage.total_bytes_processed)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Rechenzeit</dt>
                <dd className="text-display-md tabular-nums">
                  {(usage.total_duration_ms / 1000).toFixed(1).replace(".", ",")} s
                </dd>
              </div>
            </dl>

            {(usage.by_endpoint ?? []).length > 0 ? (
              <div className="mt-6 space-y-1">
                <p className="text-xs font-medium text-muted-foreground">
                  Nach Endpunkt
                </p>
                {(usage.by_endpoint ?? []).slice(0, 6).map((row) => (
                  <div
                    key={row.endpoint}
                    className="flex items-baseline justify-between gap-4 text-sm"
                  >
                    <span className="truncate font-mono text-xs">
                      {row.endpoint}
                    </span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      {row.requests.toLocaleString("de-DE")} ·{" "}
                      {bytes(row.bytes_processed)} ·{" "}
                      {row.average_duration_ms.toFixed(0)} ms
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}
