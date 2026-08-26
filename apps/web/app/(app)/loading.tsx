import { Card, CardContent, CardHeader } from "@workspace/ui/components/card"
import { Skeleton } from "@workspace/ui/components/skeleton"

/**
 * The frame of a screen while its server component resolves.
 *
 * Only ever the *shape* of a page — a heading, a banner, two panels. Deliberately no placeholder
 * where a figure will be: a grey block sitting where an amount belongs is read as a value that has
 * arrived, and on an invoice screen that is the one misreading worth designing against.
 */
export default function Loading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Inhalt wird geladen…</span>

      <div className="space-y-2">
        <Skeleton className="h-7 w-80 max-w-full" />
        <Skeleton className="h-4 w-full max-w-3xl" />
        <Skeleton className="h-4 w-2/3 max-w-2xl" />
      </div>

      <Skeleton className="h-24 w-full rounded-2xl" />

      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-48" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-4/6" />
        </CardContent>
      </Card>
    </div>
  )
}
