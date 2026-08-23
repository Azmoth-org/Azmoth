"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { Badge } from "@workspace/ui/components/badge"
import { cn } from "@workspace/ui/lib/utils"

import { NAV_ITEMS, activeHref, type NavItem } from "@/components/layout/nav"
import { ThemeToggle } from "@/components/layout/theme-toggle"

/**
 * The frame every screen sits in: a persistent sidebar, a top bar, and one content column.
 *
 * It exists for two reasons that have nothing to do with decoration.
 *
 * **Navigation.** The four screens previously did not link to each other. `/rules` and
 * `/padnext/batch` were reachable only by typing their URLs, which meant that in practice nobody
 * found them — including the reviewer whose job the rule queue exists to support.
 *
 * **One page frame instead of four.** `<main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8
 * sm:px-6">` was copy-pasted into each page. Four copies of a layout drift, and on a screen where a
 * warning banner has to appear above the fold that drift is not cosmetic.
 *
 * A client component, because the active entry depends on the path. The pages inside it stay server
 * components — this wraps `children`, it does not render them.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const active = activeHref(pathname)

  const workflow = NAV_ITEMS.filter((item) => !item.internal)
  const internal = NAV_ITEMS.filter((item) => item.internal)

  return (
    <div className="bg-background flex min-h-svh flex-col lg:flex-row">
      {/*
        Sidebar on a wide screen. Below `lg` it collapses to the horizontal strip in the top bar
        instead of a drawer: a drawer needs a portal, a focus trap and state, and four links do not
        justify any of it.
      */}
      <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border hidden w-64 shrink-0 border-r lg:flex lg:flex-col">
        <Brand />
        <nav aria-label="Hauptnavigation" className="flex flex-1 flex-col gap-6 px-3 py-4">
          <NavGroup items={workflow} active={active} />
          <NavGroup items={internal} active={active} heading="Intern" />
        </nav>
        <SidebarFooter />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-background/95 border-border supports-[backdrop-filter]:bg-background/80 sticky top-0 z-20 border-b backdrop-blur">
          <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
            <div className="lg:hidden">
              <Brand compact />
            </div>
            <div className="hidden min-w-0 flex-1 lg:block">
              <CurrentScreen active={active} />
            </div>
            <div className="ml-auto flex items-center gap-2">
              {/*
                The environment is stated in the chrome, on every screen, because this build must
                never be mistaken for one cleared to hold real data. The disclaimer banners say it in
                prose; this says it where a glance lands.
              */}
              <Badge variant="outline" className="hidden sm:inline-flex">
                Nur synthetische Daten
              </Badge>
              <ThemeToggle />
            </div>
          </div>

          {/* The same links, as a scrollable strip, for narrow screens. */}
          <nav
            aria-label="Hauptnavigation"
            className="border-border flex gap-1 overflow-x-auto border-t px-2 py-2 lg:hidden"
          >
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active === item.href ? "page" : undefined}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm whitespace-nowrap transition-colors",
                  active === item.href
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-8 sm:px-6">
          {children}
        </main>
      </div>
    </div>
  )
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      href="/"
      className={cn(
        "flex items-center gap-2 font-semibold tracking-tight",
        compact ? "text-sm" : "border-sidebar-border h-14 shrink-0 border-b px-4 text-sm",
      )}
    >
      <span className="bg-primary text-primary-foreground grid size-6 place-items-center rounded font-mono text-[11px]">
        GO
      </span>
      <span>Govatax</span>
      <span className="text-muted-foreground font-normal">GOÄ</span>
    </Link>
  )
}

function NavGroup({
  items,
  active,
  heading,
}: {
  items: readonly NavItem[]
  active: string | null
  heading?: string
}) {
  if (items.length === 0) return null
  return (
    <div className="space-y-1">
      {heading ? (
        <div className="text-muted-foreground px-3 pb-1 text-xs font-medium tracking-wide uppercase">
          {heading}
        </div>
      ) : null}
      {items.map((item) => {
        const Icon = item.icon
        const current = active === item.href
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
              current
                ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
            )}
          >
            <Icon className="size-4 shrink-0" aria-hidden />
            {item.label}
          </Link>
        )
      })}
    </div>
  )
}

/** The screen's name in the top bar, so the tab and the page agree about where the reader is. */
function CurrentScreen({ active }: { active: string | null }) {
  const item = NAV_ITEMS.find((entry) => entry.href === active)
  if (!item) return <span className="text-muted-foreground text-sm">Übersicht</span>
  return (
    <div className="flex min-w-0 items-center gap-2 text-sm">
      <span className="font-medium">{item.label}</span>
      {item.internal ? (
        <Badge variant="secondary" className="shrink-0">
          Intern
        </Badge>
      ) : null}
    </div>
  )
}

/**
 * The standing statement, in the chrome rather than only in a banner.
 *
 * A draft is not an invoice, and that has to be true of the whole application and not only of the
 * screen that happens to be showing a proposal.
 */
function SidebarFooter() {
  return (
    <div className="border-sidebar-border text-muted-foreground border-t px-4 py-3 text-xs">
      <p className="font-medium">Entwurf, keine Rechnung.</p>
      <p className="mt-1">
        Die ärztliche Prüfung ist zwingend erforderlich. Die Regelabdeckung ist unvollständig.
      </p>
    </div>
  )
}
