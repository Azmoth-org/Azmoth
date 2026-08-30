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
 * **Sign-up is gated by an allowlist, and closed by default.** `SIGNUP_ALLOWLIST` names the
 * addresses and domains that may register; unset means nobody may, except in development. The
 * check runs in the `user.create.before` hook below so it applies to *every* way an account can
 * come into existence — the password form and a Google sign-in alike — rather than to the one
 * screen somebody remembered to guard. `lib/auth-allowlist.ts` holds the rule and the reasoning.
 *
 * What that does not do is create roles. Every account admitted still has every permission inside
 * its own practice; a reviewer and an administrator are the same thing. That gap is deliberate for
 * a named pilot and is tracked in `docs/compliance/PRIVATE_DATA_WARNING.md` alongside retention.
 *
 * **Organisations are on, and they now authorise as well as identify.** The `organization()` plugin
 * below gives a session an active practice, the sidebar shows and switches it, and `lib/engine.ts`
 * forwards it to the engine on every call — which filters every proposal and every batch by it. See
 * the note on the plugin itself for what that boundary does and does not cover.
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
import { APIError } from "better-auth/api"
import { nextCookies } from "better-auth/next-js"
import { organization } from "better-auth/plugins"

import {
  SIGNUP_REFUSED_CODE,
  SIGNUP_REFUSED_MESSAGE,
  mayRegister,
} from "@/lib/auth-allowlist"
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
        "put it in the deployment's secret store — never in a committed file."
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
      return proto
        ? [`${proto}://${host}`]
        : [`https://${host}`, `http://${host}`]
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

    /**
     * Which organisation a new session starts in.
     *
     * The organization plugin does not choose one. It stores `activeOrganizationId` on the session
     * and leaves it `null` until something calls `/organization/set-active`, which means a reviewer
     * who belongs to exactly one practice would sign in to a rail reading "Keine Organisation" and
     * have to pick the only option there is. This picks it for them, at the one moment where it can
     * be done without a client round-trip and a visible correction.
     *
     * The earliest membership, not an arbitrary one. `findMany` with no `sortBy` returns whatever
     * order the database felt like, so on an account in two organisations the rail would open on a
     * different one depending on the query plan. Ordering by `createdAt` makes it the first
     * organisation the account joined, every time.
     *
     * A failure here must not cost anybody a sign-in — the active organisation is a piece of UI
     * state, and this database has none of these tables until `auth:migrate` has run. So the query
     * is wrapped: on any error the session is created exactly as it would have been without this
     * hook, and the reader picks an organisation from the menu instead.
     */
    databaseHooks: {
      /**
       * The sign-up gate. Refuses an account whose address is not on `SIGNUP_ALLOWLIST`.
       *
       * **Here rather than on the sign-up route**, and the difference is the whole point: this hook
       * runs on every path that creates a user row, so a Google sign-in by a stranger is refused by
       * the same three lines that refuse a password registration. A check written into the form —
       * or into `/api/auth/sign-up/email` — would guard one of the two doors and leave the other
       * open the day social sign-in is switched on, which is exactly the shape of bug that gets
       * found by the person who walks through it.
       *
       * `APIError` rather than returning `false`: Better Auth turns it into a 403 whose body the
       * sign-up form already renders, so the visitor gets a sentence instead of a generic failure.
       *
       * The refusal reason is logged and not sent. A stranger must not be able to tell an
       * unconfigured deployment from an address that is merely not listed — see
       * `SIGNUP_REFUSED_MESSAGE`.
       */
      user: {
        create: {
          before: async (user) => {
            const decision = mayRegister(user.email)
            if (decision.allowed) return

            console.warn(
              `[signup] refused ${user.email}: ${decision.reason}` +
                (decision.reason === "not_configured"
                  ? " — SIGNUP_ALLOWLIST is unset, so no account can be created in this deployment."
                  : "")
            )
            throw new APIError("FORBIDDEN", {
              code: SIGNUP_REFUSED_CODE,
              message: SIGNUP_REFUSED_MESSAGE,
            })
          },
        },
      },

      session: {
        create: {
          before: async (session, context) => {
            const adapter = context?.context.adapter
            if (!adapter) return

            try {
              const memberships = await adapter.findMany<{
                organizationId: string
              }>({
                model: "member",
                where: [{ field: "userId", value: session.userId }],
                sortBy: { field: "createdAt", direction: "asc" },
                limit: 1,
              })

              const organizationId = memberships[0]?.organizationId
              if (!organizationId) return

              return {
                data: { ...session, activeOrganizationId: organizationId },
              }
            } catch {
              // Most likely the organisation tables do not exist yet. Signing in still has to work.
              return
            }
          },
        },
      },
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

    plugins: [
      /**
       * Organisations — the practice a reviewer is working on behalf of.
       *
       * Better Auth's own plugin rather than anything hand-rolled, which matters more here than it
       * usually would: an organisation is the boundary a future "whose invoices may I see" check
       * will be drawn on, and the tables that boundary lives in should be the ones the library
       * maintains and migrates. It brings `organization`, `member` and `invitation`, and adds
       * `activeOrganizationId` to `session` — run `pnpm --filter web auth:migrate` after pulling
       * this, or the first sign-in reports a missing table.
       *
       * Defaults are kept deliberately. Any signed-in user may create an organisation and becomes
       * its `owner`; there is no limit and no invitation mail, because there is no SMTP relay to
       * send one with. Membership is therefore established by the creator today, and an invite flow
       * is the follow-on — see `docs/compliance/PRIVATE_DATA_WARNING.md`, which already tracks
       * closing the open sign-up this sits next to.
       *
       * **The organisation is now enforced, and it is worth being precise about where.** The
       * session's `activeOrganizationId` travels to the engine in `X-Organization-ID` on every call
       * `lib/engine.ts` proxies; `proposals.organization_id` and `batch_jobs.organization_id` exist
       * (Alembic `0006`), every read filters on the header and every write stamps it, and a request
       * that carries no organisation is refused with a `403`. One practice cannot list, open,
       * approve, reject or export another's records.
       *
       * What that does **not** cover, and should not be mistaken for: the engine does not verify the
       * header, so the boundary holds because this proxy is the engine's only caller and the engine
       * is not published to the browser — `apps/engine/app/api/tenancy.py` says so at length and is
       * the seam a verified Better Auth JWT goes into. Nor is there any *role* inside an
       * organisation: every member of a practice sees and decides everything that practice owns.
       * The boundary is between tenants, not within one.
       */
      organization(),

      /**
       * Lets a server action or a route handler set the session cookie on its own response.
       *
       * Without this the sign-in call succeeds, returns a session, and sets no cookie — the classic
       * "login worked but I am still logged out" failure in the App Router.
       *
       * Last in the list on purpose: `nextCookies` works by hooking every response on its way out,
       * so any plugin that sets a cookie of its own has to be registered before it.
       */
      nextCookies(),
    ],
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
