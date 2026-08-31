"use client"

import { LogOutIcon } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import * as React from "react"

import { Badge } from "@workspace/ui/components/badge"
import { DropdownMenuItem } from "@workspace/ui/components/dropdown-menu"
import { NavMain, type NavMainItem } from "@workspace/ui/components/nav-main"
import { NavUser } from "@workspace/ui/components/nav-user"
import { Separator } from "@workspace/ui/components/separator"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@workspace/ui/components/sidebar"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@workspace/ui/components/tooltip"

import { AzmothMark } from "@/components/brand/azmoth-mark"
import { NAV_ITEMS, activeHref } from "@/components/layout/nav"
import {
  OrganisationSwitcher,
  type OrganisationSnapshot,
} from "@/components/layout/organisation-switcher"
import { ThemeToggle } from "@/components/layout/theme-toggle"
import { authClient } from "@/lib/auth-client"

/** What the shell knows about the signed-in person. Resolved on the server, passed down as props. */
export type SessionUser = {
  name: string
  email: string
}

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
 * ## Composed from the shared sidebar templates
 *
 * The rail's three parts — header, body, footer — are now `OrgSwitcher`, `NavMain` and `NavUser`
 * from `@workspace/ui`, rather than the `SidebarMenu` markup this file used to spell out itself. The
 * markup was not wrong; what it could not do was hold an organisation. The header used to be a fixed
 * wordmark tile, and the practice a reviewer works on behalf of has to be *selectable* — which is a
 * dropdown, a list, an active item and a mutation, and none of that is worth hand-writing when the
 * package has it.
 *
 * The identity moved with it. It was a menu in the top bar beside the theme toggle; it is now the
 * rail's footer, which is where every screen in this shape puts it and which frees the bar for the
 * things that describe the *screen* rather than the session.
 *
 * `collapsible="icon"` narrows the rail to icons, which matters on `/review`, where two position
 * tables compete for horizontal space and 16rem of navigation is 16rem the invoice does not get. The
 * state persists in a cookie, so it survives a reload. `SidebarRail` makes the whole edge a drag
 * target for that collapse, ⌘B / Ctrl+B does it from the keyboard, and the collapsed rail keeps
 * tooltips so an icon-only entry still says its name.
 *
 * `variant="inset"` is what makes the content a floating panel on a tinted ground rather than a
 * column butted against a border: on a screen this dense it is the cheapest way to say where the
 * document ends and the application begins.
 *
 * `defaultOpen`, `user` and `organisations` all come from the server. `app/(app)/layout.tsx` has
 * already resolved the Better Auth session — that resolution is what decides whether any of this
 * renders at all — so who is signed in and which practices they belong to arrive as props rather
 * than being fetched again from the browser.
 */
export function AppShell({
  children,
  defaultOpen = true,
  user,
  organisations,
}: {
  children: React.ReactNode
  /** The persisted rail state, read from the `sidebar_state` cookie in `(app)/layout.tsx`. */
  defaultOpen?: boolean
  /** The signed-in person, for the rail's footer. */
  user?: SessionUser
  /** The organisations the session can switch between, resolved server-side. */
  organisations?: OrganisationSnapshot
}) {
  const pathname = usePathname()
  const active = activeHref(pathname)

  const toNavItem = (item: (typeof NAV_ITEMS)[number]): NavMainItem => {
    const Icon = item.icon
    return {
      title: item.label,
      url: item.href,
      icon: <Icon />,
      isActive: active === item.href,
    }
  }

  const workflow = NAV_ITEMS.filter((item) => !item.internal).map(toNavItem)
  const internal = NAV_ITEMS.filter((item) => item.internal).map(toNavItem)

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
          {organisations ? (
            <OrganisationSwitcher snapshot={organisations} />
          ) : (
            <Wordmark />
          )}
        </SidebarHeader>

        <SidebarContent>
          <NavMain
            label="Arbeitsablauf"
            items={workflow}
            linkRender={navLink}
          />
          <NavMain label="Intern" items={internal} linkRender={navLink} />
        </SidebarContent>

        <SidebarFooter>
          <Disclaimer />
          {user ? <AccountMenu user={user} /> : null}
        </SidebarFooter>

        <SidebarRail />
      </Sidebar>

      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 rounded-t-xl border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/80 print:hidden">
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
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-8 sm:px-6 print:max-w-none print:space-y-4 print:p-0">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

/**
 * A `next/link` for a rail entry.
 *
 * `NavMain` cannot build this itself — `@workspace/ui` has no router — so it asks for the element and
 * merges its own props onto it. `aria-current` is set here rather than there because the package
 * knows which row is highlighted but not that "page" is the right token for it.
 */
function navLink(item: { url: string; isActive?: boolean }) {
  return (
    <Link href={item.url} aria-current={item.isActive ? "page" : undefined} />
  )
}

/**
 * The product's mark, for the one caller that has no session to switch organisations with.
 *
 * `organisations` is optional on this shell, and the fallback has to be *something* — a rail whose
 * header is blank reads as a component that failed to load rather than one that was not given data.
 */
function Wordmark() {
  return (
    <Link
      href="/"
      className="flex items-center gap-2 px-1.5 py-1.5"
      aria-label="Azmoth — GOÄ-Prüfung"
    >
      {/*
        The real monogram, replacing an `AZ` tile in `bg-primary` that stood in before the brand
        existed. It takes `currentColor` through a CSS mask, so it follows the rail into dark mode
        rather than needing a second file — see `AzmothMark`.
      */}
      <AzmothMark className="size-8" />
      <span className="grid flex-1 text-left leading-tight group-data-[collapsible=icon]:hidden">
        <span className="truncate font-semibold">Azmoth</span>
        <span className="truncate text-xs text-sidebar-foreground/70">
          GOÄ-Prüfung
        </span>
      </span>
    </Link>
  )
}

/**
 * Who is signed in, and the way out, in the rail's footer.
 *
 * ## The identity is a prop, not a hook
 *
 * `authClient.useSession()` would work and is one line shorter. It also means the footer renders
 * empty, then fills in after a round-trip — a name appearing a moment after the page does, on every
 * navigation. `app/(app)/layout.tsx` has already resolved the session (it is the check that decides
 * whether this screen renders at all), so passing the two fields it read is both cheaper and
 * flicker-free.
 *
 * ## Signing out is a full navigation, not a router push
 *
 * `router.push` alone would leave the React Router cache holding the rendered proposals of the person
 * who just left — visible again with the back button, because a client-side navigation does not
 * re-render a server component it already has. `router.refresh()` discards that cache, and the push
 * then lands on a `/login` the middleware will not bounce, because the cookie is gone by then.
 *
 * The entry is disabled while the call is in flight. Not for the network's sake: a second click races
 * the first, the second request arrives without a cookie and fails — which would show an error to
 * somebody whose sign-out actually worked.
 */
function AccountMenu({ user }: { user: SessionUser }) {
  const router = useRouter()
  const [pending, setPending] = React.useState(false)

  async function abmelden() {
    if (pending) return
    setPending(true)
    try {
      await authClient.signOut()
    } finally {
      // Even if the call failed, get off this screen: a sign-out that appears to do nothing is the
      // one failure mode where a reviewer walks away from an open session.
      router.refresh()
      router.push("/login")
    }
  }

  return (
    <NavUser
      // The email under the name, not a second copy of it. Two colleagues can share a display name
      // and an audit log cannot; the address is what `audit_events.actor` resolves back to.
      name={user.name || "Konto"}
      email={user.email}
      initials={initials(user.name, user.email)}
      menuLabel={`Angemeldet als ${user.email}. Kontomenü öffnen`}
    >
      <DropdownMenuItem disabled={pending} onClick={abmelden}>
        <LogOutIcon />
        {pending ? "Wird abgemeldet…" : "Abmelden"}
      </DropdownMenuItem>
    </NavUser>
  )
}

/**
 * Up to two letters for the avatar.
 *
 * From the name when there is one, from the email otherwise — a signed-up account always has an
 * address and may have left the name blank, so falling back to the address is what keeps the circle
 * from being empty.
 */
function initials(name: string, email: string): string {
  const source = name.trim() || email.trim()
  const parts = source.split(/[\s.@_-]+/).filter(Boolean)
  const letters = parts.slice(0, 2).map((part) => part[0] ?? "")
  return (letters.join("") || source.slice(0, 2)).toUpperCase()
}

/** The screen's name in the top bar, so the tab and the page agree about where the reader is. */
function CurrentScreen({ active }: { active: string | null }) {
  const item = NAV_ITEMS.find((entry) => entry.href === active)
  if (!item)
    return <span className="text-sm text-muted-foreground">Übersicht</span>

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
 * screen that happens to be showing a proposal. Hidden when the rail is collapsed —
 * `group-data-[collapsible=icon]` is how the sidebar tells its contents which state it is in — with
 * the full text kept in a tooltip rather than dropped, because the reason this build must not be
 * trusted with real data does not stop being true when the rail is narrow.
 */
function Disclaimer() {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <div className="cursor-default px-2 py-1 text-xs text-sidebar-foreground/70 group-data-[collapsible=icon]:hidden">
            {/*
              `text-sidebar-*`, not `text-foreground`. The rail carries its own light/dark pair, and
              nothing guarantees it resolves to the same surface as the document — it is one step
              darker in both modes today. Reading the rail's own tokens is what keeps this legible
              whichever theme is on, and whatever the rail's ground becomes next.
            */}
            <p className="font-medium text-sidebar-foreground">
              Entwurf, keine Rechnung.
            </p>
            <p className="mt-1">
              Die ärztliche Prüfung ist zwingend erforderlich. Die
              Regelabdeckung ist unvollständig.
            </p>
          </div>
        }
      />
      <TooltipContent side="right" className="max-w-64">
        Entwurf, keine Rechnung. Die ärztliche Prüfung ist zwingend
        erforderlich. Die Regelabdeckung ist unvollständig.
      </TooltipContent>
    </Tooltip>
  )
}
