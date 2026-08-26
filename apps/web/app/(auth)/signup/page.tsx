import type { Metadata } from "next"
import Link from "next/link"

import { Alert, AlertDescription } from "@workspace/ui/components/alert"

import { AuthCard } from "@/components/auth/auth-card"
import { oauthErrorMessage } from "@/components/auth/auth-messages"
import { GoogleButton } from "@/components/auth/google-button"
import { SignupForm } from "@/components/auth/signup-form"
import { safeNext } from "@/lib/auth-redirect"
import { googleSignInEnabled } from "@/lib/auth-google"

export const metadata: Metadata = {
  title: "Registrieren",
  description: "Konto für die GOÄ-Prüfung anlegen. Interne Anwendung, nur synthetische Daten.",
}

/**
 * Create an account.
 *
 * Open to anyone who can reach this URL, which is a gap rather than a feature — see the note in
 * `lib/auth.ts` and `docs/compliance/PRIVATE_DATA_WARNING.md`. It is acceptable for a build that
 * holds only synthetic data and has to be closed (invite, or SSO) before one holds a real record.
 * Google does not narrow that gap and is not a substitute for closing it: any Google account can
 * register here, not only one from a particular Workspace domain.
 *
 * The Google button is the same component `/login` renders and reaches the same endpoint — OAuth
 * has one door, and whether it registers or signs in depends on the account rather than on which
 * screen was clicked. Only the label differs, because "Mit Google anmelden" under a heading that
 * says *Registrieren* reads as the wrong button.
 */
export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>
}) {
  const { next, error } = await searchParams
  const destination = safeNext(next)
  const failure = oauthErrorMessage(error)
  const back = `/signup${next ? `?next=${encodeURIComponent(destination)}` : ""}`

  return (
    <AuthCard
      title="Registrieren"
      description="Legen Sie ein Konto für die Prüfung von GOÄ-Abrechnungen an."
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
            label="Mit Google registrieren"
            callbackURL={destination}
            errorCallbackURL={back}
          />
        ) : null
      }
      footer={
        <>
          Bereits ein Konto?{" "}
          <Link
            href={`/login${next ? `?next=${encodeURIComponent(destination)}` : ""}`}
            className="text-foreground font-medium underline underline-offset-4"
          >
            Anmelden
          </Link>
        </>
      }
    >
      <SignupForm next={destination} />
    </AuthCard>
  )
}
