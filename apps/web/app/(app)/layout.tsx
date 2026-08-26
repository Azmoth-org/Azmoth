import { cookies, headers } from "next/headers"
import { redirect } from "next/navigation"

import { AppShell } from "@/components/layout/app-shell"
import { getAuth } from "@/lib/auth"

/**
 * The signed-in half of the application: every screen that shows clinical data, inside the shell.
 *
 * ## This is where access is actually decided
 *
 * `middleware.ts` redirects a request with no session cookie before it reaches here, and that is a
 * convenience — it cannot verify a cookie without a database. The `getSession` call below is the
 * real check: it validates the token against the `session` table and returns `null` for anything
 * forged, expired or revoked. A layout is the right place for it because every route in this group
 * renders through it, so a screen added tomorrow is protected without anyone remembering to protect
 * it.
 *
 * The redirect carries `next`, so signing in resumes where the reader was going. Reading the path
 * from `x-current-path` — set by nothing in this app — would be the usual way to get that wrong; it
 * comes from the middleware's own redirect for a request that had no cookie at all, and from
 * `next/headers` here only for the narrower case of a cookie that failed verification.
 *
 * ## Why the sidebar cookie moved here from the root layout
 *
 * `sidebar_state` describes the rail, and the rail only exists in this group. Reading it in the root
 * layout made `/login` — which has no sidebar — a dynamic render that depended on a cookie about a
 * component it does not have.
 */
export default async function AppLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const requestHeaders = await headers()
  const session = await getAuth().api.getSession({ headers: requestHeaders })

  if (!session) {
    redirect("/login")
  }

  // `SidebarProvider` writes this when the rail is toggled but cannot read it during the server
  // render, so without this every first paint is the expanded rail — which then snaps shut for
  // anyone who collapsed it. Any value other than a literal `"false"` means open, a missing cookie
  // included.
  const store = await cookies()
  const defaultOpen = store.get("sidebar_state")?.value !== "false"

  return (
    <AppShell
      defaultOpen={defaultOpen}
      user={{ name: session.user.name, email: session.user.email }}
    >
      {children}
    </AppShell>
  )
}
