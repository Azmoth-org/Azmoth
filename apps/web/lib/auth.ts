/**
 * The Better Auth instance. **Server-only — never imported by a client component.**
 *
 * This is the identity the whole application hangs off: the middleware gates on the cookie it
 * issues, `(app)/layout.tsx` resolves the session it describes, and `lib/engine.ts` forwards the
 * resulting `user.id` to the engine so an audit row can name a person instead of `anonymous`.
 *
 * ## What is enabled, and what is deliberately not
 *
 * **Email and password only.** Google sign-in is disabled for the pilot — see the note on
 * `socialProviders` below for how it is turned off and what bringing it back involves.
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
import { jwt, organization } from "better-auth/plugins"

import {
  SIGNUP_REFUSED_CODE,
  SIGNUP_REFUSED_MESSAGE,
  mayRegister,
} from "@/lib/auth-allowlist"
import { authDatabase, optionalEnv } from "@/lib/auth-db"
import { organizationNameForEmail } from "@/lib/organization-name"
import { slugifyOrganizationName } from "@/lib/organization-slug"
// Google sign-in is disabled for the pilot — see `socialProviders` below.
// import { googleCredentials } from "@/lib/auth-google"

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
      /**
       * 12, not Better Auth's default 8. See the module docstring.
       *
       * The pilot's full policy also wants at least 3 of {lower, upper, digit, symbol} — this
       * installed version (1.7.1) has no character-class option on `emailAndPassword` to express
       * that with (only `minPasswordLength`/`maxPasswordLength` exist; see this package's
       * `EmailAndPasswordOptions` type). That half of the policy is therefore enforced client-side
       * instead, in `lib/password-policy.ts` — this length floor is what still holds if a request
       * bypasses the form entirely.
       */
      minPasswordLength: 12,
      /**
       * Email verification disabled for the pilot phase. There is no SMTP relay configured (see
       * the module docstring), so turning this on would create accounts nobody could ever use.
       * Admission is instead controlled server-side by `SIGNUP_ALLOWLIST` (`lib/auth-allowlist.ts`),
       * checked in the `user.create.before` hook below for every account-creation path. Enable this
       * once the pilot moves to paying customers with real inboxes — AWS SES is the obvious relay,
       * at roughly €0.10 per 1,000 emails.
       */
      requireEmailVerification: false,
    },

    /**
     * Google sign-in is disabled for the pilot phase — the pilot has no need for it, and every
     * account is admitted through `SIGNUP_ALLOWLIST` instead. `undefined` here (rather than reading
     * `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` and registering conditionally) makes
     * `/api/auth/sign-in/social` refuse `google` outright regardless of what a deployment's
     * environment happens to have set, so the door is closed in code rather than by convention.
     *
     * To bring this back: restore `googleCredentials()` from `lib/auth-google.ts` (see the `import`
     * commented out above), register it here as `google ? { google: { clientId, clientSecret,
     * prompt: "select_account" } } : undefined`, and re-enable the `GoogleButton` on the login and
     * signup pages. See git history on this file for the previous implementation, including the
     * redirect-URI and account-linking notes that applied to it.
     */
    socialProviders: undefined,

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

          /**
           * Every account gets a practice, at the moment the account exists.
           *
           * **This is what makes a new account usable at all.** `lib/engine.ts` refuses any
           * proxied call whose session carries no `activeOrganizationId` with a `403`, and the
           * engine refuses it again on its own side (`app/api/tenancy.py`) — so an account with no
           * organisation reached the dashboard and watched every panel fail, including
           * `/api/engine/rules/coverage`, which is the first thing the dashboard asks for. The
           * organisation was previously created by the sign-up *form*, which left every other way
           * an account can come into existence — a seeded account, a future invite, a social
           * sign-in the day one is enabled — with no practice and no route to one.
           *
           * **Here rather than on the sign-up route**, for exactly the reason the `before` hook
           * above gives: this runs on every path that creates a user row, so there is one place
           * that can be wrong rather than one per door.
           *
           * **No `headers`, and that is load-bearing.** `/organization/create` treats a call with
           * a request or headers but no session as unauthorised; a call with neither and a
           * `userId` in the body is its server-side path. There *is* no session here — the session
           * row is written after this hook returns, which is also why `session.create.before`
           * below then finds this membership and opens the rail on it.
           *
           * **A failure here must not cost anybody their account.** The user row is already
           * written by the time this runs, so throwing would leave a registered address that
           * cannot be registered again and cannot be signed in to usefully either. The two
           * realistic failures are a database without the organisation tables (`auth:migrate` not
           * run) and a slug collision that survived its retries; both are logged and swallowed, and
           * the reader lands on a rail reading "Keine Organisation" with a button that creates one
           * — which is exactly where they were before this hook existed.
           *
           * The name is a placeholder derived from the email domain, not a claim — see
           * `lib/organization-name.ts`. `/onboarding` renames this organisation rather than
           * creating a second one, and so does the sign-up form.
           */
          after: async (user) => {
            const name = organizationNameForEmail(user.email)
            try {
              await getAuth().api.createOrganization({
                body: {
                  name,
                  slug: slugifyOrganizationName(name),
                  userId: user.id,
                },
              })
            } catch (error) {
              console.warn(
                `[signup] could not create an organisation for ${user.email}: ${
                  error instanceof Error ? error.message : String(error)
                } — the account exists and can create one from the rail.`
              )
            }
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
       * Lets `lib/engine.ts` hand the engine a real, verifiable credential instead of the
       * asserted `X-User-ID` header it has always sent — see the long note in
       * `apps/engine/app/api/identity.py` about why that header is not authentication and what
       * the eventual fix was always going to be.
       *
       * Used for exactly one call today: `POST /api/v1/rules/{rule_id}/review`, which changes
       * platform-wide rule enforcement and is the one endpoint the engine now verifies itself
       * (`apps/engine/app/api/session_auth.py`). `getToken()` is called on every proxied request
       * regardless — see `requireIdentity()` below — because a per-route special case is a
       * special case somebody forgets; the engine simply ignores the header on endpoints that
       * do not declare the dependency.
       *
       * `issuer`/`audience` are fixed strings naming this exact pair of services, not derived
       * from `baseURL` (the plugin's default): `BETTER_AUTH_URL` is frequently unset in this
       * application — see the note on it above — and an empty-string issuer both sides
       * separately fell back to would be an implicit agreement neither side actually states.
       * `expirationTime` is minutes, not the session's own week: this token is minted fresh for
       * one proxied call and verified once, so there is no reason for a copy of it to be valid
       * any longer than the request it rides on.
       */
      jwt({
        jwt: {
          issuer: "azmoth-web",
          audience: "azmoth-engine",
          expirationTime: "2m",
        },
      }),

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
