import { cookies, headers } from "next/headers"
import { redirect } from "next/navigation"

import { AppShell } from "@/components/layout/app-shell"
import type { OrganisationSnapshot } from "@/components/layout/organisation-switcher"
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
 *
 * ## Why the organisations are resolved here too
 *
 * The rail's header is a switcher, and a switcher that renders empty and then fills in is a header
 * that changes shape on every navigation. The session is already resolved at this point and the
 * connection is already open, so listing the organisations costs one more query in a pass that had
 * to happen anyway — and the first paint is then correct rather than corrected.
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
      organisations={await organisationSnapshot(
        requestHeaders,
        session.session.activeOrganizationId ?? null
      )}
    >
      {children}
    </AppShell>
  )
}

/**
 * The organisations this session can switch between, and which one it is in.
 *
 * Wrapped in a `try` on purpose, and the reason is a specific failure worth naming: the organisation
 * tables arrive with a migration, so anybody who pulls this branch and starts the app before running
 * `pnpm --filter web auth:migrate` has a database where this query cannot succeed. That must not
 * blank out the entire application — the rail falls back to the wordmark and every screen behind it
 * keeps working, which is a far better failure than a stack trace on `/`.
 *
 * `activeId` is passed in rather than re-read. It is the plugin's own field on the session row, added
 * there by `organization()` in `lib/auth.ts`, and the caller already has the session in hand — asking
 * for it again would be a second query for a value that is one property away.
 */
async function organisationSnapshot(
  requestHeaders: Headers,
  activeId: string | null
): Promise<OrganisationSnapshot> {
  try {
    const organisations = await getAuth().api.listOrganizations({
      headers: requestHeaders,
    })

    return {
      items: organisations.map((organisation) => ({
        id: organisation.id,
        name: organisation.name,
        meta: organisation.slug,
      })),
      activeId,
    }
  } catch {
    return { items: [], activeId: null }
  }
}
