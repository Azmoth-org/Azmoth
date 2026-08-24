import { ChevronRightIcon } from "lucide-react"
import Link from "next/link"

import { Badge } from "@workspace/ui/components/badge"
import { cn } from "@workspace/ui/lib/utils"

import { shortId, type StatusPresentation } from "@/lib/dashboard/format"
import type { ActivityRow as Row } from "@/lib/dashboard/types"
import { timestamp } from "@/lib/review/format"

/**
 * One line in the two activity cards: an identifier, a status, a line of context, a time.
 *
 * **A list of links, not a table with a row handler.** A `<tr>` cannot legally contain the anchor
 * that would make the whole row clickable, and the alternative — an `onClick` plus a `router.push`
 * — turns a card that renders on the server into a client component and gives up middle-click,
 * ctrl-click and "copy link address" for nothing. A list of `<Link>`s is keyboard reachable and
 * focusable without a line of JavaScript.
 *
 * **The link carries the record's id, and today the target screen ignores it.** `/review` starts
 * from a synthetic case and solves; `/padnext/batch` starts from an upload. Neither reads a search
 * parameter, so clicking a row lands on the right workbench with an empty one. That gap is real and
 * it is not closed here: opening a stored record needs the workbenches to read `?id=`, and those
 * screens are out of scope for this change. The parameter is on the link already so that the day
 * deep-linking lands, no dashboard code has to move.
 */
export function ActivityRow({
  row,
  status,
}: {
  row: Row
  status: StatusPresentation
}) {
  return (
    <li>
      <Link
        href={row.href}
        // `title` carries the untruncated identifier, so the value the row shows short is still
        // readable in full without leaving the page.
        title={row.id}
        className="hover:bg-muted/50 focus-visible:ring-ring group -mx-2 flex items-center gap-3 rounded-md px-2 py-2.5 transition-colors focus-visible:ring-2 focus-visible:outline-none"
      >
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-mono text-xs">{shortId(row.id)}</span>
            <Badge variant={status.variant} className={cn(status.className)}>
              {status.label}
            </Badge>
          </div>
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
            <span className="truncate">{row.detail}</span>
            <span aria-hidden>·</span>
            <span className="tabular-nums">{timestamp(row.createdAt)}</span>
          </div>
        </div>
        <ChevronRightIcon
          className="text-muted-foreground/60 group-hover:text-foreground size-4 shrink-0 transition-colors"
          aria-hidden
        />
      </Link>
    </li>
  )
}
