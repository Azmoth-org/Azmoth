import { ChevronRightIcon } from "lucide-react"
import Link from "next/link"

/**
 * Where the reader is, and one click back up.
 *
 * Built here rather than pulled in as a primitive: `packages/ui` has no breadcrumb, and what this
 * needs is an ordered list, a separator and one `aria-current` — a dependency for that would be more
 * code to review than the component.
 *
 * The semantics are the part worth getting right, because a breadcrumb rendered as a row of `<div>`s
 * is decoration that a screen reader announces as noise. `<nav aria-label>` names the landmark, the
 * `<ol>` says these are ordered steps, the separators are `aria-hidden` so "chevron right" is not
 * read between every level, and the last item is plain text with `aria-current="page"` rather than a
 * link to where the reader already is.
 *
 * A server component. It has no state and takes no interaction, so there is nothing here worth a
 * client boundary — which also means it renders in the same pass as the page around it.
 */
export type Crumb = {
  label: string
  /** Omitted on the last crumb: the page the reader is on is not a link. */
  href?: string
}

export function Breadcrumbs({ trail }: { trail: readonly Crumb[] }) {
  if (trail.length === 0) return null

  return (
    <nav aria-label="Brotkrumen">
      <ol className="text-muted-foreground flex flex-wrap items-center gap-1.5 text-xs">
        {trail.map((crumb, index) => {
          const last = index === trail.length - 1
          return (
            <li key={`${crumb.label}-${index}`} className="flex items-center gap-1.5">
              {index > 0 ? (
                <ChevronRightIcon className="size-3 shrink-0 opacity-60" aria-hidden />
              ) : null}
              {crumb.href && !last ? (
                <Link
                  href={crumb.href}
                  className="hover:text-foreground rounded transition-colors hover:underline"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span aria-current={last ? "page" : undefined} className="text-foreground">
                  {crumb.label}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
