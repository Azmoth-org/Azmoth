/**
 * Whether "Mit Google anmelden" exists on this deployment, and the credentials behind it.
 * **Server-only** — the secret is read here and must never reach a bundle sent to a browser.
 *
 * Split out of `lib/auth.ts` so the *question* ("is the button there?") can be asked by the two
 * auth screens without importing the Better Auth instance, which opens the accounts database on
 * first use. A login page that connected to Postgres in order to decide whether to render a button
 * would be a database round-trip in front of the one screen that has to work when things are
 * broken.
 *
 * ## Configured, absent, and half-configured
 *
 * Google sign-in is **opt-in and off by default.** Nothing about this application needs it — email
 * and password stand on their own — and a deployment that has not registered an OAuth client
 * should not show a button that leads to a Google error page. So `GOOGLE_CLIENT_ID` and
 * `GOOGLE_CLIENT_SECRET` being unset is a supported state, not a misconfiguration: the provider is
 * not registered, and neither screen offers it.
 *
 * **Half-configured warns and counts as absent, rather than throwing.** One of the two set is
 * plainly a mistake, and the tempting response is to refuse to start. That would be the wrong
 * trade here: `getAuth()` builds the instance every session lookup goes through, so throwing on a
 * typo in an *optional* setting would take the whole application down — including the email and
 * password sign-in that has nothing to do with Google. What happens instead is that the button is
 * absent and the reason is on stderr, which is a legible failure rather than a silent one.
 *
 * ## Privacy, because this is not a neutral button
 *
 * Sending a reviewer to `accounts.google.com` tells Google that this person signed in to this
 * deployment at this moment. That is a real disclosure on a tool used to audit medical invoices,
 * even though no patient data crosses the boundary and Google is told nothing about what is being
 * reviewed. It is the reason this is a per-deployment switch and not a default: a practice that
 * runs on Google Workspace already has that relationship and gains a real thing — no eighth
 * password, and accounts that end when the Workspace account does. One that does not should leave
 * both variables unset and never see the button.
 */

import { optionalEnv } from "@/lib/auth-db"

/** The pair Better Auth's `socialProviders.google` needs. Both halves, or nothing. */
export type GoogleCredentials = {
  clientId: string
  clientSecret: string
}

/**
 * The configured Google OAuth client, or `undefined` when this deployment has none.
 *
 * `optionalEnv`, not `process.env` directly: compose passes an unset variable through as an empty
 * string, and an empty client id is "not configured" rather than "configured as nothing" — see the
 * note on that helper in `lib/auth-db.ts` for what the difference costs elsewhere.
 */
export function googleCredentials(): GoogleCredentials | undefined {
  const clientId = optionalEnv("GOOGLE_CLIENT_ID")
  const clientSecret = optionalEnv("GOOGLE_CLIENT_SECRET")

  if (clientId && clientSecret) return { clientId, clientSecret }

  if (clientId || clientSecret)
    warnOnce(clientId ? "GOOGLE_CLIENT_SECRET" : "GOOGLE_CLIENT_ID")
  return undefined
}

/**
 * Say it once per process, however many times the question is asked.
 *
 * This function is called on every render of either auth screen *and* whenever the Better Auth
 * instance is built, so an unguarded `console.warn` would print the same line on every page view.
 * A configuration warning that repeats is a configuration warning that gets filtered out of the
 * logs, which defeats the only thing it is here to do.
 */
let warned = false

function warnOnce(missing: string): void {
  if (warned) return
  warned = true
  console.warn(
    `Google sign-in is disabled: ${missing} is not set, and both halves are required. The button ` +
      "will not be shown and email/password sign-in is unaffected. See apps/web/.env.example."
  )
}

/**
 * Whether the two auth screens should offer Google.
 *
 * The same question `buildAuth` answers when it decides whether to register the provider, asked
 * from the same environment in the same process — so the button is shown exactly when the endpoint
 * behind it exists. Deriving it from anything else (a public flag, a build-time constant) is how a
 * button comes to point at a provider the server never registered.
 */
export function googleSignInEnabled(): boolean {
  return googleCredentials() !== undefined
}
