/**
 * The Better Auth instance. **Server-only — never imported by a client component.**
 *
 * This is the identity the whole application hangs off: the middleware gates on the cookie it
 * issues, `(app)/layout.tsx` resolves the session it describes, and `lib/engine.ts` forwards the
 * resulting `user.id` to the engine so an audit row can name a person instead of `anonymous`.
 *
 * ## What is enabled, and what is deliberately not
 *
 * **Email and password, and nothing else.** No social provider, because there is no organisation
 * behind this build to federate with, and an OAuth button is a redirect to a third party that would
 * then learn which practice is auditing invoices. No magic links, because they need an SMTP
 * relay — a piece of infrastructure that does not exist here yet and that would silently become a
 * dependency of signing in.
 *
 * **`requireEmailVerification` is off.** It is the right setting for a public sign-up and the wrong
 * one here: with no mail transport configured, turning it on would create accounts nobody could
 * ever use. What *is* on is the password floor — Better Auth's default minimum is 8, and 12 is the
 * BSI's recommendation for an account that reaches clinical data.
 *
 * **Sign-up is open, and that is a gap rather than a decision.** Anyone who can reach `/signup` can
 * make an account. That is acceptable for a build that holds only synthetic data and is not
 * acceptable for one that holds real records; an invite-only flow (or an SSO integration) is what
 * `docs/compliance/PRIVATE_DATA_WARNING.md` now tracks alongside the retention policy.
 *
 * ## Session length
 *
 * Seven days, refreshed a day at a time. A reviewer works in this application daily, so a short
 * absolute expiry would sign them out mid-review for no security gain; `updateAge` is what keeps an
 * active session alive without ever extending an abandoned one past a week.
 *
 * `cookieCache` is off. It trades a database round-trip per request for a session that stays valid
 * for its cache window *after* it was revoked — and revocation is the one thing a sign-out has to
 * mean on a service holding clinical data.
 *
 * ## Why this is a function and not a `const`
 *
 * Building the instance opens the accounts database, and `authSecret()` refuses to run in
 * production without a secret. Doing either at module scope means `next build` does it: the build
 * imports every route to collect its page data, and a container image is built long before it is
 * handed the deployment's secrets. So the instance is built on first *use* and memoised —
 * `getAuth()` from a request is where the connection appears, which is also the point at which a
 * misconfiguration should be reported.
 */

import { betterAuth } from "better-auth"
import { nextCookies } from "better-auth/next-js"

import { authDatabase } from "@/lib/auth-db"

/**
 * The key every session cookie and every password reset token is signed with.
 *
 * Required in production and refused if absent, rather than defaulted: a generated-per-boot secret
 * signs sessions that the next container cannot verify, which presents as "everyone is randomly
 * logged out" and is diagnosed as anything but a missing environment variable. In development it
 * falls back to a fixed, obviously-fake string — committed on purpose, because a value in a public
 * repository is not a secret and pretending otherwise is worse than saying so.
 */
function authSecret(): string {
  const configured = process.env.BETTER_AUTH_SECRET
  if (configured && configured.length > 0) return configured

  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "BETTER_AUTH_SECRET is not set. It signs the session cookies, so a missing value means " +
        "every deploy invalidates every session. Generate one with `openssl rand -base64 32` and " +
        "put it in the deployment's secret store — never in a committed file.",
    )
  }
  return "development-only-secret-not-for-any-deployment"
}

function buildAuth() {
  return betterAuth({
    database: authDatabase(),

    /**
     * Where the auth endpoints live, for the links Better Auth generates.
     *
     * Unset is fine for same-origin use, which is all this application does — every call to
     * `/api/auth/*` comes from the same host that served the page. It is read from the environment
     * so a deployment behind a proxy that terminates TLS on another hostname can state its origin.
     */
    baseURL: process.env.BETTER_AUTH_URL,

    secret: authSecret(),

    emailAndPassword: {
      enabled: true,
      /** 12, not Better Auth's default 8. See the module docstring. */
      minPasswordLength: 12,
      requireEmailVerification: false,
    },

    session: {
      expiresIn: 60 * 60 * 24 * 7,
      updateAge: 60 * 60 * 24,
    },

    advanced: {
      /**
       * `Secure` on the session cookie whenever this is a real deployment.
       *
       * Better Auth infers this from `baseURL`, which is unset for same-origin use — so it is
       * stated here instead. Without it a proxy that speaks plain HTTP to the container would be
       * handed a cookie the browser is willing to send over plain HTTP too.
       */
      useSecureCookies: process.env.NODE_ENV === "production",
    },

    /**
     * Lets a server action or a route handler set the session cookie on its own response.
     *
     * Without this the sign-in call succeeds, returns a session, and sets no cookie — the classic
     * "login worked but I am still logged out" failure in the App Router.
     */
    plugins: [nextCookies()],
  })
}

/** Built once per process, on the first request that needs it. See the note above. */
let instance: ReturnType<typeof buildAuth> | null = null

/** The Better Auth instance. Server-only; every caller is a route handler or a server component. */
export function getAuth(): ReturnType<typeof buildAuth> {
  instance ??= buildAuth()
  return instance
}

/** The session object the rest of the application passes around. */
export type Session = ReturnType<typeof buildAuth>["$Infer"]["Session"]
