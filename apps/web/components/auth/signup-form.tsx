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
  DUPLICATE_EMAIL_CODE,
  NETWORK_ERROR_MESSAGE,
  authErrorMessage,
} from "@/components/auth/auth-messages"
import { authClient } from "@/lib/auth-client"
import { slugifyOrganizationName } from "@/lib/organization-slug"
import {
  MIN_PASSWORD_LENGTH,
  checkPassword,
  passwordPolicyMessage,
  type PasswordCheck,
} from "@/lib/password-policy"

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
 *
 * ## The password field is the one exception to "uncontrolled"
 *
 * Every other field here is read from `FormData` at submit and holds no state in between — see
 * `login-form.tsx` for why. The password field is different because of the live strength meter:
 * showing "Schwach/Okay/Stark" as someone types requires a re-render on every keystroke, and that
 * re-render is scoped to `PasswordField` below rather than to this whole form, so the other three
 * fields still repaint only once, on submit. `lib/password-policy.ts` is what both the meter and
 * the rejection message below call, so they can't describe the policy differently.
 *
 * ## A duplicate email gets an escape hatch, not just a sentence
 *
 * `USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL` is the one failure on this form where "try again" is not
 * the fix — the fix is `/login`. So alongside the translated message, this form also renders a
 * "Stattdessen anmelden" link straight to it, carrying the same `next` the sign-up would have.
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
  const [duplicateEmail, setDuplicateEmail] = React.useState(false)
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
    // answers in codes. The server remains the one that decides — and still enforces the length
    // floor on its own, since the character-class half of this policy is client-only (see
    // `lib/password-policy.ts`).
    const passwordIssue = passwordPolicyMessage(password)
    if (passwordIssue) {
      setDuplicateEmail(false)
      setError(passwordIssue)
      return
    }
    if (password !== confirmation) {
      setDuplicateEmail(false)
      setError("Die beiden Passwörter stimmen nicht überein.")
      return
    }

    setError(null)
    setDuplicateEmail(false)
    setPending(true)
    try {
      const { error: failure } = await authClient.signUp.email({
        name: organizationName,
        email,
        password,
      })
      if (failure) {
        setError(authErrorMessage(failure))
        setDuplicateEmail(failure.code === DUPLICATE_EMAIL_CODE)
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
            <AlertDescription>
              {error}{" "}
              {duplicateEmail ? (
                <Link
                  href={loginHref}
                  className="font-medium underline underline-offset-4"
                >
                  Stattdessen anmelden
                </Link>
              ) : null}
            </AlertDescription>
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

        <PasswordField disabled={pending} />

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

/**
 * The password input plus its live strength meter, isolated in its own component so the keystroke
 * it re-renders on is its own rather than the whole `SignupForm` — see the module docstring.
 *
 * Still submitted the ordinary way: it carries `name="password"` and `submit` above reads it back
 * out of `FormData`, exactly like every other field. Tracking `value` here is only what feeds the
 * meter, not a second source of truth for what gets submitted.
 */
function PasswordField({ disabled }: { disabled: boolean }) {
  const [value, setValue] = React.useState("")
  const check = checkPassword(value)

  return (
    <Field>
      <FieldLabel htmlFor="password">Passwort</FieldLabel>
      <Input
        id="password"
        name="password"
        type="password"
        autoComplete="new-password"
        required
        minLength={MIN_PASSWORD_LENGTH}
        disabled={disabled}
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <FieldDescription>
        Mindestens {MIN_PASSWORD_LENGTH} Zeichen, davon mindestens 3 von 4: Kleinbuchstaben,
        Großbuchstaben, Ziffern, Sonderzeichen.
      </FieldDescription>
      {value ? <PasswordStrengthMeter check={check} /> : null}
    </Field>
  )
}

const STRENGTH_TONE: Record<PasswordCheck["strength"], { bar: string; label: string }> = {
  Schwach: { bar: "bg-red-500", label: "text-red-700" },
  Okay: { bar: "bg-amber-500", label: "text-amber-700" },
  Stark: { bar: "bg-emerald-500", label: "text-emerald-700" },
}

const STRENGTH_SEGMENTS: Record<PasswordCheck["strength"], number> = {
  Schwach: 1,
  Okay: 2,
  Stark: 3,
}

/** "Schwach/Okay/Stark", mirroring the server-parity policy in `lib/password-policy.ts`. */
function PasswordStrengthMeter({ check }: { check: PasswordCheck }) {
  const tone = STRENGTH_TONE[check.strength]
  const filled = STRENGTH_SEGMENTS[check.strength]

  return (
    <div className="flex items-center gap-2">
      <div className="flex flex-1 gap-1">
        {[0, 1, 2].map((segment) => (
          <div
            key={segment}
            className={`h-1.5 flex-1 rounded-full ${segment < filled ? tone.bar : "bg-muted"}`}
          />
        ))}
      </div>
      <span className={`text-xs font-medium ${tone.label}`}>{check.strength}</span>
    </div>
  )
}
