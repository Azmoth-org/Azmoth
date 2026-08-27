"use client"

import { ChevronDownIcon } from "lucide-react"
import * as React from "react"

import { Badge } from "@workspace/ui/components/badge"
import { Card } from "@workspace/ui/components/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@workspace/ui/components/collapsible"
import { cn } from "@workspace/ui/lib/utils"

/**
 * Disclosure, twice: once as a whole card, once as a line inside one.
 *
 * The review screen has two kinds of detail a reviewer needs *available* rather than *present*. The
 * audit trail is one — a hundred proof steps that answer "why is this on the bill?" and that nobody
 * reads until they are disputing something. The provenance block in the header is the other: eight
 * version strings that make the result reproducible and that a reader glancing at an amount does not
 * need in their way.
 *
 * Both are the shared `Collapsible`, which is where the open state, the `aria-expanded` /
 * `aria-controls` wiring and the height transition come from. Two things are added on top, and both
 * are about paper.
 *
 * **`keepMounted`.** By default the panel unmounts when closed, and an unmounted subtree cannot be
 * printed. With it the content stays in the DOM behind the `hidden` attribute, where the print
 * stylesheet can reach it. A printed proposal that quietly omitted the versions it was produced
 * under would be exactly the document this system exists not to make: the receipt hash means nothing
 * without the catalog and rule versions it hashes over.
 *
 * **`data-print` rather than a `print:block!` class.** It was the class first, and it silently did
 * nothing. Tailwind's preflight carries `[hidden] { display: none !important }` in `@layer base`, and
 * for *important* declarations the cascade reverses layer order — the earlier layer wins — so an
 * important utility in `@layer utilities` cannot beat it at any specificity. The rule lives in the
 * print stylesheet in `@workspace/ui` instead; this marks which panels it applies to.
 *
 * **`printOpen={false}`** is the exception, for the one kind of detail that is genuinely not part of
 * the document: measured stage timings and raw JSON, excluded from the receipt hash precisely
 * because they are not evidence. Several pages of them behind a physician's signature would be noise
 * asserting itself as record.
 *
 * `hiddenUntilFound` would also keep the content mounted, and would additionally let the browser's
 * find-in-page open it — but it hides through `content-visibility`, which a print stylesheet cannot
 * override either, so it is the wrong half of the trade here.
 */
function printMode(printOpen: boolean): "expand" | "omit" {
  return printOpen ? "expand" : "omit"
}

export function CollapsibleSection({
  title,
  description,
  icon: Icon,
  count,
  defaultOpen = false,
  printOpen = true,
  children,
}: {
  title: string
  description?: string
  icon?: React.ComponentType<{ className?: string }>
  /** Shown as a badge beside the title. Omit when there is nothing countable. */
  count?: number
  defaultOpen?: boolean
  /** Whether a print job expands this regardless of the screen state. See the note above. */
  printOpen?: boolean
  children: React.ReactNode
}) {
  return (
    // `<Card>` wrapping `<Collapsible>`, rather than `render={<Card />}`. Base UI's `useRender` merges
    // the two elements' props and the primitive's own `data-slot="collapsible"` wins — which silently
    // costs the section every rule keyed on `[data-slot="card"]`, including the print stylesheet's, so
    // this one card would have printed with a screen shadow. Nesting keeps both slots.
    <Card>
      <Collapsible
        defaultOpen={defaultOpen}
        className="flex flex-col gap-(--card-spacing)"
      >
        {/*
          `group` so the chevron can read the trigger's own state: Base UI puts `data-panel-open` on
          the trigger while the panel is open, and the shadcn wrapper adds no group class of its own.
        */}
        <CollapsibleTrigger
          className={cn(
            "group flex w-full cursor-pointer items-center gap-3 focus-visible:ring-ring",
            "px-(--card-spacing) text-left focus-visible:ring-2 focus-visible:outline-none"
          )}
        >
          {Icon ? (
            <Icon className="size-4 shrink-0 text-muted-foreground" />
          ) : null}
          <span className="min-w-0 flex-1">
            <span className="block font-heading text-base font-medium">
              {title}
            </span>
            {description ? (
              <span className="block text-sm text-muted-foreground">
                {description}
              </span>
            ) : null}
          </span>
          {count !== undefined ? (
            <Badge variant="secondary" className="tabular-nums">
              {count}
            </Badge>
          ) : null}
          <ChevronDownIcon
            aria-hidden
            className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[panel-open]:rotate-180 print:hidden"
          />
        </CollapsibleTrigger>

        <CollapsibleContent keepMounted data-print={printMode(printOpen)}>
          <div className="border-t px-(--card-spacing) pt-(--card-spacing)">
            {children}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}

/**
 * The same behaviour without the card — for detail that belongs *inside* a section rather than
 * beside it. A card nested in a card reads as a second subject; this reads as a footnote.
 */
export function Disclosure({
  label,
  defaultOpen = false,
  printOpen = true,
  children,
}: {
  label: string
  defaultOpen?: boolean
  /** Whether a print job expands this regardless of the screen state. See the note above. */
  printOpen?: boolean
  children: React.ReactNode
}) {
  return (
    <Collapsible defaultOpen={defaultOpen}>
      <CollapsibleTrigger className="group flex cursor-pointer items-center gap-1.5 rounded text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none print:hidden">
        <ChevronDownIcon
          aria-hidden
          className="size-3.5 transition-transform group-data-[panel-open]:rotate-180"
        />
        {label}
      </CollapsibleTrigger>

      {/* The trigger is a control and does not print; the label it carries still has to. */}
      {printOpen ? (
        <span className="hidden text-xs font-medium text-muted-foreground print:block">
          {label}
        </span>
      ) : null}

      <CollapsibleContent keepMounted data-print={printMode(printOpen)}>
        <div className="pt-3">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  )
}
