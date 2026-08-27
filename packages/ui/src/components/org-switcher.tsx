"use client"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@workspace/ui/components/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@workspace/ui/components/sidebar"
import { cn } from "@workspace/ui/lib/utils"
import { CheckIcon, ChevronsUpDownIcon, PlusIcon } from "lucide-react"

/** One switchable organisation. `meta` is the second line — a slug, a role, a plan. */
export type OrgSwitcherItem = {
  id: string
  name: string
  meta?: string
  logo?: React.ReactNode
}

/**
 * The organisation in the rail's header, and the menu that changes it.
 *
 * This is the shadcn `TeamSwitcher` template, generalised into something an application can drive.
 * Three things changed, and each one was load-bearing.
 *
 * **It is controlled.** The template held `useState(teams[0])` internally, which made it a switcher
 * that changed a local variable and nothing else — the selection could not survive a navigation, let
 * alone reach a server. `activeId` and `onSelect` hand that decision to the caller, which is where
 * the Better Auth session lives.
 *
 * **It is renamed.** The template called this a *team*, and Better Auth's organization plugin has a
 * separate, real `teams` feature with its own `activeTeamId` on the session. Keeping the template's
 * noun would have meant two different things called "team" in one sidebar.
 *
 * **The ⌘1 / ⌘2 shortcut labels are gone.** The template rendered them next to each entry and bound
 * nothing, so they advertised keystrokes that did nothing. A check mark on the active row says what
 * the reader actually needs to know, and it is true.
 *
 * The empty state is deliberate and not an error: a user who belongs to no organisation yet is the
 * normal first state after signing up, and the menu's job there is to offer creating one rather than
 * to render a blank trigger.
 */
export function OrgSwitcher({
  items,
  activeId,
  onSelect,
  label,
  emptyName,
  emptyMeta,
  fallbackLogo,
  addLabel,
  onAdd,
  triggerLabel,
  pending = false,
}: {
  items: readonly OrgSwitcherItem[]
  /** The active organisation's id, or null when the user belongs to none. */
  activeId?: string | null
  onSelect: (id: string) => void
  /** The menu's group heading — "switch organisation", in the caller's language. */
  label: string
  /** The trigger's first line when there is no active organisation. */
  emptyName: string
  /** The trigger's second line in that same state. */
  emptyMeta?: string
  /** Stands in for an organisation that has no logo of its own, which is all of them by default. */
  fallbackLogo?: React.ReactNode
  /** Omitted, along with the whole entry, on deployments where a user may not create one. */
  addLabel?: string
  onAdd?: () => void
  /** The trigger's accessible name. */
  triggerLabel: string
  /** Disables selection while a switch is in flight. */
  pending?: boolean
}) {
  const { isMobile } = useSidebar()
  const active = items.find((item) => item.id === activeId) ?? null

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton
                size="lg"
                className="data-open:bg-sidebar-accent data-open:text-sidebar-accent-foreground"
                aria-label={triggerLabel}
              />
            }
          >
            <div className="grid aspect-square size-8 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground [&>svg]:size-4">
              {active?.logo ?? fallbackLogo}
            </div>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-semibold">
                {active?.name ?? emptyName}
              </span>
              <span className="truncate text-xs text-sidebar-foreground/70">
                {active?.meta ?? (active ? undefined : emptyMeta)}
              </span>
            </div>
            <ChevronsUpDownIcon className="ml-auto size-4" />
          </DropdownMenuTrigger>

          <DropdownMenuContent
            className="min-w-60"
            align="start"
            side={isMobile ? "bottom" : "right"}
            sideOffset={4}
          >
            {items.length > 0 ? (
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-xs text-muted-foreground">
                  {label}
                </DropdownMenuLabel>
                {items.map((item) => {
                  const current = item.id === activeId
                  return (
                    <DropdownMenuItem
                      key={item.id}
                      disabled={pending}
                      onClick={() => onSelect(item.id)}
                      className="gap-2 p-2"
                    >
                      <div className="grid size-6 shrink-0 place-items-center rounded-md border [&>svg]:size-3.5">
                        {item.logo ?? fallbackLogo}
                      </div>
                      <span className="min-w-0 flex-1 truncate">
                        {item.name}
                      </span>
                      {/*
                        Reserved rather than conditionally rendered: a check that appears and
                        disappears shifts every name in the list by its own width as the reader moves
                        down the menu.
                      */}
                      <CheckIcon
                        className={cn(
                          "size-4 shrink-0",
                          current ? "opacity-100" : "opacity-0"
                        )}
                        aria-hidden={!current}
                      />
                    </DropdownMenuItem>
                  )
                })}
              </DropdownMenuGroup>
            ) : null}

            {addLabel && onAdd ? (
              <>
                {items.length > 0 ? <DropdownMenuSeparator /> : null}
                <DropdownMenuItem
                  disabled={pending}
                  onClick={onAdd}
                  className="gap-2 p-2"
                >
                  <div className="grid size-6 shrink-0 place-items-center rounded-md border bg-transparent [&>svg]:size-3.5">
                    <PlusIcon />
                  </div>
                  <span className="font-medium text-muted-foreground">
                    {addLabel}
                  </span>
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
