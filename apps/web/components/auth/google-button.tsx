"use client"

import * as React from "react"

import { Alert, AlertDescription } from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"

import {
  NETWORK_ERROR_MESSAGE,
  authErrorMessage,
} from "@/components/auth/auth-messages"
import { authClient } from "@/lib/auth-client"

/**
 * "Mit Google anmelden" — the whole OAuth flow, from one button.
 *
 * Rendered only where the server registered the provider: both auth pages ask
 * `googleSignInEnabled()` and omit this component otherwise, so the button never points at an
 * endpoint that would answer `PROVIDER_NOT_FOUND`. See `lib/auth-google.ts`.
 *
 * ## Two different failures, in two different places
 *
 * `signIn.social` does not sign anybody in. It asks our own server for Google's authorisation URL
 * and the client redirects the browser there; everything after that happens at Google and comes
 * back to `/api/auth/callback/google`, which is a *server* round-trip this component never sees.
 *
 * So the alert below covers only the first half — the request that asks for the URL, which fails
 * when the server is unreachable or has no such provider. The second half fails by redirecting to
 * `errorCallbackURL` with `?error=<code>`, and the page reads that parameter and renders it at the
 * top of the card. Both are needed; neither can report the other's failure.
 *
 * ## `pending` is never released on success
 *
 * Better Auth's client sets `window.location.href` itself once the URL comes back, so a successful
 * click ends in a full-page navigation to Google. Clearing the spinner here would put the label
 * back for the frames before the browser leaves, which reads as a button that did nothing.
 */
export function GoogleButton({
  label,
  callbackURL,
  errorCallbackURL,
}: {
  /** "Mit Google anmelden" on `/login`, "Mit Google registrieren" on `/signup`. */
  label: string
  /** Where Google's callback lands on success — the screen the reader was headed for. */
  callbackURL: string
  /** Where it lands on failure, with `?error=<code>` appended. The screen they came from. */
  errorCallbackURL: string
}) {
  const [error, setError] = React.useState<string | null>(null)
  const [pending, setPending] = React.useState(false)

  async function start() {
    if (pending) return
    setError(null)
    setPending(true)
    try {
      const { error: failure } = await authClient.signIn.social({
        provider: "google",
        callbackURL,
        errorCallbackURL,
      })
      if (failure) {
        setError(authErrorMessage(failure))
        setPending(false)
      }
    } catch {
      setError(NETWORK_ERROR_MESSAGE)
      setPending(false)
    }
  }

  return (
    <div className="space-y-4">
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Button
        type="button"
        variant="outline"
        className="w-full"
        onClick={start}
        disabled={pending}
      >
        <GoogleMark />
        {pending ? "Weiterleitung zu Google…" : label}
      </Button>
    </div>
  )
}

/**
 * Google's four-colour G.
 *
 * Inline rather than a Lucide glyph, and the colours are literals rather than tokens. Google's
 * brand guidelines for "Sign in with Google" require their mark, not an approximation — Lucide's
 * `Chrome` is a different product's logo and monochrome besides. The same reasoning keeps the fills
 * fixed across light and dark: a brand mark that recolours with the theme is no longer the mark,
 * and the shape is legible on both grounds because none of the four colours is near either one.
 *
 * `aria-hidden`, because the button's own text already says Google; announcing it twice is noise.
 */
function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        fill="#4285F4"
        d="M23.49 12.27c0-.79-.07-1.54-.19-2.27H12v4.51h6.47a5.53 5.53 0 0 1-2.4 3.58v3h3.86c2.26-2.09 3.56-5.17 3.56-8.82Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09A11.99 11.99 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.27 14.29a7.2 7.2 0 0 1 0-4.58V6.62H1.29a12 12 0 0 0 0 10.76l3.98-3.09Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.98 3.09C6.22 6.86 8.87 4.75 12 4.75Z"
      />
    </svg>
  )
}
