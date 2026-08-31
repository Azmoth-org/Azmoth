import type { Metadata } from "next"
import Link from "next/link"
import { cookies } from "next/headers"
import { redirect } from "next/navigation"

import { OnboardingForm } from "@/components/onboarding/onboarding-form"
import { safeNext } from "@/lib/auth-redirect"
import { ONBOARDING_COOKIE } from "@/lib/onboarding/cookie"
import { readOnboarding } from "@/lib/onboarding/store"
import { requireSession } from "@/lib/session"

export const metadata: Metadata = {
  title: "Einrichtung",
  description: "Arztprofil und Praxisdaten für die GOÄ-Prüfung hinterlegen.",
  robots: { index: false, follow: false },
}

/** Reads the session and both business tables on every visit; never cached. */
export const dynamic = "force-dynamic"

/**
 * `/onboarding` — the practice's own details, before the application is of any use to it.
 *
 * ## This is the authoritative half of the onboarding gate
 *
 * `middleware.ts` decides from a cookie, because middleware has no database. This decides from the
 * database, and the relationship between the two is exactly the one the session gate already uses:
 * a fast optimistic check in the middleware, and the real answer somewhere that can query. The
 * difference is which way the correction runs. For sessions, the authoritative check *rejects* what
 * the middleware let through. Here it *admits* what the middleware turned away — a reader whose
 * details are already stored but whose browser has never held the cookie.
 *
 * That case is ordinary, not exotic: a second device, another browser, cleared site data, or a
 * cookie that expired alongside the session it was cut to match. Sending them to
 * `/api/onboarding/resume` re-issues the cookie and forwards them on, so the whole detour is one
 * redirect nobody sees. Without it the cookie would be the only record of a fact that lives in the
 * database, and the second device would be marched through a form containing its own data.
 *
 * **Only when the cookie is absent.** A reader who has the cookie and comes here deliberately wants
 * to *change* something — a practice moves, a name is misspelled — and bouncing them to the
 * dashboard would make their own details unreachable. So they get the form, prefilled, and
 * `POST /api/onboarding` upserts. That is also why this page reads the stored values at all rather
 * than only asking whether they exist.
 *
 * ## Not inside `(app)`
 *
 * A sidebar full of links to screens that redirect straight back here would be worse than no
 * sidebar — the same reason `(auth)` sits outside it. What is shared instead is the disclaimer and
 * the wordmark, because this is a screen somebody types a real LANR into and the standing statement
 * about synthetic data belongs where that happens.
 */
export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>
}) {
  const { next } = await searchParams
  const destination = safeNext(next)

  // `requireSession`, not `currentSession`: the middleware sends signed-out visitors to `/login`
  // before they reach this, and this is the check that decides — same split as `(app)/layout.tsx`.
  const session = await requireSession(
    `/onboarding${next ? `?next=${encodeURIComponent(destination)}` : ""}`
  )

  const store = await cookies()
  const believedOnboarded = store.get(ONBOARDING_COOKIE)?.value === "1"

  const state = await readOnboarding(
    session.user.id,
    session.session.activeOrganizationId ?? null
  )

  if (state.complete && !believedOnboarded) {
    // A cookie this browser never had, for a practice that has already onboarded. The resume route
    // re-derives that from the database, sets the cookie and forwards — see its own docstring.
    redirect(`/api/onboarding/resume?next=${encodeURIComponent(destination)}`)
  }

  return (
    <div className="flex min-h-svh flex-col gap-8 bg-muted/30 px-4 py-8 sm:px-6 md:py-12">
      <div className="flex justify-center md:justify-start">
        <Link
          href="/"
          className="flex items-center gap-2.5"
          aria-label="Azmoth"
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary font-mono text-xs font-medium text-primary-foreground">
            AZ
          </span>
          <span className="grid text-left leading-tight">
            <span className="text-base font-semibold">Azmoth</span>
            <span className="text-xs text-muted-foreground">GOÄ-Prüfung</span>
          </span>
        </Link>
      </div>

      <div className="flex flex-1 items-start justify-center md:items-center">
        {/*
          `max-w-xl` rather than the auth screens' `max-w-sm`: this card carries paired fields —
          Vorname/Nachname, PLZ/Ort — and at 384px those pairs have to stack on a desktop screen
          that has room for them side by side.
        */}
        <div className="flex w-full max-w-xl flex-col gap-6">
          <div className="flex flex-col gap-1">
            <h1 className="text-display-md">Einrichtung</h1>
            <p className="text-sm text-balance text-muted-foreground">
              Bevor Abrechnungen geprüft werden können, hinterlegen Sie bitte
              einmalig Ihr Arztprofil und Ihre Praxisdaten.
            </p>
          </div>

          <OnboardingForm
            next={destination}
            initial={{
              title: state.doctor?.title ?? "",
              firstName: state.doctor?.firstName ?? "",
              lastName: state.doctor?.lastName ?? "",
              lanr: state.doctor?.lanr ?? "",
              specialty: state.doctor?.specialty ?? "",
              practiceName: state.practice?.practiceName ?? "",
              bsnr: state.practice?.bsnr ?? "",
              city: state.practice?.city ?? "",
              plz: state.practice?.plz ?? "",
            }}
          />

          <p className="text-center text-xs text-balance text-muted-foreground">
            Interne Anwendung. Ausschließlich synthetische Daten — keine
            Patientendaten eingeben.
          </p>
        </div>
      </div>
    </div>
  )
}
