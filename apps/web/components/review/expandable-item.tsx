"use client"

import { ChevronDownIcon } from "lucide-react"
import type * as React from "react"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@workspace/ui/components/collapsible"
import { cn } from "@workspace/ui/lib/utils"

/**
 * A compact row that opens into its own explanation.
 *
 * The two prose panels on the review screen — Dokumentationslücken and Hinweise der Engine — were
 * the same mistake twice: every entry rendered its whole explanation inline, so a proposal with six
 * gaps and eleven warnings put seventeen paragraphs of German legal text on the screen at once, and
 * a reader looking for *which* positions were affected had to read all of them to find out. Both are
 * lists of things a physician needs to be able to count and locate first, and read second.
 *
 * So the collapsed row carries only what distinguishes one entry from the next — an icon that
 * classifies it, a title that names it, and the Ziffer or the factors it concerns — and the
 * explanation is one click below it.
 *
 * **`keepMounted` and `data-print="expand"`**, for the same reason `CollapsibleSection` has them: an
 * unmounted subtree cannot be printed, and whether a reader had clicked a row is a property of a
 * browsing session rather than of the document. On paper every entry is open. The rules that do this
 * live in `@workspace/ui`'s print stylesheet — see the note on `collapsible-section.tsx` for why
 * they cannot be a `print:` utility.
 */
export function ExpandableItem({
  icon,
  title,
  meta,
  className,
  children,
}: {
  /** The classifying glyph. Already coloured by the caller — that colour is the classification. */
  icon: React.ReactNode
  /** One scannable line. Bold, and short enough not to wrap on a phone. */
  title: React.ReactNode
  /** Badges and small print that belong on the collapsed row: a Ziffer, a paragraph reference. */
  meta?: React.ReactNode
  className?: string
  children: React.ReactNode
}) {
  return (
    <li className={cn("overflow-hidden rounded-2xl border", className)}>
      <Collapsible>
        {/*
          `group` so the chevron can read the trigger's own state: Base UI puts `data-panel-open` on
          the trigger while the panel is open, and the shadcn wrapper adds no group class of its own.
        */}
        <CollapsibleTrigger
          className={cn(
            "group hover:bg-muted/50 focus-visible:ring-ring flex w-full cursor-pointer",
            "items-start gap-3 p-3 text-left focus-visible:ring-2 focus-visible:outline-none",
          )}
        >
          <span className="mt-0.5 shrink-0 [&_svg]:size-4">{icon}</span>
          <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-semibold">{title}</span>
            {meta}
          </span>
          <ChevronDownIcon
            aria-hidden
            className="text-muted-foreground mt-0.5 size-4 shrink-0 transition-transform group-data-[panel-open]:rotate-180 print:hidden"
          />
        </CollapsibleTrigger>

        <CollapsibleContent keepMounted data-print="expand">
          <div className="text-muted-foreground space-y-2 px-3 pt-1 pb-3 pl-10 text-sm">
            {children}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}
