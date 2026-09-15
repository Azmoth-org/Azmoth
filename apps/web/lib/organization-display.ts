/**
 * The signed-in practice's *name*, for a document that has to print one.
 *
 * Separate from `requireIdentity()` in `lib/engine.ts`, and deliberately not folded into it. That
 * function resolves what the engine *authorises* on — the user id and the tenant id — and it runs on
 * every proxied call. This is display text for the two or three routes that render a document, it
 * costs a query, and a value nothing filters or stores should not be on the hot path of everything.
 *
 * Returns `null` rather than a placeholder whenever the name cannot be established: no session, no
 * active organisation, the organisation tables not migrated yet, or a name that is empty once
 * trimmed. The engine already has a fallback for each of those (`organization_label` prints a
 * neutral label from the id), so inventing one here would mean two places deciding what an unknown
 * practice is called.
 */

import { headers as nextHeaders } from "next/headers"

import { getAuth } from "@/lib/auth"

/** The practice name for the current session, or `null` when there is nothing certain to print. */
export async function activeOrganizationName(): Promise<string | null> {
  try {
    const requestHeaders = await nextHeaders()
    const session = await getAuth().api.getSession({ headers: requestHeaders })

    const activeId = session?.session.activeOrganizationId
    if (!activeId) return null

    // `listOrganizations` rather than `getFullOrganization`: this is the membership list, so an
    // organisation the session is *not* a member of cannot be resolved through it whatever the
    // session's `activeOrganizationId` happens to say. The list is short — a pilot account belongs
    // to one practice — and the alternative would trust a stale id to name a real organisation.
    const organisations = await getAuth().api.listOrganizations({
      headers: requestHeaders,
    })

    const active = organisations.find(
      (organisation) => organisation.id === activeId
    )
    const name = active?.name?.trim()
    return name ? name : null
  } catch {
    // Most likely the organisation tables do not exist yet — the same condition `(app)/layout.tsx`
    // swallows around its own `listOrganizations`. A report that prints the id-derived label is a
    // far better outcome than a download that fails.
    return null
  }
}
