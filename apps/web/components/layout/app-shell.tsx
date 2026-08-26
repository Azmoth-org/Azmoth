"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { Badge } from "@workspace/ui/components/badge"
import { Separator } from "@workspace/ui/components/separator"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@workspace/ui/components/sidebar"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@workspace/ui/components/tooltip"

import { NAV_ITEMS, activeHref, type NavItem } from "@/components/layout/nav"
import { ThemeToggle } from "@/components/layout/theme-toggle"
import { UserMenu, type SessionUser } from "@/components/layout/user-menu"

/**
 * The frame every screen sits in.
 *
 * It exists for two reasons that have nothing to do with decoration.
 *
 * **Navigation.** The screens did not link to each other. `/rules` and `/padnext/batch` were
 * reachable only by typing their URLs, which meant that in practice nobody found them — including
 * the reviewer whose job the rule queue exists to support.
 *
 * **One page frame instead of four.** `<main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8
 * sm:px-6">` was copy-pasted into each page. Four copies of a layout drift, and on a screen where a
 * warning banner has to appear above the fold that drift is not cosmetic.
 *
 * ## Built on the shared `Sidebar`
 *
 * This was a hand-rolled `<aside>` plus, below `lg`, a horizontal strip of links that scrolled
 * sideways in the top bar. The strip was the compromise: "a drawer needs a portal, a focus trap and
 * state, and four links do not justify any of it." There are seven links now, and
 * `@workspace/ui/components/sidebar` brings the portal, the focus trap and the state with it — so
 * the compromise is no longer worth its cost. Narrow screens get a real off-canvas sheet, and wide
 * ones get something the hand-rolled version never had:
 *
 * - **A collapse.** `collapsible="icon"` narrows the rail to icons, which matters on `/review`,
 *   where two position tables compete for horizontal space and 16rem of navigation is 16rem the
 *   invoice does not get. The state persists in a cookie, so it survives a reload.
 * - **`SidebarRail`** — the whole edge is a drag target for that collapse, not just a small button.
 * - **⌘B / Ctrl+B**, which is what a reader who lives in editors will try first.
 * - **Tooltips on the collapsed rail**, so an icon-only entry still says its name.
 *
 * `variant="inset"` is what makes the content a floating panel on a tinted ground rather than a
 * column butted against a border: on a screen this dense it is the cheapest way to say where the
 * document ends and the application begins.
 *
 * `defaultOpen` comes from the server, read out of the same cookie the provider writes. Without it
 * the first paint is always the expanded rail, which then snaps shut for anyone who collapsed it.
 *
 * So does `user`. The shell is only ever rendered by `app/(app)/layout.tsx`, which has already
 * resolved the Better Auth session — that resolution is what decides whether any of this renders at
 * all — so who is signed in arrives as a prop rather than being fetched again from the browser. It
 * is optional because one caller has no session to hand it: `app/not-found.tsx`, which is served for
 * a URL that matches no route and therefore never ran the layout.
 */
export function AppShell({
  children,
  defaultOpen = true,
  user,
}: {
  children: React.ReactNode
  /** The persisted rail state, read from the `sidebar_state` cookie in `(app)/layout.tsx`. */
  defaultOpen?: boolean
  /** The signed-in person, for the account menu in the top bar. */
  user?: SessionUser
}) {
  const pathname = usePathname()
  const active = activeHref(pathname)

  const workflow = NAV_ITEMS.filter((item) => !item.internal)
  const internal = NAV_ITEMS.filter((item) => item.internal)

  return (
    <SidebarProvider defaultOpen={defaultOpen}>
      {/*
        Navigation is not part of the document — `/review` prints a billing proposal, not the
        application it was read in — but that is not arranged here. `Sidebar` puts this `className` on
        its inner container, which leaves the outer wrapper and the spacer reserving 16rem of page
        width behind; the print stylesheet in `@workspace/ui` hides `[data-slot="sidebar"]` instead.
      */}
      <Sidebar collapsible="icon" variant="inset">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" render={<Link href="/" />}>
                <span className="bg-primary text-primary-foreground grid size-8 shrink-0 place-items-center rounded-lg font-mono text-[11px] font-medium">
                  GO
                </span>
                <span className="grid flex-1 text-left leading-tight">
                  <span className="truncate font-semibold">Govatax</span>
                  <span className="text-sidebar-foreground/70 truncate text-xs">GOÄ-Prüfung</span>
                </span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <SidebarContent>
          <NavGroup items={workflow} active={active} label="Arbeitsablauf" />
          <NavGroup items={internal} active={active} label="Intern" />
        </SidebarContent>

        <SidebarFooter>
          <Disclaimer />
        </SidebarFooter>

        <SidebarRail />
      </Sidebar>

      <SidebarInset>
        <header className="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 rounded-t-xl border-b px-4 backdrop-blur print:hidden">
          <SidebarTrigger />
          <Separator orientation="vertical" className="mr-1 h-4" />
          <CurrentScreen active={active} />
          <div className="ml-auto flex items-center gap-2">
            {/*
              The environment is stated in the chrome, on every screen, because this build must never
              be mistaken for one cleared to hold real data. The disclaimer banners say it in prose;
              this says it where a glance lands.
            */}
            <Badge variant="outline" className="hidden sm:inline-flex">
              Nur synthetische Daten
            </Badge>
            <ThemeToggle />
            {user ? (
              <>
                {/*
                  A rule between the tooling and the identity. The theme toggle changes how this
                  screen looks; the menu beside it ends the session — two very different weights of
                  action, and on a bar this narrow a separator is the cheapest way to say so.
                */}
                <Separator orientation="vertical" className="mx-0.5 h-4" />
                <UserMenu user={user} />
              </>
            ) : null}
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-8 sm:px-6 print:max-w-none print:space-y-4 print:p-0">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

function NavGroup({
  items,
  active,
  label,
}: {
  items: readonly NavItem[]
  active: string | null
  label: string
}) {
  if (items.length === 0) return null

  return (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => {
            const Icon = item.icon
            const current = active === item.href
            return (
              <SidebarMenuItem key={item.href}>
                <SidebarMenuButton
                  isActive={current}
                  // The name, for the collapsed rail — where the label is not rendered at all and an
                  // icon on its own is a guess.
                  tooltip={item.label}
                  render={<Link href={item.href} aria-current={current ? "page" : undefined} />}
                >
                  <Icon />
                  <span>{item.label}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

/** The screen's name in the top bar, so the tab and the page agree about where the reader is. */
function CurrentScreen({ active }: { active: string | null }) {
  const item = NAV_ITEMS.find((entry) => entry.href === active)
  if (!item) return <span className="text-muted-foreground text-sm">Übersicht</span>

  return (
    <div className="flex min-w-0 items-center gap-2 text-sm">
      <span className="truncate font-medium">{item.label}</span>
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
 * screen that happens to be showing a proposal. Collapsed to its first sentence when the rail is —
 * `group-data-[collapsible=icon]` is how the sidebar tells its contents which state it is in — with
 * the full text kept in a tooltip rather than dropped, because the reason this build must not be
 * trusted with real data does not stop being true when the rail is narrow.
 */
function Disclaimer() {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <div className="text-sidebar-foreground/70 cursor-default px-2 py-1 text-xs group-data-[collapsible=icon]:hidden">
            {/*
              `text-sidebar-*`, not `text-foreground`. The rail carries its own light/dark pair, and
              nothing guarantees it resolves to the same surface as the document — it is one step
              darker in both modes today. Reading the rail's own tokens is what keeps this legible
              whichever theme is on, and whatever the rail's ground becomes next.
            */}
            <p className="text-sidebar-foreground font-medium">Entwurf, keine Rechnung.</p>
            <p className="mt-1">
              Die ärztliche Prüfung ist zwingend erforderlich. Die Regelabdeckung ist unvollständig.
            </p>
          </div>
        }
      />
      <TooltipContent side="right" className="max-w-64">
        Entwurf, keine Rechnung. Die ärztliche Prüfung ist zwingend erforderlich. Die Regelabdeckung
        ist unvollständig.
      </TooltipContent>
    </Tooltip>
  )
}
