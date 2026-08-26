import type { Metadata } from "next"
import Link from "next/link"

import { AuthCard } from "@/components/auth/auth-card"
import { LoginForm } from "@/components/auth/login-form"
import { safeNext } from "@/lib/auth-redirect"

export const metadata: Metadata = {
  title: "Anmelden",
  description: "Anmeldung zur GOÄ-Prüfung. Interne Anwendung, nur synthetische Daten.",
}

/**
 * The way in.
 *
 * `next` is the screen the middleware interrupted, and it is passed through `safeNext` before it
 * reaches the form — a login page that will redirect anywhere is how a phishing link comes to be
 * served from the application's own domain. Anything that is not a same-site path becomes `/`.
 *
 * A server component holding a client form, rather than a client page: the title and the `robots`
 * metadata belong to the route, and there is nothing on this screen that needs the browser except
 * the two inputs and the submit.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>
}) {
  const { next } = await searchParams
  const destination = safeNext(next)

  return (
    <AuthCard
      title="Anmelden"
      description="Melden Sie sich mit Ihrer dienstlichen E-Mail-Adresse an."
      footer={
        <>
          Noch kein Konto?{" "}
          <Link
            // The destination travels with the reader across the two screens, so a visitor who was
            // sent here from /review and turns out to need an account still lands on /review.
            href={`/signup${next ? `?next=${encodeURIComponent(destination)}` : ""}`}
            className="text-foreground font-medium underline underline-offset-4"
          >
            Registrieren
          </Link>
        </>
      }
    >
      <LoginForm next={destination} />
    </AuthCard>
  )
}
