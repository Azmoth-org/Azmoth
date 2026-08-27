"use client"

import { useRouter } from "next/navigation"
import Link from "next/link"
import * as React from "react"

import { Alert, AlertDescription } from "@workspace/ui/components/alert"
import { LoginForm as LoginFormTemplate } from "@workspace/ui/components/login-form"

import {
  NETWORK_ERROR_MESSAGE,
  authErrorMessage,
} from "@/components/auth/auth-messages"
import { authClient } from "@/lib/auth-client"

/**
 * Sign in with an email address and a password.
 *
 * The layout is `@workspace/ui`'s `LoginForm` template; everything below is what makes it this
 * application's sign-in — the German copy, the Better Auth call, and the two failures that have to
 * read differently. The template owns no words and no provider, so the Google button arrives here as
 * a slot rather than as the GitHub button the shadcn original shipped with.
 *
 * ## Uncontrolled fields, read from `FormData`
 *
 * The template's inputs carry `name` and no `value`, so this component holds no per-keystroke state.
 * Two fields do not need a reducer, and the version of this file that had one re-rendered the whole
 * form on every character typed into it.
 *
 * ## `router.refresh()` before the push, every time
 *
 * The screens behind `/login` are server components, and Next caches their rendered output per
 * route. Pushing straight to `next` after a successful sign-in can therefore land on a cached copy
 * rendered for whoever was signed in before — or on the redirect the middleware produced a moment
 * ago. `refresh()` discards that cache so the destination is rendered against the session that now
 * exists.
 *
 * ## The failure is a value, not a thrown error
 *
 * `authClient.signIn.email` resolves with `{ error }` rather than rejecting, so the `catch` below is
 * for the transport only — no network, DNS gone, the server not running. Those two cases read
 * differently to the person in front of the form ("your password is wrong" versus "we could not
 * ask"), which is why they produce different sentences.
 */
export function LoginForm({
  next,
  social,
  signupHref,
  alert,
}: {
  /** Where a successful sign-in lands. Already passed through `safeNext` by the page. */
  next: string
  /** The Google button, on deployments that have one. */
  social?: React.ReactNode
  /** `/signup`, carrying the same destination so the reader does not lose their place. */
  signupHref: string
  /** A failure from a previous render — the `?error=` an OAuth round-trip came back with. */
  alert?: React.ReactNode
}) {
  const router = useRouter()
  const [error, setError] = React.useState<string | null>(null)
  const [pending, setPending] = React.useState(false)

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return

    const form = new FormData(event.currentTarget)
    const email = String(form.get("email") ?? "").trim()
    const password = String(form.get("password") ?? "")

    setError(null)
    setPending(true)
    try {
      const { error: failure } = await authClient.signIn.email({
        email,
        password,
      })
      if (failure) {
        setError(authErrorMessage(failure))
        setPending(false)
        return
      }
      router.refresh()
      router.push(next)
      // `pending` stays true through the navigation on purpose: releasing it here puts the button
      // back to "Anmelden" for the moment before the new screen paints, which reads as a sign-in
      // that did nothing.
    } catch {
      setError(NETWORK_ERROR_MESSAGE)
      setPending(false)
    }
  }

  return (
    <LoginFormTemplate
      onSubmit={submit}
      noValidate
      pending={pending}
      title="Anmelden"
      description="Melden Sie sich mit Ihrer dienstlichen E-Mail-Adresse an."
      emailLabel="E-Mail"
      emailPlaceholder="name@praxis.de"
      passwordLabel="Passwort"
      submitLabel={pending ? "Wird angemeldet…" : "Anmelden"}
      separatorLabel="Oder fortfahren mit"
      social={social}
      alert={
        // The alert the page passed in (an OAuth round-trip that failed) and the one this form
        // produced (a wrong password) occupy the same slot, because they are the same thing to the
        // reader: the reason they are still on this screen.
        error ? (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : (
          alert
        )
      }
      footer={
        <>
          Noch kein Konto?{" "}
          <Link
            href={signupHref}
            className="font-medium text-foreground underline underline-offset-4"
          >
            Registrieren
          </Link>
        </>
      }
    />
  )
}
