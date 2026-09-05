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
 *
 * ## The second gate: onboarding
 *
 * A session that has never entered its practice details is sent to `/onboarding`, and the check is
 * the same shape as the one above it — a cookie, because middleware has no database and cannot ask
 * whether a row exists in `doctor_profiles` any more than it can verify a session token.
 *
 * The two gates are not the same kind of thing, though, and the difference is worth being plain
 * about. The session check is a **security** boundary with an authoritative counterpart in
 * `app/(app)/layout.tsx`; this one is a **workflow** gate with no counterpart, because nothing is
 * protected by it. Onboarding data is what a practice puts on its own invoices: a forged
 * `onboarding_complete=1` buys the forger nothing except not having typed their own LANR. If that
 * ever stops being true — if some screen comes to *require* a stored BSNR — the check that enforces
 * it belongs in that screen with the database in front of it, not here.
 *
 * `lib/onboarding/cookie.ts` holds the cookie and the reasoning; `app/onboarding/page.tsx` is what
 * makes it self-correcting, by asking the database and re-issuing the cookie for a session that has
 * already onboarded on some other device.
 *
 * ## The third gate, and why it runs before the other two
 *
 * A per-IP budget on the endpoints that accept a credential — five POSTs a minute, then `429`.
 * `lib/rate-limit.ts` holds the counter and the reasoning about which address to trust;
 * `RATE_LIMITED_AUTH_PREFIXES` below holds the far more consequential decision about which paths
 * are counted, and specifically which are not.
 *
 * It is first in the function because the paths it guards are exactly the ones the session gate
 * lets through: `/api/auth` is in `PUBLIC_PREFIXES`, which returns early, so a limiter placed after
 * that check would never see a sign-in attempt at all.
 *
 * **In middleware rather than in Caddy**, which was a deliberate choice against the more obvious
 * one. Caddy has no rate limiting in its standard build — it needs `caddy-ratelimit`, which means
 * a custom image built with `xcaddy` and a second thing to rebuild on every Caddy release. This
 * file already runs on every request and already knows which paths are credential endpoints, and
 * distinguishing `/api/auth/sign-in` from `/api/auth/get-session` is the part that actually matters
 * here — a proxy-level rule over `/api/auth/*` would sign users out for using the app. What the
 * choice costs is stated in `lib/rate-limit.ts`: the count lives in one process's memory, so it
 * resets on deploy and does not span replicas.
 */

import { getSessionCookie } from "better-auth/cookies"
import { NextResponse, type NextRequest } from "next/server"

import {
  ONBOARDING_COOKIE,
  clearOnboardingCookie,
} from "@/lib/onboarding/cookie"
import { clientAddress, consume } from "@/lib/rate-limit"

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
  /**
   * The public demo, and the proxy routes behind it.
   *
   * This is the only *data* path in the application open to an anonymous visitor, so it is worth
   * saying exactly what it can reach. `/api/demo/*` proxies to two engine endpoints that take no
   * body, no query and no path parameter and audit one committed synthetic delivery — so no
   * request a visitor composes causes anything of theirs to be processed. That property, not this
   * list, is what makes the route publishable; see `apps/engine/app/api/demo.py`.
   *
   * The gated track is unaffected: `/padnext`, `/review` and every `/api/engine/*` route stay
   * behind the session, which is what keeps "look at the product" and "upload a document" two
   * different acts with two different front doors.
   */
  "/demo",
  "/api/demo",
] as const

/**
 * Paths a signed-in session reaches whether or not it has onboarded.
 *
 * Short, and every entry is here to stop a loop rather than to grant an exemption. `/onboarding` is
 * the destination — redirecting it to itself is an infinite redirect the browser reports as
 * `ERR_TOO_MANY_REDIRECTS` with nothing on screen to explain it. `/api/onboarding` is the endpoint
 * that form posts to and the resume route that issues the cookie: gating either behind the cookie
 * they exist to *set* is the same loop with a fetch in the middle, and it would present as a form
 * that silently fails to submit.
 *
 * `PUBLIC_PREFIXES` needs no entry here — those paths return before this check runs — but note that
 * `/api/auth` being among them is what keeps signing out possible for a session mid-onboarding.
 */
const ONBOARDING_EXEMPT_PREFIXES = ["/onboarding", "/api/onboarding"] as const

/**
 * The Better Auth paths that spend a rate-limit budget: the ones that take a credential.
 *
 * **Not all of `/api/auth/*`, and the exclusions are the load-bearing part of this list.** Better
 * Auth's client calls `/api/auth/get-session` on mount, on focus and on every session refresh, so a
 * blanket five-per-minute over the whole prefix would sign users out for browsing their own
 * dashboard — the limiter would present as an authentication bug, which is the worst possible
 * disguise for it. `/api/auth/sign-out` is excluded for a plainer reason: refusing to let somebody
 * sign out is a security regression, not a control.
 *
 * What is left is exactly the set an attacker submits guesses to. `sign-in` and `sign-up` are the
 * brief's login and signup; the two password-reset paths are here because they are the same shape
 * of thing — an unauthenticated POST whose response is an oracle about whether an address exists,
 * and the endpoint people forget when they harden the obvious two.
 *
 * Matched as prefixes because Better Auth namespaces by method: the email flow is
 * `/api/auth/sign-in/email` and the Google one is `/api/auth/sign-in/social`. Naming the parent
 * covers a provider added later, which is the direction a stale list should fail in.
 */
const RATE_LIMITED_AUTH_PREFIXES = [
  "/api/auth/sign-in",
  "/api/auth/sign-up",
  "/api/auth/forget-password",
  "/api/auth/reset-password",
] as const

function matchesPrefix(pathname: string, prefixes: readonly string[]): boolean {
  return prefixes.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  )
}

function isPublic(pathname: string): boolean {
  return matchesPrefix(pathname, PUBLIC_PREFIXES)
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl

  // Before every other gate, because the paths it guards are the ones that are *supposed* to be
  // reachable without a session — `PUBLIC_PREFIXES` returns early a few lines below, so anything
  // placed after that check would never see a sign-in attempt at all.
  const refusal = refuseIfOverAuthRateLimit(request, pathname)
  if (refusal) return refusal

  const hasSession = getSessionCookie(request) !== null

  if (isPublic(pathname)) {
    // Someone who is already signed in has no business on the login form; sending them to the
    // dashboard instead is what makes a bookmarked `/login` behave the way a reader expects.
    // Only the two screens, never `/api/auth/*` — bouncing the sign-out call would make signing
    // out impossible, and never `/demo`, which a signed-in reader has every reason to open: it is
    // what they show a colleague, and bouncing them to the dashboard would make it unreachable
    // from inside the product.
    if (hasSession && (pathname === "/login" || pathname === "/signup")) {
      return NextResponse.redirect(new URL("/", request.url))
    }
    // A public path reached without a session is the tail of a sign-out — Better Auth has just
    // cleared its own cookie and knows nothing about ours. Dropping it here is what stops the next
    // person to sign in on a shared machine inheriting the previous user's "already onboarded".
    return hasSession
      ? NextResponse.next()
      : forgetOnboarding(request, NextResponse.next())
  }

  if (!hasSession) {
    // An API route gets a 401, not a redirect. A `fetch` that follows a redirect to the login page
    // receives 200 and a body of HTML, which the caller parses as JSON and reports as "the engine
    // returned invalid JSON" — a wrong answer to a question that has a right one.
    if (pathname.startsWith("/api/")) {
      return forgetOnboarding(
        request,
        NextResponse.json(
          {
            error: "unauthenticated",
            message: "Nicht angemeldet. Bitte melden Sie sich erneut an.",
          },
          { status: 401 }
        )
      )
    }

    const login = new URL("/login", request.url)
    // Where they were going, so signing in resumes it instead of dumping everyone on the dashboard.
    // A path with its query, never an absolute URL: `/login` will only follow a same-site path.
    login.searchParams.set("next", `${pathname}${search}`)
    return forgetOnboarding(request, NextResponse.redirect(login))
  }

  // Signed in. The second gate: has this session said who it bills as?
  const onboarded = request.cookies.get(ONBOARDING_COOKIE)?.value === "1"
  if (onboarded || matchesPrefix(pathname, ONBOARDING_EXEMPT_PREFIXES)) {
    return NextResponse.next()
  }

  // Same reasoning as the 401 above, and the same reason it is not a redirect: an API caller wants
  // a status it can branch on, not the HTML of a form. 403 rather than 401 because the session is
  // perfectly valid — what is missing is a step, not a credential.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json(
      {
        error: "onboarding_required",
        message:
          "Bitte vervollständigen Sie zuerst Ihr Praxisprofil unter /onboarding.",
      },
      { status: 403 }
    )
  }

  const onboarding = new URL("/onboarding", request.url)
  // Carried for the same reason `/login` carries it, and consumed the same way: the form redirects
  // here on success, and `safeNext` refuses anything that is not a same-site path.
  onboarding.searchParams.set("next", `${pathname}${search}`)
  return NextResponse.redirect(onboarding)
}

/**
 * `429` when this address has spent its budget on a credential endpoint; `null` otherwise.
 *
 * Only counts `POST`. A `GET` on these paths is Better Auth's OAuth callback and a browser
 * navigation, and neither carries a guess — counting them would mean a user who reloads the login
 * page five times cannot then sign in.
 *
 * **A request with no proxy header is limited under a shared bucket rather than exempted.** In this
 * deployment every request arrives through Caddy, which always sets `X-Forwarded-For`, so a missing
 * header means either a direct connection to the container's port — which nothing outside the
 * compose network can open, since the port is not published — or a client that somehow stripped it.
 * Neither should be *safer* than coming in the front door. Lumping them into one bucket means the
 * worst case is that such callers share five attempts a minute between them, which is the right way
 * for this to fail: an anonymous attacker gets a stricter budget, never a free pass. The name
 * cannot collide with a real address because no address contains a space.
 */
function refuseIfOverAuthRateLimit(
  request: NextRequest,
  pathname: string
): NextResponse | null {
  if (request.method !== "POST") return null
  if (!matchesPrefix(pathname, RATE_LIMITED_AUTH_PREFIXES)) return null

  const address = clientAddress(request.headers) ?? "unknown source"
  const decision = consume(address)

  if (decision.allowed) return null

  const response = NextResponse.json(
    {
      error: "rate_limit_exceeded",
      message:
        "Zu viele Anmeldeversuche. Bitte warten Sie eine Minute und versuchen Sie es erneut. — " +
        "Too many sign-in attempts. Please wait a minute and try again.",
      retry_after: decision.retryAfterSeconds,
    },
    { status: 429 }
  )

  // `Retry-After` is what a well-behaved client and every browser devtools panel reads; the
  // `X-RateLimit-*` trio is what the engine's own limiter emits (`app/api/ratelimit.py`), and
  // matching it means one vocabulary across both tiers rather than two spellings of one idea.
  response.headers.set("Retry-After", String(decision.retryAfterSeconds))
  response.headers.set("X-RateLimit-Limit", String(decision.limit))
  response.headers.set("X-RateLimit-Remaining", "0")
  // No-store, or a shared cache in front of this could serve one client's refusal to another.
  response.headers.set("Cache-Control", "no-store")

  // The address is already in the access log of every proxy in front of this; what is not is the
  // fact that a threshold was crossed, which is the line worth alerting on. Deliberately not the
  // submitted email or any part of the body — middleware never reads it, and a log of attempted
  // usernames is a credential-adjacent artefact nobody wants to have retained.
  console.warn(
    `rate limit: ${address} refused on ${pathname} (${decision.limit}/min, retry in ${decision.retryAfterSeconds}s)`
  )

  return response
}

/** Drop the onboarding cookie on a response, but only when the browser actually sent one. */
function forgetOnboarding(
  request: NextRequest,
  response: NextResponse
): NextResponse {
  if (!request.cookies.has(ONBOARDING_COOKIE)) return response
  return clearOnboardingCookie(response)
}

/**
 * Files under `public/` that must be reachable without a session.
 *
 * These were being redirected to `/login`, and the symptom was specific: the brand mark was
 * **invisible on the login page and the demo**, because the CSS that paints it loads
 * `/brand/azmoth-mark.png` and an anonymous request for that asset got a `307` to `/login` instead
 * of a PNG. Every favicon and the web manifest had the same problem — a browser asking for
 * `/apple-touch-icon.png` before anyone has signed in was told to go and sign in.
 *
 * It was latent rather than new: the matcher below has always excluded only `favicon.ico`, so this
 * was true of any asset added to `public/`. It only became visible once `public/` held something a
 * page renders.
 *
 * **Excluded in the matcher rather than added to `PUBLIC_PREFIXES`**, so the middleware does not run
 * for them at all. That is the same argument the matcher's own comment makes about `_next/static`: a
 * function invocation per asset that protects nothing. It is also why this list is explicit rather
 * than a "anything with a file extension" pattern — a rule that un-gates every future path
 * containing a dot is a rule nobody will remember when they add one.
 *
 * Regex-escaped where it matters: a `.` is written `\\.` so `favicon.ico` cannot also match
 * `faviconXico`. It has to be **one string literal**: Turbopack parses `matcher` at compile time and
 * refuses a concatenation outright, which is a build failure rather than a subtle one.
 */
export const config = {
  /**
   * Everything except Next's own build output and the files under `public/`.
   *
   * `_next/static` and `_next/image` are build output and image optimisation — running middleware
   * on them costs a function invocation per asset and protects nothing. The brand and icon files
   * listed after them are `public/` assets for the same reason, and see the note above for the bug
   * that omitting them caused. Everything else, pages and API routes alike, goes through the
   * function above and is refused unless `PUBLIC_PREFIXES` names it.
   */
  // One literal, unwrapped and unjoined. Turbopack parses `matcher` at compile time and refuses a
  // concatenation with "Entry `matcher[0]` need to be static strings" — which is worth knowing
  // before reaching for a prettier line length.
  matcher: [
    "/((?!_next/static|_next/image|brand/|favicon\\.ico|favicon-96x96\\.png|apple-touch-icon\\.png|web-app-manifest-192x192\\.png|web-app-manifest-512x512\\.png|site\\.webmanifest|llms\\.txt).*)",
  ],
}
