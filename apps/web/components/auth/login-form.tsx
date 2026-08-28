"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import * as React from "react"

import { Alert, AlertDescription } from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldSeparator,
} from "@workspace/ui/components/field"
import { Input } from "@workspace/ui/components/input"

import {
  NETWORK_ERROR_MESSAGE,
  authErrorMessage,
} from "@/components/auth/auth-messages"
import { authClient } from "@/lib/auth-client"

/**
 * Sign in with an email address and a password.
 *
 * The layout is shadcn's `login-02` form, installed into this app rather than into `@workspace/ui`.
 * It lives here because it is not shared: every string in it is German, the provider is Google, and
 * the submit calls Better Auth. A copy in the shared package would be a component with one consumer
 * that no second app could adopt without first removing this app's language from it.
 *
 * Three things the block shipped are gone. Its GitHub button became the `social` slot, because
 * whether this deployment has a provider at all is a server-side question (`googleSignInEnabled()`)
 * and the page answers it. Its `href="#"` "Forgot your password?" link is not rendered, because
 * there is no reset flow to point it at and a dead link on a login form reads as a broken product.
 * Its English copy is replaced outright.
 *
 * ## Uncontrolled fields, read from `FormData`
 *
 * The inputs carry `name` and no `value`, so this component holds no per-keystroke state. Two
 * fields do not need a reducer, and the version of this file that had one re-rendered the whole
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
    <form className="flex flex-col gap-6" onSubmit={submit} noValidate>
      <FieldGroup>
        <div className="flex flex-col items-center gap-1 text-center">
          {/*
            An `<h1>`, not a `<div>`. On a screen whose entire content is one form, the form's name
            is the page's name, and a page with no level-1 heading gives a screen-reader user
            nothing to land on.
          */}
          <h1 className="text-2xl font-bold">Anmelden</h1>
          <p className="text-sm text-balance text-muted-foreground">
            Melden Sie sich mit Ihrer dienstlichen E-Mail-Adresse an.
          </p>
        </div>

        {/*
          The alert the page passed in (an OAuth round-trip that failed) and the one this form
          produced (a wrong password) occupy the same slot, because they are the same thing to the
          reader: the reason they are still on this screen.

          It sits above the fields rather than beside the button that caused it, because the failure
          it usually reports happened on a previous render — by the time it is read the button is no
          longer what the reader is looking at.
        */}
        {error ? (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : (
          alert
        )}

        <Field>
          <FieldLabel htmlFor="email">E-Mail</FieldLabel>
          <Input
            id="email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            // The cursor starts here. On a form of two fields that is the difference between typing
            // and reaching for the mouse first.
            autoFocus
            required
            placeholder="name@praxis.de"
            disabled={pending}
          />
        </Field>

        <Field>
          <FieldLabel htmlFor="password">Passwort</FieldLabel>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            disabled={pending}
          />
        </Field>

        <Field>
          <Button type="submit" disabled={pending}>
            {pending ? "Wird angemeldet…" : "Anmelden"}
          </Button>
        </Field>

        {social ? (
          <>
            <FieldSeparator>Oder fortfahren mit</FieldSeparator>
            <Field>{social}</Field>
          </>
        ) : null}

        <FieldDescription className="text-center">
          Noch kein Konto?{" "}
          <Link
            href={signupHref}
            className="font-medium text-foreground underline underline-offset-4"
          >
            Registrieren
          </Link>
        </FieldDescription>
      </FieldGroup>
    </form>
  )
}
