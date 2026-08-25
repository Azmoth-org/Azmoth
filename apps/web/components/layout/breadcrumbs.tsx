import Link from "next/link"
import * as React from "react"

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@workspace/ui/components/breadcrumb"

/**
 * Where the reader is, and one click back up.
 *
 * This used to be a hand-written `<nav><ol>` with its own separator and its own `aria-current`,
 * because `packages/ui` had no breadcrumb. It has one now, so this is a thin adapter over it: the
 * `trail` shape the two call sites already pass, rendered with the shared primitive.
 *
 * The semantics are the part worth getting right, and they are the reason the primitive is worth
 * using rather than reproducing. `Breadcrumb` renders `<nav aria-label="breadcrumb">`,
 * `BreadcrumbList` an `<ol>`, `BreadcrumbSeparator` a `role="presentation" aria-hidden` list item so
 * "chevron right" is not announced between every level, and `BreadcrumbPage` a
 * `role="link" aria-disabled aria-current="page"` — the page the reader is on is not a link.
 *
 * A server component: no state, no interaction, so it renders in the same pass as the page around it.
 */
export type Crumb = {
  label: string
  /** Omitted on the last crumb: the page the reader is on is not a link. */
  href?: string
}

export function Breadcrumbs({ trail }: { trail: readonly Crumb[] }) {
  if (trail.length === 0) return null

  return (
    <Breadcrumb>
      <BreadcrumbList>
        {trail.map((crumb, index) => {
          const last = index === trail.length - 1
          return (
            <React.Fragment key={`${crumb.label}-${index}`}>
              {index > 0 ? <BreadcrumbSeparator /> : null}
              <BreadcrumbItem>
                {crumb.href && !last ? (
                  // `render` rather than `asChild`: this registry is built on Base UI, which takes
                  // the element to render as a prop. Next's `Link` keeps client-side navigation.
                  <BreadcrumbLink render={<Link href={crumb.href} />}>{crumb.label}</BreadcrumbLink>
                ) : (
                  <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                )}
              </BreadcrumbItem>
            </React.Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
