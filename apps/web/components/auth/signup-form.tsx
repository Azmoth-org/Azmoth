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
 * The password floor, stated in three places that must not disagree.
 *
 * `lib/auth.ts` enforces it, the browser's own `minLength` rejects a short one without a
 * round-trip, and the sentence under the field says it before either fires. 12 rather than Better
 * Auth's default 8 — see the note in `lib/auth.ts`.
 */
const MIN_PASSWORD_LENGTH = 12

/**
 * Create an account.
 *
 * The layout is shadcn's `signup-02` form, installed into this app rather than into
 * `@workspace/ui`. See `components/auth/login-form.tsx` for why it lives here, why the fields are
 * uncontrolled, why `router.refresh()` precedes the push, and why a returned `{ error }` and a
 * thrown exception produce different sentences. All four apply identically.
 *
 * Four fields rather than the login screen's two, and the confirmation is the reason this is a
 * separate component rather than a `mode` prop on that one. It is also new with the block: the form
 * this replaced had a single password box, so a typo produced an account nobody could sign in to
 * and no way to find out why.
 *
 * The block's own field descriptions are replaced rather than kept. "We'll use this to contact you"
 * is untrue here — nothing mails this address — and "at least 8 characters" would contradict the
 * server. The name's description is the one that earns its place: it explains why a name is asked
 * for at all, which is that it ends up beside every approval in the audit trail.
 */
export function SignupForm({
  next,
  social,
  loginHref,
  alert,
}: {
  /** Where a successful registration lands. Already passed through `safeNext` by the page. */
  next: string
  /** The Google button, on deployments that have one. */
  social?: React.ReactNode
  /** `/login`, carrying the same destination so the reader does not lose their place. */
  loginHref: string
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
    const name = String(form.get("name") ?? "").trim()
    const email = String(form.get("email") ?? "").trim()
    const password = String(form.get("password") ?? "")
    const confirmation = String(form.get("confirm-password") ?? "")

    // Checked here rather than in `lib/auth.ts` alone, because the message is German and the server
    // answers in codes. The server remains the one that decides.
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(
        `Das Passwort muss mindestens ${MIN_PASSWORD_LENGTH} Zeichen lang sein.`
      )
      return
    }
    if (password !== confirmation) {
      setError("Die beiden Passwörter stimmen nicht überein.")
      return
    }

    setError(null)
    setPending(true)
    try {
      const { error: failure } = await authClient.signUp.email({
        name,
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
    } catch {
      setError(NETWORK_ERROR_MESSAGE)
      setPending(false)
    }
  }

  return (
    <form className="flex flex-col gap-6" onSubmit={submit} noValidate>
      <FieldGroup>
        <div className="flex flex-col items-center gap-1 text-center">
          <h1 className="text-2xl font-bold">Registrieren</h1>
          <p className="text-sm text-balance text-muted-foreground">
            Legen Sie ein Konto für die Prüfung von GOÄ-Abrechnungen an.
          </p>
        </div>

        {error ? (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : (
          alert
        )}

        <Field>
          <FieldLabel htmlFor="name">Name</FieldLabel>
          <Input
            id="name"
            name="name"
            type="text"
            autoComplete="name"
            autoFocus
            required
            placeholder="Dr. med. Maria Muster"
            disabled={pending}
          />
          <FieldDescription>
            Erscheint im Prüfprotokoll neben jeder Freigabe.
          </FieldDescription>
        </Field>

        <Field>
          <FieldLabel htmlFor="email">E-Mail</FieldLabel>
          <Input
            id="email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="username"
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
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            disabled={pending}
          />
          <FieldDescription>
            Mindestens {MIN_PASSWORD_LENGTH} Zeichen.
          </FieldDescription>
        </Field>

        <Field>
          <FieldLabel htmlFor="confirm-password">
            Passwort bestätigen
          </FieldLabel>
          <Input
            id="confirm-password"
            name="confirm-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            disabled={pending}
          />
        </Field>

        <Field>
          <Button type="submit" disabled={pending}>
            {pending ? "Konto wird erstellt…" : "Registrieren"}
          </Button>
        </Field>

        {social ? (
          <>
            <FieldSeparator>Oder fortfahren mit</FieldSeparator>
            <Field>{social}</Field>
          </>
        ) : null}

        <FieldDescription className="text-center">
          Bereits ein Konto?{" "}
          <Link
            href={loginHref}
            className="font-medium text-foreground underline underline-offset-4"
          >
            Anmelden
          </Link>
        </FieldDescription>
      </FieldGroup>
    </form>
  )
}
