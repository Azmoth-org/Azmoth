import { CircleAlertIcon, InboxIcon, SearchXIcon } from "lucide-react"
import Link from "next/link"

import { buttonVariants } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"
import { Skeleton } from "@workspace/ui/components/skeleton"
import { cn } from "@workspace/ui/lib/utils"

/**
 * What a list page shows instead of rows: loading, nothing yet, nothing matching, or a failure.
 *
 * Four states rather than three, and the split that matters is the middle two. **"No records exist"
 * and "no records match your filter" are different facts and need different words.** Collapsing them
 * into one "Keine Daten" is how a reviewer concludes the database is empty when they have a status
 * filter set two controls above — so the empty state offers a way to *create* the first record, and
 * the no-match state offers a way to clear the filter.
 *
 * All four live in one module so that a failure on `/proposals` looks like a failure on
 * `/padnext/batch/history`. Two pages each inventing their own wording is how one screen ends up
 * saying the engine is unreachable and the other saying a request failed, for one dead process.
 */

/**
 * The table's shape while its data is in flight, as the `Suspense` fallback.
 *
 * Header cells carry their real labels — the page already knows what it is a table of — and only the
 * body is bars. A skeleton stands in for layout, never for a figure: there is no number-shaped
 * placeholder here that a reader could mistake for a rendered zero, which is the rule the `Skeleton`
 * component documents.
 */
export function TableSkeleton({
  columns,
  rows = 8,
}: {
  columns: readonly string[]
  rows?: number
}) {
  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="flex flex-wrap items-end gap-3">
          <Skeleton className="h-9 w-48" />
          <Skeleton className="h-9 w-80" />
        </div>
        <div className="space-y-3">
          <div className="flex gap-3 border-b pb-3">
            {columns.map((column) => (
              <span
                key={column}
                className="flex-1 text-sm font-medium text-muted-foreground"
              >
                {column}
              </span>
            ))}
          </div>
          {Array.from({ length: rows }, (_, index) => (
            <div key={index} className="flex gap-3">
              {columns.map((column) => (
                <Skeleton key={column} className="h-4 flex-1" />
              ))}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * The table is empty because nothing has been created yet.
 *
 * Carries the action that creates the first one. A list page a reader reaches before doing any work
 * is otherwise a dead end that tells them to go and find the right screen themselves.
 */
export function NoRecords({
  message,
  hint,
  action,
}: {
  message: string
  hint: string
  action: { href: string; label: string }
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <InboxIcon
        className="size-6 text-muted-foreground opacity-60"
        aria-hidden
      />
      <p className="text-sm font-medium">{message}</p>
      <p className="max-w-md text-xs text-muted-foreground">{hint}</p>
      <Link
        href={action.href}
        className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
      >
        {action.label}
      </Link>
    </div>
  )
}

/**
 * The table is empty because the filter matched nothing — a different sentence, and a different way
 * out. `reset` is the same URL the toolbar's reset button points at, so a reader has the escape hatch
 * where they are looking rather than where the control happens to live.
 */
export function NoMatches({
  message,
  hint,
  reset,
}: {
  message: string
  hint?: string
  reset: string
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <SearchXIcon
        className="size-6 text-muted-foreground opacity-60"
        aria-hidden
      />
      <p className="text-sm font-medium">{message}</p>
      {hint ? (
        <p className="max-w-md text-xs text-muted-foreground">{hint}</p>
      ) : null}
      <Link
        href={reset}
        className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
      >
        Filter zurücksetzen
      </Link>
    </div>
  )
}

/**
 * The page number is past the end of the result set.
 *
 * Reachable from an ordinary sequence: follow a shared `?page=7`, or narrow a filter while deep in a
 * list. It is stated rather than silently corrected to the last page, because moving somebody to a
 * page they did not ask for makes the URL they followed a lie — and because a URL is a paste as often
 * as it is a click, so "this link is stale" is real information.
 */
export function PageOutOfRange({
  firstPage,
  pages,
}: {
  firstPage: string
  pages: number
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <SearchXIcon
        className="size-6 text-muted-foreground opacity-60"
        aria-hidden
      />
      <p className="text-sm font-medium">Diese Seite ist leer</p>
      <p className="max-w-md text-xs text-muted-foreground">
        Es gibt nur {pages} {pages === 1 ? "Seite" : "Seiten"}. Vermutlich
        stammt der Link aus einer Zeit, in der die Liste länger war, oder ein
        Filter hat sie verkürzt.
      </p>
      <Link
        href={firstPage}
        className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
      >
        Zur ersten Seite
      </Link>
    </div>
  )
}

/**
 * The engine or the proxy refused, and the reason it gave.
 *
 * The engine's own German message is shown rather than a generic line: `callEngine` already produces
 * a specific sentence for every failure it has — unreachable, timed out, empty body, unparsable JSON
 * — and replacing that with "Fehler beim Laden" throws away the only thing a reader can act on.
 */
export function LoadFailed({
  headline,
  message,
}: {
  headline: string
  message: string
}) {
  return (
    <div className="space-y-2 py-10 text-center">
      <p className="flex items-center justify-center gap-2 text-sm font-medium text-destructive">
        <CircleAlertIcon className="size-4 shrink-0" aria-hidden />
        {headline}
      </p>
      <p className="mx-auto max-w-md text-xs text-muted-foreground">
        {message}
      </p>
    </div>
  )
}
