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
