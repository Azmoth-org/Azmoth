"use client"

import { LogOutIcon } from "lucide-react"
import { useRouter } from "next/navigation"
import * as React from "react"

import { Avatar, AvatarFallback } from "@workspace/ui/components/avatar"
import { Button } from "@workspace/ui/components/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@workspace/ui/components/dropdown-menu"

import { authClient } from "@/lib/auth-client"

/** What the shell knows about the signed-in person. Resolved on the server, passed down as props. */
export type SessionUser = {
  name: string
  email: string
}

/**
 * Who is signed in, and the way out.
 *
 * ## The identity is a prop, not a hook
 *
 * `authClient.useSession()` would work and is one line shorter. It also means the top bar renders
 * empty, then fills in after a round-trip — a name appearing a moment after the page does, on every
 * navigation. `app/(app)/layout.tsx` has already resolved the session (it is the check that decides
 * whether this screen renders at all), so passing the two fields it read is both cheaper and
 * flicker-free. This component is `"use client"` for the dropdown and the sign-out call, not for
 * fetching anything.
 *
 * ## Signing out is a full navigation, not a router push
 *
 * `router.push` would leave the React Router cache holding the rendered proposals of the person who
 * just left — visible again with the back button, because a client-side navigation does not
 * re-render a server component it already has. `router.refresh()` before the push discards that
 * cache, and the push then lands on a `/login` the middleware will not bounce, because the cookie
 * is gone by then.
 *
 * The button is disabled while the call is in flight. Not for the network's sake: a second click
 * races the first, and the second request arrives without a cookie and fails — which would show an
 * error to somebody whose sign-out actually worked.
 */
export function UserMenu({ user }: { user: SessionUser }) {
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
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            className="h-9 gap-2 px-1.5 sm:pr-3"
            aria-label={`Angemeldet als ${user.email}. Kontomenü öffnen`}
          >
            <Avatar className="size-6">
              <AvatarFallback className="text-[10px] font-medium">
                {initials(user.name, user.email)}
              </AvatarFallback>
            </Avatar>
            {/*
              The email, not the name. Two colleagues can share a display name and an audit log
              cannot; the address is what `audit_events.actor` resolves back to, so it is what the
              chrome should show. Hidden below `sm`, where the avatar carries it and the accessible
              name above still says it in full.
            */}
            <span className="hidden max-w-40 truncate text-sm font-normal sm:inline">
              {user.email}
            </span>
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-64">
        <div className="px-2 py-1.5">
          <p className="truncate text-sm font-medium">{user.name || "Konto"}</p>
          <p className="text-muted-foreground truncate text-xs">{user.email}</p>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={pending} onClick={abmelden}>
          <LogOutIcon />
          {pending ? "Wird abgemeldet…" : "Abmelden"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
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
