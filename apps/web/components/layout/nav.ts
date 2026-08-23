import { FileCheck2Icon, LayersIcon, ScaleIcon, StethoscopeIcon } from "lucide-react"

/**
 * The application's screens, in the order the work happens.
 *
 * One list, used by the sidebar, the mobile nav and the dashboard cards, so a new screen cannot be
 * added to one and forgotten in the others — which is how `/rules` and `/padnext/batch` came to be
 * reachable only by typing their URLs.
 *
 * `description` is the same sentence as the screen's own `metadata.description`. Kept identical on
 * purpose: the dashboard card and the browser tab should not describe a screen differently.
 */
export type NavItem = {
  href: string
  label: string
  description: string
  icon: typeof StethoscopeIcon
  /** Internal tooling rather than part of the review workflow. Grouped separately. */
  internal?: boolean
}

export const NAV_ITEMS: readonly NavItem[] = [
  {
    href: "/review",
    label: "Prüfung",
    description:
      "Ärztliche Prüfung eines deterministisch erzeugten GOÄ-Abrechnungsvorschlags. Nur synthetische Daten.",
    icon: StethoscopeIcon,
  },
  {
    href: "/padnext",
    label: "Rechnungsprüfung",
    description:
      "Prüfung einer bereits kodierten PADnext-Lieferung gegen die GOÄ-Regeln. Nur synthetische Daten.",
    icon: FileCheck2Icon,
  },
  {
    href: "/padnext/batch",
    label: "Stapelprüfung",
    description:
      "Mehrere PADnext-Lieferungen auf einmal prüfen und das systemische Risiko über alle Rechnungen bewerten. Nur synthetische Daten.",
    icon: LayersIcon,
  },
  {
    href: "/rules",
    label: "Regelprüfung",
    description:
      "Internes Werkzeug: maschinell extrahierte GOÄ-Regeln prüfen und freigeben, um die Gruppe „unbestätigt“ in künftigen Rechnungsprüfungen zu verkleinern.",
    icon: ScaleIcon,
    internal: true,
  },
]

/**
 * Which single nav entry the reader is on, or null for a path outside the nav.
 *
 * Deliberately not a per-item `startsWith` predicate. `/padnext` is a prefix of `/padnext/batch`, so
 * a predicate would report *both* entries active on the batch screen — two highlighted rows and no
 * answer to "where am I". This resolves the longest matching href instead, which keeps exactly one
 * entry active and still highlights Stapelprüfung on a future `/padnext/batch/<id>`.
 *
 * Matching is anchored on a path segment (`href` itself, or `href` followed by `/`), so `/rulesets`
 * would not match `/rules`.
 */
export function activeHref(pathname: string): string | null {
  const matches = NAV_ITEMS.filter(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  )
  if (matches.length === 0) return null
  return matches.reduce((best, item) => (item.href.length > best.href.length ? item : best)).href
}
