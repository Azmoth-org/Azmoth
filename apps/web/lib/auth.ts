/**
 * The Better Auth instance. **Server-only — never imported by a client component.**
 *
 * This is the identity the whole application hangs off: the middleware gates on the cookie it
 * issues, `(app)/layout.tsx` resolves the session it describes, and `lib/engine.ts` forwards the
 * resulting `user.id` to the engine so an audit row can name a person instead of `anonymous`.
 *
 * ## What is enabled, and what is deliberately not
 *
 * **Email and password always; Google only where a deployment has configured it.** The password
 * flow is the one that must work everywhere, so it is unconditional. Google is registered only when
 * `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are both set — an OAuth button is a redirect to a
 * third party that then learns which practice is auditing invoices at what time, which is a real
 * disclosure to make on this application and therefore a per-deployment decision rather than a
 * default. `lib/auth-google.ts` holds that switch and the reasoning behind it, and the two auth
 * screens ask the same function, so the button appears exactly where the endpoint behind it does.
 *
 * No magic links, because they need an SMTP relay — a piece of infrastructure that does not exist
 * here yet and that would silently become a dependency of signing in.
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

import { authDatabase, optionalEnv } from "@/lib/auth-db"
import { googleCredentials } from "@/lib/auth-google"

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
  const configured = optionalEnv("BETTER_AUTH_SECRET")
  if (configured) return configured

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
  const google = googleCredentials()

  return betterAuth({
    database: authDatabase(),

    /**
     * Where the auth endpoints live, for the links Better Auth generates.
     *
     * Unset is fine for same-origin use, which is all this application does — every call to
     * `/api/auth/*` comes from the same host that served the page, and Better Auth then derives the
     * origin from the incoming request. It is read from the environment so a deployment behind a
     * proxy that terminates TLS on another hostname can state its public origin.
     *
     * **`optionalEnv`, not `process.env` directly, and the difference is not cosmetic.** Compose
     * passes an unset variable through as `""` (`BETTER_AUTH_URL: "${BETTER_AUTH_URL:-}"`), and an
     * empty string here is not the same as `undefined`: Better Auth takes it as a *configured* base
     * URL, derives `trustedOrigins` from it, and then rejects every request whose `Origin` header
     * does not match — which is every browser sign-in, since a browser always sends `Origin` on a
     * POST. The symptom is a login form answering `403 INVALID_ORIGIN` while `curl` (which sends no
     * `Origin`) works fine, and nothing about it points at an empty environment variable.
     */
    baseURL: optionalEnv("BETTER_AUTH_URL"),

    /**
     * The CSRF check: a state-changing request is accepted only if its `Origin` is the host the
     * browser actually addressed.
     *
     * Better Auth's default is to trust `baseURL` alone, and with `baseURL` unset it derives one
     * per request from `request.url`. That derivation is what breaks in a container: `next dev`
     * binds `0.0.0.0`, so `request.url` is `http://0.0.0.0:3000/…` while the browser's `Origin` is
     * `http://localhost:3000` — the two never match, and every sign-in answers `403 INVALID_ORIGIN`
     * while `curl` (which sends no `Origin`, so the check is skipped) works perfectly. The same
     * mismatch appears behind any proxy, and under any hostname a developer reaches the app by.
     *
     * `Host` is the right thing to compare against instead, and comparing it to `Origin` *is* the
     * classic same-origin CSRF check rather than a weakening of one. A browser sets both headers
     * itself and a page cannot forge either: a cross-site POST from `evil.example` carries
     * `Origin: https://evil.example` against our own `Host`, and is refused. A non-browser client
     * can set both to anything, which is irrelevant — CSRF is about a browser attaching the
     * victim's cookie to somebody else's request, and a client writing its own headers has no
     * cookie to attach.
     *
     * `x-forwarded-host` wins when present, because behind a proxy that is the host the browser
     * used and `Host` is the internal one. When the proxy does not say which scheme it terminated,
     * both are accepted for that exact host: guessing wrong would reject every request, and the
     * scheme is not what this check is protecting.
     *
     * A configured `BETTER_AUTH_URL` still applies on top of this — it is what a deployment states
     * when its public origin is not something the request headers can reveal.
     */
    trustedOrigins: (request?: Request) => {
      // Called without a request during initialisation, and once per request afterwards. An empty
      // list is the right answer to "which origins does this instance trust in the abstract": with
      // no request there is no host to compare against, and inventing one would trust it forever.
      const headers = request?.headers
      if (!headers) return []

      const host = headers.get("x-forwarded-host") ?? headers.get("host")
      if (!host) return []

      const proto = headers.get("x-forwarded-proto")
      return proto ? [`${proto}://${host}`] : [`https://${host}`, `http://${host}`]
    },

    secret: authSecret(),

    emailAndPassword: {
      enabled: true,
      /** 12, not Better Auth's default 8. See the module docstring. */
      minPasswordLength: 12,
      requireEmailVerification: false,
    },

    /**
     * Google, when this deployment has an OAuth client. `undefined` — not `{}` — when it does not,
     * so `/api/auth/sign-in/social` refuses `google` outright instead of half-answering with
     * credentials that are empty strings.
     *
     * ## The redirect URI Google must be told about
     *
     * Better Auth serves the callback at **`/api/auth/callback/google`**, and Google refuses any
     * `redirect_uri` that is not registered against the client character for character — scheme,
     * host, port and path. So every origin this application is reached by needs its own entry under
     * *Authorised redirect URIs* in the Google Cloud console:
     *
     *     http://localhost:3000/api/auth/callback/google      pnpm dev, and the Docker stack
     *     https://<deployment-host>/api/auth/callback/google  each deployed origin
     *
     * The path is Better Auth's and is not configurable here; what varies is the origin, which
     * Better Auth derives per request unless `BETTER_AUTH_URL` states it. A proxy that terminates
     * TLS on a different hostname than this process sees is exactly the case where that variable
     * has to be set — otherwise the `redirect_uri` sent to Google is the internal origin, which is
     * not the one registered, and the flow dies at Google with `redirect_uri_mismatch`.
     *
     * ## Account linking is deliberately not loosened
     *
     * Somebody who registered with a password and later clicks "Mit Google anmelden" at the same
     * address is **not** signed in: Better Auth refuses to attach a Google identity to a local user
     * whose own email address was never verified, and redirects to `?error=account_not_linked`.
     * That looks like a bug and is the correct behaviour. `requireEmailVerification` is off here
     * (there is no mail transport — see above), so *every* password account in this database has
     * `emailVerified: false`, and relaxing the gate would mean anyone who registers an account at a
     * colleague's address gets handed that colleague's Google identity the first time they sign in.
     * `components/auth/auth-messages.ts` turns that redirect into a sentence that says to use the
     * password instead, which is the honest answer until there is an SMTP relay to verify with.
     */
    socialProviders: google
      ? {
          google: {
            clientId: google.clientId,
            clientSecret: google.clientSecret,
            /**
             * Always ask which account, rather than silently reusing whichever Google session the
             * browser already has. A reviewer signing in to a clinical tool from a machine with a
             * personal Google account logged in is the common case, and the default — straight
             * through, no prompt — is how the audit log ends up naming the wrong person.
             */
            prompt: "select_account",
          },
        }
      : undefined,

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
