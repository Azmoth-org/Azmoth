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
import { slugifyOrganizationName } from "@/lib/organization-slug"

/**
 * The password floor, stated in three places that must not disagree.
 *
 * `lib/auth.ts` enforces it, the browser's own `minLength` rejects a short one without a
 * round-trip, and the sentence under the field says it before either fires. 12 rather than Better
 * Auth's default 8 — see the note in `lib/auth.ts`.
 */
const MIN_PASSWORD_LENGTH = 12

/**
 * Create an account — for the organisation running the pilot, not for one named reviewer.
 *
 * The layout is shadcn's `signup-02` form, installed into this app rather than into
 * `@workspace/ui`. See `components/auth/login-form.tsx` for why it lives here, why the fields are
 * uncontrolled, why `router.refresh()` precedes the push, and why a returned `{ error }` and a
 * thrown exception produce different sentences. All four apply identically.
 *
 * ## Four fields, and no personal ones
 *
 * Email, password, its confirmation, and the organisation's name — nothing else. The pilot persona
 * is a billing bureau (Abrechnungsstelle) working from synthetic data, not an individual physician,
 * so there is no LANR, no phone number and no postal address to ask for here: none of it would be
 * used, and GDPR's data-minimisation principle is the reason not to collect it anyway just because a
 * form template had a field for it. Whoever needs to be named on a specific delivery still can be —
 * that belongs to the delivery, not to the account that uploaded it.
 *
 * ## The organisation is created here, not later from the sidebar
 *
 * Better Auth's `name` field still exists on every user row and is not nullable, so it is set to the
 * organisation's own name rather than asked for twice — nothing in this application reads a
 * personal name back out of it. Immediately after `signUp.email` succeeds, `authClient.organization.
 * create` and `.setActive` run in the same submit, so a reader who has just registered lands on a
 * dashboard that already knows which organisation it is rather than one reading "Keine
 * Organisation" until they find the prompt in `organisation-switcher.tsx` that used to be the only
 * way to get one. That stopgap still exists for a second organisation later; it is no longer the
 * first one's only door.
 *
 * A failure to create the organisation is reported rather than swallowed — the account exists at
 * that point regardless, and signing in afterwards reaches the same rail's "Organisation anlegen".
 * That is a worse first run than this form succeeding outright, not a broken one.
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
    const organizationName = String(form.get("organization") ?? "").trim()
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
        name: organizationName,
        email,
        password,
      })
      if (failure) {
        setError(authErrorMessage(failure))
        setPending(false)
        return
      }

      // The account exists at this point regardless of what happens below, so a failure here is
      // reported rather than left to look like the sign-up itself failed — see the module docstring.
      const { data: organization, error: organizationFailure } =
        await authClient.organization.create({
          name: organizationName,
          slug: slugifyOrganizationName(organizationName),
        })
      if (organizationFailure) {
        setError(authErrorMessage(organizationFailure))
        setPending(false)
        return
      }

      // `create` does not itself make the new organisation the session's active one — the rail
      // would otherwise still read "Keine Organisation" until something else set it.
      await authClient.organization.setActive({
        organizationId: organization.id,
      })

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
          <h1 className="text-display-md">Registrieren</h1>
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
          <FieldLabel htmlFor="organization">Organisation</FieldLabel>
          <Input
            id="organization"
            name="organization"
            type="text"
            autoComplete="organization"
            autoFocus
            required
            placeholder="Abrechnungsstelle Muster"
            disabled={pending}
          />
          <FieldDescription>
            Der Name Ihrer Abrechnungsstelle oder Praxis.
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
