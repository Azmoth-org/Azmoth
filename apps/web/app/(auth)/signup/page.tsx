import type { Metadata } from "next"
import Link from "next/link"

import { AuthCard } from "@/components/auth/auth-card"
import { SignupForm } from "@/components/auth/signup-form"
import { safeNext } from "@/lib/auth-redirect"

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
 */
export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>
}) {
  const { next } = await searchParams
  const destination = safeNext(next)

  return (
    <AuthCard
      title="Registrieren"
      description="Legen Sie ein Konto für die Prüfung von GOÄ-Abrechnungen an."
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
