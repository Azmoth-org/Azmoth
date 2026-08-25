"use client"

import { ChevronDownIcon } from "lucide-react"
import * as React from "react"

import { Badge } from "@workspace/ui/components/badge"
import { Card } from "@workspace/ui/components/card"
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
 * Both are collapsed, and by default **neither is collapsed on paper**. A printed proposal that
 * quietly omitted the versions it was produced under would be exactly the document this system
 * exists not to make: the receipt hash means nothing without the catalog and rule versions it hashes
 * over. So the closed state is `hidden print:block!` rather than an unmounted subtree — the content
 * is in the DOM, the screen just is not showing it.
 *
 * `printOpen={false}` is the exception, for the one kind of detail that is genuinely not part of the
 * document: measured stage timings and raw JSON, which are excluded from the receipt hash precisely
 * because they are not evidence. Several pages of them behind a physician's signature would be noise
 * asserting itself as record.
 *
 * Native `<details>` was the obvious first choice and cannot do any of this: a closed `<details>`
 * hides its content through the browser's own machinery, which a print stylesheet cannot reach.
 */
function useDisclosure(defaultOpen: boolean) {
  const [open, setOpen] = React.useState(defaultOpen)
  const contentId = React.useId()
  return { open, toggle: () => setOpen((value) => !value), contentId }
}

/** Hidden on screen; shown on paper unless this is the section that does not belong on paper. */
function contentClass(open: boolean, printOpen: boolean, className?: string) {
  return cn(open ? (printOpen ? null : "print:hidden") : printOpen ? "hidden print:block!" : "hidden", className)
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
  const { open, toggle, contentId } = useDisclosure(defaultOpen)

  return (
    <Card>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={contentId}
        className="focus-visible:ring-ring flex w-full cursor-pointer items-center gap-3 px-(--card-spacing) text-left focus-visible:ring-2 focus-visible:outline-none"
      >
        {Icon ? <Icon className="text-muted-foreground size-4 shrink-0" /> : null}
        <span className="min-w-0 flex-1">
          <span className="font-heading block text-base font-medium">{title}</span>
          {description ? (
            <span className="text-muted-foreground block text-sm">{description}</span>
          ) : null}
        </span>
        {count !== undefined ? (
          <Badge variant="secondary" className="tabular-nums">
            {count}
          </Badge>
        ) : null}
        <span className="text-muted-foreground shrink-0 text-xs print:hidden">
          {open ? "einklappen" : "ausklappen"}
        </span>
        <ChevronDownIcon
          aria-hidden
          className={cn(
            "text-muted-foreground size-4 shrink-0 transition-transform print:hidden",
            open ? "rotate-180" : null,
          )}
        />
      </button>

      <div
        id={contentId}
        className={contentClass(open, printOpen, "border-t px-(--card-spacing) pt-(--card-spacing)")}
      >
        {children}
      </div>
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
  const { open, toggle, contentId } = useDisclosure(defaultOpen)

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={contentId}
        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring flex cursor-pointer items-center gap-1.5 rounded text-xs font-medium focus-visible:ring-2 focus-visible:outline-none print:hidden"
      >
        <ChevronDownIcon
          aria-hidden
          className={cn("size-3.5 transition-transform", open ? "rotate-180" : null)}
        />
        {label}
      </button>
      {/* The trigger is a control and does not print; the label it carries still has to. */}
      {printOpen ? (
        <span className="text-muted-foreground hidden text-xs font-medium print:block">{label}</span>
      ) : null}
      <div id={contentId} className={contentClass(open, printOpen, "pt-3")}>
        {children}
      </div>
    </div>
  )
}
