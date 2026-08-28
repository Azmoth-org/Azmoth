/**
 * The cookie that says this session has already entered its practice details.
 *
 * ## What it is for, and what it is emphatically not
 *
 * `middleware.ts` runs on every request and has no database — it cannot ask whether a row exists in
 * `doctor_profiles` any more than it can verify a session token. So the onboarding gate uses the
 * same shape as the session gate one line above it: **an optimistic cookie check in the middleware,
 * and the authoritative answer somewhere that can query.** Here that somewhere is
 * `app/onboarding/page.tsx`, which reads both tables directly and either renders the form or, for a
 * session whose profile is already complete, re-issues this cookie and sends the reader on.
 *
 * That second half is what makes the cookie safe to trust. Without it the cookie would be the only
 * record of a fact that actually lives in the database, and the first time somebody signed in on a
 * second device — new browser, no cookie, complete profile — they would be marched through
 * onboarding again with all their own data already in it. The cookie is a *cache* of a database
 * fact, and `/api/onboarding/resume` is how a cold cache refills itself.
 *
 * **It is not a security boundary and must never become one.** Onboarding gates nothing: a session
 * that skipped it can reach exactly what a session that completed it can, and the only thing a
 * forged `onboarding_complete=1` buys is not having typed your own LANR. Anything that genuinely
 * has to be true before a request is served belongs in a route handler with the database in front
 * of it — the way `lib/engine.ts` resolves the session rather than trusting the middleware ran.
 *
 * `httpOnly`, even so. No client code reads this, only the middleware does, and a cookie that
 * scripts cannot touch is one fewer thing an XSS on any page of this application can flip.
 */

import type { NextResponse } from "next/server"

/** The name, in one place, because the middleware and two route handlers all have to agree on it. */
export const ONBOARDING_COOKIE = "onboarding_complete"

/**
 * Seven days — deliberately the same as `session.expiresIn` in `lib/auth.ts`.
 *
 * A cookie that outlived the session would be a stale answer waiting for the next person to sign in
 * on this browser; one that expired sooner would send somebody mid-week back through a form they
 * have already filled in. Matching the session means the two go stale together, and the resume
 * route re-issues it on the next sign-in either way.
 */
const MAX_AGE_SECONDS = 60 * 60 * 24 * 7

/**
 * Mark this browser as onboarded.
 *
 * `secure` follows `NODE_ENV` rather than being inferred, for the same reason `useSecureCookies`
 * does in `lib/auth.ts`: a proxy that speaks plain HTTP to the container would otherwise be handed
 * a cookie the browser is willing to send over plain HTTP too.
 */
export function setOnboardingCookie(response: NextResponse): NextResponse {
  response.cookies.set({
    name: ONBOARDING_COOKIE,
    value: "1",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  })
  return response
}

/**
 * Forget it — called by the middleware on any request that arrives without a session.
 *
 * Sign-out is the case that matters. Better Auth clears its own cookie and knows nothing about this
 * one, so without this the next person to sign in on a shared machine would inherit the previous
 * user's "already onboarded" answer and land on a dashboard belonging to a practice they have not
 * entered. Clearing it costs a `Set-Cookie` on requests that are already redirecting to `/login`.
 */
export function clearOnboardingCookie(response: NextResponse): NextResponse {
  response.cookies.set({
    name: ONBOARDING_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  })
  return response
}
