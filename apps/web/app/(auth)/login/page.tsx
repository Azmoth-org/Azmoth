import type { Metadata } from "next"

import { Alert, AlertDescription } from "@workspace/ui/components/alert"

import { AuthShell } from "@/components/auth/auth-shell"
import { oauthErrorMessage } from "@/components/auth/auth-messages"
import { GoogleButton } from "@/components/auth/google-button"
import { LoginForm } from "@/components/auth/login-form"
import { safeNext } from "@/lib/auth-redirect"
import { googleSignInEnabled } from "@/lib/auth-google"

export const metadata: Metadata = {
  title: "Anmelden",
  description:
    "Anmeldung zur GOÄ-Prüfung. Interne Anwendung, nur synthetische Daten.",
}

/**
 * The way in.
 *
 * `next` is the screen the middleware interrupted, and it is passed through `safeNext` before it
 * reaches the form — a login page that will redirect anywhere is how a phishing link comes to be
 * served from the application's own domain. Anything that is not a same-site path becomes `/`.
 *
 * `error` is the other query parameter, and it arrives from a different direction: a Google sign-in
 * that failed comes *back* here as a redirect with `?error=<code>` rather than as a response some
 * component could catch. It is looked up in a fixed table and never rendered as itself — the value
 * is partly Google's and entirely attacker-reachable, and a login screen that echoes a string from
 * its own URL is a phishing surface.
 *
 * A server component holding a client form, rather than a client page: the title and the `robots`
 * metadata belong to the route, and there is nothing on this screen that needs the browser except
 * the inputs, the submit, and the Google button.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>
}) {
  const { next, error } = await searchParams
  const destination = safeNext(next)
  const failure = oauthErrorMessage(error)
  // The destination has to survive the trip to Google and back, and the only place to keep it is
  // the URL these two callbacks name — there is no session yet to hold it in.
  const back = `/login${next ? `?next=${encodeURIComponent(destination)}` : ""}`

  return (
    <AuthShell>
      <LoginForm
        next={destination}
        // The destination travels with the reader across the two screens, so a visitor who was sent
        // here from /review and turns out to need an account still lands on /review.
        signupHref={`/signup${next ? `?next=${encodeURIComponent(destination)}` : ""}`}
        alert={
          failure ? (
            <Alert variant="destructive" role="alert">
              <AlertDescription>{failure}</AlertDescription>
            </Alert>
          ) : null
        }
        social={
          googleSignInEnabled() ? (
            <GoogleButton
              label="Mit Google anmelden"
              callbackURL={destination}
              errorCallbackURL={back}
            />
          ) : null
        }
      />
    </AuthShell>
  )
}
