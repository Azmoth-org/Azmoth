/**
 * Reading the current session on the server, and the redirect that follows from not having one.
 *
 * **This is the authoritative check.** `middleware.ts` also gates the protected routes, but it only
 * looks at whether a session cookie is *present* — it cannot verify one without a database, and
 * verifying one per request in the edge runtime is not something to build a security boundary out
 * of. So the middleware is a fast redirect for the common case, and this is the check that decides.
 * Anything that renders a proposal must call `requireSession`, not trust that the middleware ran.
 */

import { headers } from "next/headers"
import { redirect } from "next/navigation"

import { getAuth, type Session } from "@/lib/auth"

/** The signed-in user and their session, or `null`. Never throws for an anonymous request. */
export async function currentSession(): Promise<Session | null> {
  return await getAuth().api.getSession({ headers: await headers() })
}

/**
 * The signed-in user, or a redirect to `/login` carrying where they were going.
 *
 * `next` is a *path*, taken from the caller rather than from a header, and `/login` refuses
 * anything that is not a same-site path — an open redirect on a login page is the classic way to
 * make a phishing link look like it came from the application itself.
 */
export async function requireSession(next?: string): Promise<Session> {
  const session = await currentSession()
  if (session) return session

  const target = next && next.startsWith("/") ? `?next=${encodeURIComponent(next)}` : ""
  redirect(`/login${target}`)
}
