/**
 * `GET /api/onboarding/resume?next=…` — refill the onboarding cookie from the database.
 *
 * The one piece that keeps `middleware.ts`'s cookie check honest. That check is optimistic by
 * necessity — middleware has no database — so a session whose practice details are *already stored*
 * but whose browser has never held the cookie looks exactly like a session that never onboarded.
 * That is not a hypothetical: it is the second device, the other browser, the cleared site data,
 * and the week-old cookie that expired alongside its session. Without this route, every one of
 * those marches a practice back through a form containing their own data.
 *
 * So `app/onboarding/page.tsx` asks the database, and when the answer is "already complete" it
 * redirects here. This sets the cookie and sends the reader where they were originally going. No
 * page renders in between, so there is no flash of a form nobody needed to see.
 *
 * **It re-derives the fact rather than taking anyone's word for it.** The cookie is issued only
 * after `readOnboarding` says both rows exist, for the session resolved out of the request. A
 * request to this URL from somebody who has *not* onboarded gets no cookie and a redirect to the
 * form — which is why it is safe for this to be a plain `GET` anyone can navigate to.
 *
 * `next` is validated by `safeNext` for the same reason `/login` validates it: it arrives in a URL,
 * so it is attacker-controlled, and a redirect that would leave this origin is the classic way to
 * make a phishing link look like it came from the application itself.
 *
 * ## Why the redirects are relative, and not `NextResponse.redirect`
 *
 * That helper needs an absolute URL, and the only one available in a route handler is built from
 * `request.url` — which inside a container is the address the *server* bound, not the one the
 * browser typed. `next dev` binds `0.0.0.0`, so the reader would be sent to `http://0.0.0.0:3000/`
 * and the flow would die there; behind a proxy it would be the internal hostname instead. It is the
 * same mismatch `trustedOrigins` in `lib/auth.ts` exists to work around, arriving from the other
 * direction.
 *
 * A relative `Location` sidesteps the question entirely: RFC 7231 has allowed a relative reference
 * since 2014, every browser resolves it against the URL it actually requested, and there is then no
 * origin for this handler to guess wrong. `middleware.ts` has no such problem — `request.nextUrl`
 * there is derived from the browser's own `Host` — which is why it still builds absolute URLs.
 */

import { NextResponse } from "next/server"

import { safeNext } from "@/lib/auth-redirect"
import { setOnboardingCookie } from "@/lib/onboarding/cookie"
import { readOnboarding } from "@/lib/onboarding/store"
import { currentSession } from "@/lib/session"

export const dynamic = "force-dynamic"

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url)
  const destination = safeNext(url.searchParams.get("next"))

  const session = await currentSession()
  if (!session) {
    // No session at all: `/login` rather than `/onboarding`, which would only bounce them here.
    return seeOther("/login")
  }

  const state = await readOnboarding(
    session.user.id,
    session.session.activeOrganizationId ?? null
  )

  if (!state.complete) {
    // Nothing to resume. Back to the form, without a cookie that would say otherwise.
    return seeOther("/onboarding")
  }

  return setOnboardingCookie(seeOther(destination))
}

/**
 * A redirect to a same-origin path, without naming the origin. See the note above.
 *
 * 303 rather than 307: this is a `GET` either way, and 303 is the status that means "the answer to
 * your question is over there" rather than "repeat what you did against a new URL". It is also the
 * one a browser will not offer to re-submit.
 */
function seeOther(path: string): NextResponse {
  return new NextResponse(null, { status: 303, headers: { Location: path } })
}
