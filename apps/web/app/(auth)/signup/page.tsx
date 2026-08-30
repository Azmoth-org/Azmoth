import type { Metadata } from "next"
import Link from "next/link"

import { Alert, AlertDescription } from "@workspace/ui/components/alert"

import { AuthShell } from "@/components/auth/auth-shell"
import { oauthErrorMessage } from "@/components/auth/auth-messages"
import { GoogleButton } from "@/components/auth/google-button"
import { SignupForm } from "@/components/auth/signup-form"
import { safeNext } from "@/lib/auth-redirect"
import { googleSignInEnabled } from "@/lib/auth-google"

export const metadata: Metadata = {
  title: "Registrieren",
  description:
    "Konto für die GOÄ-Prüfung anlegen. Der Zugang ist derzeit auf freigeschaltete " +
    "Pilot-Teilnehmer beschränkt.",
}

/**
 * Create an account — for an address on `SIGNUP_ALLOWLIST`.
 *
 * The gate is in `lib/auth.ts`'s `user.create.before` hook rather than on this screen, which means
 * it covers Google sign-in as well as the password form: both create a user row, and both are
 * refused by the same three lines. A check written here would guard one of the two doors.
 *
 * **The notice below is shown to everybody, before anyone types anything.** A form that accepts an
 * email and a password and then refuses is a small cruelty and a support ticket; saying up front
 * that the pilot is invite-only turns the same refusal into an expectation. It deliberately does
 * not say whether a *particular* address is on the list — that answer only comes from submitting,
 * and `SIGNUP_REFUSED_MESSAGE` is worded so that "not configured" and "not listed" are
 * indistinguishable to a stranger.
 *
 * A visitor who only wants to see the product is sent to `/demo`, which needs no account at all.
 * That link is the reason this screen can be strict without being a dead end.
 *
 * A new account belongs to no organisation. The rail's header says so ("Keine Organisation") and
 * offers to create one — registering does not silently make a practice on somebody's behalf,
 * because an organisation is a boundary and inventing one would be inventing the wrong one.
 *
 * The Google button is the same component `/login` renders and reaches the same endpoint — OAuth has
 * one door, and whether it registers or signs in depends on the account rather than on which screen
 * was clicked. Only the label differs, because "Mit Google anmelden" under a heading that says
 * *Registrieren* reads as the wrong button.
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
    <AuthShell>
      <SignupForm
        next={destination}
        loginHref={`/login${next ? `?next=${encodeURIComponent(destination)}` : ""}`}
        alert={
          failure ? (
            <Alert variant="destructive" role="alert">
              <AlertDescription>{failure}</AlertDescription>
            </Alert>
          ) : (
            <Alert>
              <AlertDescription className="space-y-2">
                <p>
                  Die Registrierung ist derzeit auf{" "}
                  <strong>freigeschaltete Pilot-Teilnehmer</strong> beschränkt.
                  Wenn Ihre Adresse noch nicht freigegeben ist, schreiben Sie uns
                  kurz — wir schalten sie frei.
                </p>
                <p>
                  Sie möchten die Prüfung zuerst nur ansehen?{" "}
                  <Link
                    href="/demo"
                    className="font-medium underline underline-offset-4"
                  >
                    Zur Demo mit Beispieldaten
                  </Link>{" "}
                  — ohne Konto und ohne Upload.
                </p>
              </AlertDescription>
            </Alert>
          )
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
      />
    </AuthShell>
  )
}
