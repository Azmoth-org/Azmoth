/**
 * The gate in front of every screen. Signed out means `/login`, wherever you were going.
 *
 * ## What this check is, and what it is not
 *
 * It asks whether a Better Auth session cookie is **present**. It does not verify the cookie's
 * signature and does not look the session up, because middleware runs before the request reaches a
 * route that could — Better Auth's own guidance for the App Router is exactly this: an optimistic
 * cookie check here, and the real check in the page. So a forged cookie gets past this file and is
 * then rejected by `requireSession` in `app/(app)/layout.tsx`, which is the boundary that actually
 * decides. Removing either would be a mistake: without the middleware, a signed-out visitor renders
 * a whole layout before being sent away; without the layout check, a cookie called
 * `better-auth.session_token` with any value at all would be enough.
 *
 * ## Why a denylist of public paths rather than an allowlist of private ones
 *
 * `config.matcher` below excludes the static assets and nothing else, so a screen added tomorrow is
 * protected by default and has to be *named* to be public. The reverse — listing the seven
 * protected routes — is a list that goes stale the first time somebody adds an eighth, and the
 * failure mode is a screen full of clinical data served to anyone who finds its URL.
 *
 * `/api/engine/*` is inside the gate on purpose. Those handlers proxy to the FastAPI service and
 * forward the user id it records in its audit log; leaving them open would mean the UI is protected
 * and the data behind it is not.
 */

import { getSessionCookie } from "better-auth/cookies"
import { NextResponse, type NextRequest } from "next/server"

/**
 * Paths reachable without a session.
 *
 * `/api/auth` has to be here — signing in cannot require being signed in. `/api/health` has to be
 * here for a different reason: it is what the container's healthcheck calls, and a healthcheck that
 * needed a session would report every container as unhealthy forever.
 */
const PUBLIC_PREFIXES = [
  "/login",
  "/signup",
  "/api/auth",
  "/api/health",
] as const

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  )
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl

  const hasSession = getSessionCookie(request) !== null

  if (isPublic(pathname)) {
    // Someone who is already signed in has no business on the login form; sending them to the
    // dashboard instead is what makes a bookmarked `/login` behave the way a reader expects.
    // Only the two screens, never `/api/auth/*` — bouncing the sign-out call would make signing
    // out impossible.
    if (hasSession && (pathname === "/login" || pathname === "/signup")) {
      return NextResponse.redirect(new URL("/", request.url))
    }
    return NextResponse.next()
  }

  if (hasSession) return NextResponse.next()

  // An API route gets a 401, not a redirect. A `fetch` that follows a redirect to the login page
  // receives 200 and a body of HTML, which the caller parses as JSON and reports as "the engine
  // returned invalid JSON" — a wrong answer to a question that has a right one.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json(
      {
        error: "unauthenticated",
        message: "Nicht angemeldet. Bitte melden Sie sich erneut an.",
      },
      { status: 401 }
    )
  }

  const login = new URL("/login", request.url)
  // Where they were going, so signing in resumes it instead of dumping everyone on the dashboard.
  // A path with its query, never an absolute URL: `/login` will only follow a same-site path.
  login.searchParams.set("next", `${pathname}${search}`)
  return NextResponse.redirect(login)
}

export const config = {
  /**
   * Everything except Next's own assets and the favicon.
   *
   * `_next/static` and `_next/image` are build output and image optimisation — running middleware
   * on them costs a function invocation per asset and protects nothing. Everything else, pages and
   * API routes alike, goes through the function above and is refused unless `PUBLIC_PREFIXES` names
   * it.
   */
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
}
