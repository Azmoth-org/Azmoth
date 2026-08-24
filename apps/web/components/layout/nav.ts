import {
  FileCheck2Icon,
  HistoryIcon,
  LayersIcon,
  LayoutDashboardIcon,
  ListIcon,
  ScaleIcon,
  StethoscopeIcon,
} from "lucide-react"

/**
 * The application's screens, in the order the work happens.
 *
 * One list, used by the sidebar, the mobile nav and the dashboard cards, so a new screen cannot be
 * added to one and forgotten in the others — which is how `/rules` and `/padnext/batch` came to be
 * reachable only by typing their URLs.
 *
 * The dashboard is the first entry and is in this list rather than beside it, so the sidebar
 * highlights it like any other screen and the top bar names it. It is excluded from the *workspace
 * grid* on the dashboard itself by `WORKSPACE_ITEMS` below — a card linking to the page it is on is
 * not navigation.
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

/** The dashboard's own path. Named because two things below have to agree about it. */
export const DASHBOARD_HREF = "/"

export const NAV_ITEMS: readonly NavItem[] = [
  {
    href: DASHBOARD_HREF,
    label: "Übersicht",
    description:
      "Systemstatus, die letzten Abrechnungsvorschläge und die letzten Stapelprüfungen auf einen Blick.",
    icon: LayoutDashboardIcon,
  },
  {
    href: "/review",
    label: "Prüfung",
    description:
      "Ärztliche Prüfung eines deterministisch erzeugten GOÄ-Abrechnungsvorschlags. Nur synthetische Daten.",
    icon: StethoscopeIcon,
  },
  {
    href: "/proposals",
    label: "Alle Prüfungen",
    description:
      "Alle gespeicherten GOÄ-Abrechnungsvorschläge, filterbar nach Status und Fall-ID. Nur synthetische Daten.",
    icon: ListIcon,
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
    href: "/padnext/batch/history",
    label: "Stapel-Historie",
    description:
      "Alle gespeicherten PADnext-Stapelprüfungen, filterbar nach Status. Nur synthetische Daten.",
    icon: HistoryIcon,
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
 * Every screen except the dashboard — what the dashboard's own card grid renders.
 *
 * Derived rather than a second literal, so adding a screen to `NAV_ITEMS` puts it on the dashboard
 * too. That is the mistake this module was written to prevent, and a hand-maintained copy would
 * reintroduce it one entry at a time.
 */
export const WORKSPACE_ITEMS: readonly NavItem[] = NAV_ITEMS.filter(
  (item) => item.href !== DASHBOARD_HREF,
)

/**
 * Which single nav entry the reader is on, or null for a path outside the nav.
 *
 * Deliberately not a per-item `startsWith` predicate. `/padnext` is a prefix of `/padnext/batch`,
 * which is in turn a prefix of `/padnext/batch/history`, so a predicate would report *three* entries
 * active on the history screen — three highlighted rows and no answer to "where am I". This resolves
 * the longest matching href instead, which keeps exactly one entry active and still highlights
 * Stapelprüfung on a future `/padnext/batch/<id>`.
 *
 * Matching is anchored on a path segment (`href` itself, or `href` followed by `/`), so `/rulesets`
 * would not match `/rules`.
 *
 * The dashboard's `/` needs no special case, and it is worth saying why rather than leaving the next
 * reader to work it out: `pathname === "/"` matches only the root, and the prefix test looks for
 * `"//"`, which no path starts with. So `/` is active on the dashboard and on nothing else, and it
 * never competes with a longer href in the reduce below.
 */
export function activeHref(pathname: string): string | null {
  const matches = NAV_ITEMS.filter(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  )
  if (matches.length === 0) return null
  return matches.reduce((best, item) => (item.href.length > best.href.length ? item : best)).href
}
