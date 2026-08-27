"use client"

import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "@workspace/ui/components/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
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
import { ChevronsUpDownIcon } from "lucide-react"

/**
 * Who is signed in, in the rail's footer, with the account menu hanging off it.
 *
 * The template's menu was a fixed list — "Upgrade to Pro", "Account", "Billing", "Notifications",
 * "Log out". All five are gone and the menu body is `children` instead. Two reasons, and the second
 * is the one that matters: the strings were English in a package that cannot know its consumer's
 * language, and four of the five pointed at screens that only exist in the template's imaginary
 * product. A shared component that ships menu entries also ships the routes behind them, and it has
 * no way to know which of those a given application actually has.
 *
 * The identity is repeated inside the menu, as the template had it. That is not redundancy on a
 * collapsed rail: the trigger is an avatar and nothing else there, so the panel is the only place
 * the name and address are legible.
 *
 * `initials` is a prop rather than derived here. Deriving two letters from a name is easy and
 * deriving them from `"dr.med.maria.muster@praxis.de"` is not, and the caller is the one that knows
 * which of the two it has.
 */
export function NavUser({
  name,
  email,
  initials,
  avatarSrc,
  menuLabel,
  children,
}: {
  name: string
  email: string
  /** Up to two letters for the avatar, for accounts with no picture. */
  initials: string
  /** Omitted on deployments with no avatar source, which is every one that has no object store. */
  avatarSrc?: string
  /** The trigger's accessible name. It must say who is signed in, not just "menu". */
  menuLabel: string
  /** The menu's entries. Supplied by the application, in the application's language. */
  children: React.ReactNode
}) {
  const { isMobile } = useSidebar()

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton
                size="lg"
                className="aria-expanded:bg-sidebar-accent"
                aria-label={menuLabel}
              />
            }
          >
            <Avatar>
              {avatarSrc ? <AvatarImage src={avatarSrc} alt="" /> : null}
              <AvatarFallback className="text-xs font-medium">
                {initials}
              </AvatarFallback>
            </Avatar>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">{name}</span>
              <span className="truncate text-xs">{email}</span>
            </div>
            <ChevronsUpDownIcon className="ml-auto size-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="min-w-56"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuGroup>
              <DropdownMenuLabel className="p-0 font-normal">
                <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                  <Avatar>
                    {avatarSrc ? <AvatarImage src={avatarSrc} alt="" /> : null}
                    <AvatarFallback className="text-xs font-medium">
                      {initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">{name}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {email}
                    </span>
                  </div>
                </div>
              </DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            {children}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
