import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react"
import Link from "next/link"

import { buttonVariants } from "@workspace/ui/components/button"
import { cn } from "@workspace/ui/lib/utils"

import { PAGE_SIZE, nextHref, offsetOf, pageCount, type ListParams } from "@/lib/lists/params"

/**
 * Previous / Next and "Seite 2 von 5", as links.
 *
 * **Links, not buttons with handlers.** The next page is a place, and it has a URL — so it gets an
 * `<a>`, which means middle-click, ctrl-click, "copy link address" and the browser's own prefetch all
 * work, and none of it costs a line of JavaScript. A `<button onClick={router.push}>` would look
 * identical and quietly give all of that up.
 *
 * A disabled link is not a thing, so the ends of the range render as a `<span>` carrying the same
 * classes plus `aria-disabled`. That keeps the row the same width on the first and last page — a
 * control that disappears at the edges makes the whole strip jump.
 *
 * The row also states the range it is showing ("1–50 von 214"), because `total` is the number the
 * engine's listing endpoint was given a `total` field for: without it a reader cannot tell fifty rows
 * from the first fifty of nine hundred, and a page number alone does not say it either.
 *
 * A server component. The hrefs are computable from the params the page already has.
 */
export function Pagination({
  pathname,
  params,
  total,
  shown,
}: {
  pathname: string
  params: ListParams
  /** Every row matching the filters, from the engine. Not the page length. */
  total: number
  /** How many rows this page actually rendered, for the range label. */
  shown: number
}) {
  const pages = pageCount(total)
  const hasPrevious = params.page > 1
  const hasNext = params.page < pages

  const from = total === 0 ? 0 : offsetOf(params.page) + 1
  const to = total === 0 ? 0 : offsetOf(params.page) + shown

  return (
    <nav
      aria-label="Seitennavigation"
      className="flex flex-wrap items-center justify-between gap-3 pt-2"
    >
      <p className="text-muted-foreground text-xs">
        {total === 0 ? (
          "Keine Einträge"
        ) : (
          <>
            <span className="tabular-nums">
              {from}–{to}
            </span>{" "}
            von <span className="tabular-nums">{total}</span> · {PAGE_SIZE} pro Seite
          </>
        )}
      </p>

      <div className="flex items-center gap-2">
        <Step
          href={nextHref(pathname, params, { page: params.page - 1 })}
          enabled={hasPrevious}
          label="Zurück"
          icon="left"
        />
        {/*
          `aria-live` so a screen reader hears the new position after a page change. The links
          themselves announce their own labels; this is the only element that says *where you now
          are*, and without it a paginated table is silent about having moved.
        */}
        <span className="text-xs tabular-nums" aria-live="polite">
          Seite {params.page} von {pages}
        </span>
        <Step
          href={nextHref(pathname, params, { page: params.page + 1 })}
          enabled={hasNext}
          label="Weiter"
          icon="right"
        />
      </div>
    </nav>
  )
}

function Step({
  href,
  enabled,
  label,
  icon,
}: {
  href: string
  enabled: boolean
  label: string
  icon: "left" | "right"
}) {
  const className = cn(buttonVariants({ variant: "outline", size: "sm" }))
  const Icon = icon === "left" ? ChevronLeftIcon : ChevronRightIcon
  const content =
    icon === "left" ? (
      <>
        <Icon aria-hidden />
        {label}
      </>
    ) : (
      <>
        {label}
        <Icon aria-hidden />
      </>
    )

  if (!enabled) {
    return (
      <span aria-disabled="true" className={cn(className, "pointer-events-none opacity-50")}>
        {content}
      </span>
    )
  }
  return (
    <Link href={href} className={className}>
      {content}
    </Link>
  )
}
