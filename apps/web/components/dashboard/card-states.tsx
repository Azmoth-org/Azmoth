import { CircleAlertIcon, InboxIcon } from "lucide-react"

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"
import { Skeleton } from "@workspace/ui/components/skeleton"

/**
 * The three things a dashboard card can be other than itself: loading, empty, or unable to load.
 *
 * Kept in one module because the failure of one card must look like the failure of any other. Three
 * cards each inventing their own "could not load" wording is how a screen ends up telling a reader
 * that the engine is unreachable in one place and that a request failed in another, for one dead
 * process.
 */

/**
 * The card's shape while its data is in flight.
 *
 * A skeleton stands in for *layout*, never for a figure — the same rule the `Skeleton` component
 * documents. There is no number-shaped placeholder here that a reader could mistake for a rendered
 * zero: the rows are bars, and the title is the real title, because the card already knows what it
 * is going to be a card of.
 *
 * Rendered as the `Suspense` fallback for each card, which is what makes the three independent. The
 * page shell, the header and the two cards that are already resolved are streamed immediately;
 * whichever engine call is slowest holds up only its own card.
 */
export function CardSkeleton({
  title,
  rows = 3,
}: {
  title: string
  rows?: number
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <Skeleton className="h-3.5 w-40" />
      </CardHeader>
      <CardContent className="space-y-3">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="space-y-1.5">
            <Skeleton className="h-3.5 w-2/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

/**
 * Nothing has happened yet — which is a normal state on a fresh database, not a fault.
 *
 * Worded as an absence of records rather than as an absence of data, and it says what to do next.
 * "Keine Daten" would leave a reader on a new checkout unable to tell an empty table from a broken
 * read, which is precisely the distinction this screen exists to make.
 */
export function EmptyState({
  message,
  hint,
}: {
  message: string
  hint?: string
}) {
  return (
    <div className="flex flex-col items-center gap-2 py-8 text-center text-muted-foreground">
      <InboxIcon className="size-5 opacity-60" aria-hidden />
      <p className="text-sm">{message}</p>
      {hint ? <p className="max-w-xs text-xs">{hint}</p> : null}
    </div>
  )
}

/**
 * The card could not be loaded, and the reason the engine or the proxy gave.
 *
 * The engine's own message is shown rather than a generic line, because `callEngine` already
 * produces a specific German sentence for every failure mode it has — unreachable, timed out, empty
 * body, unparsable JSON — and replacing that with "Fehler beim Laden" would throw away the only
 * information a reader can act on. The headline names which card failed, so a reader with one broken
 * card out of three knows which figure not to trust.
 */
export function ErrorState({
  headline,
  message,
}: {
  headline: string
  message: string
}) {
  return (
    <div className="space-y-2 py-6 text-sm text-muted-foreground">
      <p className="flex items-center gap-2 font-medium text-destructive">
        <CircleAlertIcon className="size-4 shrink-0" aria-hidden />
        {headline}
      </p>
      <p className="text-xs">{message}</p>
    </div>
  )
}

/**
 * The metric row's shape while its five counts are in flight.
 *
 * Four tiles, and **no number-shaped placeholder** — the same rule the card skeleton above follows,
 * and it matters more here. `CardSkeleton` stands in for rows of text nobody could mistake for a
 * value; a grey block where a 32px numeral is about to appear is one a reader's eye resolves as a
 * figure that has not finished painting. So the bar that stands in for the figure is deliberately
 * the wrong shape for one: short and wide, at the height of the numeral's cap rather than its box.
 *
 * The labels are real, because the row already knows what it is going to be a row of, and a reader
 * who sees "Offene Prüfungen" with a pending value learns something the four grey rectangles alone
 * would not tell them.
 *
 * The grid is repeated rather than shared with `MetricsRow`. Two literals is the smaller cost: a
 * shared wrapper would have to be a component that takes children and a label, and the failure mode
 * of getting it wrong here is a layout shift when the real row lands — which is exactly what a
 * skeleton exists to prevent, so it is worth the duplication being visible.
 */
export function MetricsRowSkeleton({ labels }: { labels: readonly string[] }) {
  return (
    <div aria-hidden className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {labels.map((label) => (
        <Card key={label} size="sm" className="h-full gap-3">
          <div className="flex items-start justify-between gap-3 px-(--card-spacing)">
            <span className="text-sm font-medium text-muted-foreground">
              {label}
            </span>
            <Skeleton className="size-8 shrink-0 rounded-full" />
          </div>
          <div className="px-(--card-spacing)">
            <Skeleton className="h-8 w-16" />
            <Skeleton className="mt-2.5 h-3 w-28" />
          </div>
        </Card>
      ))}
    </div>
  )
}

/** The four labels, so the skeleton and the row cannot drift about what the tiles are called. */
export const METRIC_LABELS = [
  "Offene Prüfungen",
  "Freigegeben",
  "Stapel in Arbeit",
  "Fehlgeschlagen",
] as const
