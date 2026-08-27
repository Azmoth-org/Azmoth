"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import * as React from "react"

import { Alert, AlertDescription } from "@workspace/ui/components/alert"
import { SignupForm as SignupFormTemplate } from "@workspace/ui/components/signup-form"

import {
  NETWORK_ERROR_MESSAGE,
  authErrorMessage,
} from "@/components/auth/auth-messages"
import { authClient } from "@/lib/auth-client"

/**
 * The password floor, stated in three places that must not disagree.
 *
 * `lib/auth.ts` enforces it, the template hands it to the browser's own `minLength`, and the sentence
 * under the field says it. 12 rather than Better Auth's default 8 — see the note in `lib/auth.ts`.
 */
const MIN_PASSWORD_LENGTH = 12

/**
 * Create an account.
 *
 * The layout is `@workspace/ui`'s `SignupForm` template, and the confirmation field is new with it —
 * the form this replaced had one password box, so a typo produced an account nobody could sign in to
 * and no way to find out why. The comparison happens here rather than in the package, because the
 * message it produces is German and the package has no language.
 *
 * See `components/auth/login-form.tsx` for why the fields are uncontrolled, why `router.refresh()`
 * precedes the push, and why a returned `{ error }` and a thrown exception produce different
 * sentences. All three apply identically here.
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
    <SignupFormTemplate
      onSubmit={submit}
      noValidate
      pending={pending}
      minPasswordLength={MIN_PASSWORD_LENGTH}
      title="Registrieren"
      description="Legen Sie ein Konto für die Prüfung von GOÄ-Abrechnungen an."
      nameLabel="Name"
      namePlaceholder="Dr. med. Maria Muster"
      nameHint="Erscheint im Prüfprotokoll neben jeder Freigabe."
      emailLabel="E-Mail"
      emailPlaceholder="name@praxis.de"
      passwordLabel="Passwort"
      passwordHint={`Mindestens ${MIN_PASSWORD_LENGTH} Zeichen.`}
      confirmLabel="Passwort bestätigen"
      submitLabel={pending ? "Konto wird erstellt…" : "Registrieren"}
      separatorLabel="Oder fortfahren mit"
      social={social}
      alert={
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
          Bereits ein Konto?{" "}
          <Link
            href={loginHref}
            className="font-medium text-foreground underline underline-offset-4"
          >
            Anmelden
          </Link>
        </>
      }
    />
  )
}
