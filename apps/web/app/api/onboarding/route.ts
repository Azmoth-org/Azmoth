/**
 * `POST /api/onboarding` — the doctor and the practice behind a new account.
 *
 * The one endpoint in this application that writes business data directly instead of proxying to
 * the engine, and the one that spans both migrators: it writes `doctor_profiles` and `practices`,
 * which are Alembic's tables (`apps/engine/alembic/versions/20260828_0005_practice_identity.py`),
 * and it renames a Better Auth `organization`, which is Better Auth's row and is therefore touched
 * only through Better Auth's own API. Nothing here adds a business column to an identity table —
 * that separation is what lets two migrators share one database, and `lib/auth-db.ts` says why.
 *
 *     POST /api/onboarding
 *     {
 *       "doctor":   { "title": "Dr. med.", "firstName": "…", "lastName": "…",
 *                     "lanr": "123456789", "specialty": "Allgemeinmedizin" },
 *       "practice": { "practiceName": "Praxis am Markt", "bsnr": "987654321",
 *                     "city": "Bonn", "plz": "53111" }
 *     }
 *
 * ## Authentication
 *
 * `currentSession()`, which resolves the cookie against the `session` table. `middleware.ts` also
 * refuses this path without a cookie and cannot do better — it has no database — so a cookie that is
 * present but forged, expired or **revoked by a sign-out** gets past it and is stopped here. Same
 * reasoning as `lib/engine.ts`, and the same reason the check is not left to the middleware.
 *
 * Everything written is keyed on ids taken from *that session* — `session.user.id` and
 * `session.session.activeOrganizationId` — never from the body. A `userId` field in the request
 * would be an endpoint for writing somebody else's LANR.
 *
 * ## The organisation, which may not exist yet
 *
 * `app/(auth)/signup/page.tsx` is explicit that a new account belongs to no organisation: signing
 * up does not invent a practice on somebody's behalf. Onboarding is the moment that stops being
 * true, so this handles both states — an active organisation is renamed to the practice name, and
 * no active organisation means one is created with that name and made active. Either way the
 * organisation switcher ends up showing a practice rather than an empty label, which is the point.
 *
 * ## The order of the three writes, which is chosen for how they fail
 *
 * There is no transaction spanning them and there cannot be: the two rows are written with
 * `pg`/`better-sqlite3` while the organisation goes through Better Auth's own adapter. So the
 * ordering is what decides what a half-completed request leaves behind, and it is
 *
 *     1. the doctor profile   — the only write that can be refused on a value somebody typed
 *     2. the organisation     — created, or renamed; the only write that can be refused on a role
 *     3. the practice         — which by then can fail on nothing but the database being gone
 *
 * A LANR already registered to another account is *the* predictable rejection here, and putting
 * that write first means such a request is refused having created nothing — no organisation, no
 * practice. A member who is not allowed to rename their organisation is the other one, and it is
 * refused having written only that user's own profile, which is theirs and is correct.
 *
 * The brief puts the rename last. The end state is identical and every write is an upsert, so the
 * whole request is safe to repeat; what this ordering buys is that the failures leave nothing
 * confusing behind.
 */

import { APIError } from "better-auth/api"
import { headers } from "next/headers"
import { NextResponse } from "next/server"

import { getAuth } from "@/lib/auth"
import { uniqueViolationColumn } from "@/lib/db"
import { setOnboardingCookie } from "@/lib/onboarding/cookie"
import { upsertDoctorProfile, upsertPractice } from "@/lib/onboarding/store"
import { parseOnboarding } from "@/lib/onboarding/validate"
import { currentSession } from "@/lib/session"

/** Written to and read from the database on every call; never cached, never statically rendered. */
export const dynamic = "force-dynamic"

/** The organisation this practice belongs to, after it has been named. */
type ResolvedOrganization = {
  id: string
  name: string
  slug: string
}

function failure(
  error: string,
  message: string,
  status: number,
  details?: unknown
): Response {
  return Response.json(
    details === undefined ? { error, message } : { error, message, details },
    { status, headers: { "Cache-Control": "no-store" } }
  )
}

/**
 * A URL-safe slug from a practice name, or `praxis` when nothing survives.
 *
 * Better Auth requires a slug on create and enforces its uniqueness across every organisation in
 * the deployment, so this is a *proposal* — `ensureOrganization` retries with a suffix when it is
 * taken. Umlauts are transliterated rather than dropped, because "Praxis Grün" collapsing to
 * `praxis-gr` is the kind of small wrongness a practice notices in its own URL.
 */
export function slugify(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    // Anything that is left and is not a letter, a digit or a hyphen becomes a separator. NFD
    // first, so an accent that was composed into one code point is split off and dropped rather
    // than taking its letter with it.
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
    .replace(/-+$/g, "")

  return slug || "praxis"
}

/** Six hex characters, to get past a slug somebody else already has. */
function slugSuffix(): string {
  return Math.floor(Math.random() * 0xffffff)
    .toString(16)
    .padStart(6, "0")
}

/**
 * The active organisation, renamed to the practice — or a new one, created and made active.
 *
 * `keepCurrentActiveOrganization` is left at its default on create, which is what makes the new
 * organisation the session's active one. Nothing else in this request would set it, and an
 * organisation the user is not switched into would leave the rail still reading "Keine
 * Organisation" immediately after onboarding said it was done.
 */
async function ensureOrganization(
  activeOrganizationId: string | null,
  practiceName: string,
  requestHeaders: Headers
): Promise<ResolvedOrganization> {
  const auth = getAuth()

  if (activeOrganizationId) {
    const updated = await auth.api.updateOrganization({
      body: {
        data: { name: practiceName },
        organizationId: activeOrganizationId,
      },
      headers: requestHeaders,
    })

    return {
      id: activeOrganizationId,
      name: readString(updated, "name") ?? practiceName,
      slug: readString(updated, "slug") ?? "",
    }
  }

  // Three attempts: the clean slug, then two suffixed ones. A practice name that collides is
  // ordinary — two "Praxis am Markt" in one deployment — and a collision on a random suffix after
  // that is not something to keep retrying about.
  let candidate = slugify(practiceName)

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const created = await auth.api.createOrganization({
        body: { name: practiceName, slug: candidate },
        headers: requestHeaders,
      })

      const id = readString(created, "id")
      if (!id) {
        throw new Error("createOrganization returned no organisation")
      }

      return {
        id,
        name: readString(created, "name") ?? practiceName,
        slug: readString(created, "slug") ?? candidate,
      }
    } catch (error) {
      if (!isSlugTaken(error) || attempt === 2) throw error
      candidate = `${slugify(practiceName).slice(0, 41)}-${slugSuffix()}`
    }
  }

  // Unreachable: the loop either returns or rethrows on its last attempt.
  throw new Error("createOrganization exhausted its slug attempts")
}

/** Better Auth's endpoints are typed loosely enough that reading a field is worth doing safely. */
function readString(value: unknown, key: string): string | null {
  if (typeof value !== "object" || value === null) return null
  const candidate = (value as Record<string, unknown>)[key]
  return typeof candidate === "string" && candidate !== "" ? candidate : null
}

/** The one create failure worth retrying rather than reporting. */
function isSlugTaken(error: unknown): boolean {
  return (
    error instanceof APIError &&
    error.status === "BAD_REQUEST" &&
    typeof error.body?.message === "string" &&
    /already exists|slug already taken/i.test(error.body.message)
  )
}

export async function POST(request: Request): Promise<Response> {
  const session = await currentSession()
  if (!session) {
    return failure(
      "unauthenticated",
      "Die Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
      401
    )
  }

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return failure(
      "invalid_request_body",
      "Der Request-Body ist kein gültiges JSON.",
      400
    )
  }

  const parsed = parseOnboarding(body)
  if (!parsed.ok) {
    return failure(
      "validation_error",
      "Bitte prüfen Sie die markierten Felder.",
      422,
      parsed.errors
    )
  }

  const { doctor, practice } = parsed.value
  const requestHeaders = await headers()

  // 1. The doctor. Keyed on the session's own user id, so the only thing it can be refused on is a
  //    LANR that belongs to somebody else — and refusing here means nothing else has happened yet.
  let profile
  try {
    profile = await upsertDoctorProfile(session.user.id, doctor)
  } catch (error) {
    const column = uniqueViolationColumn(error)
    if (column === "lanr") {
      return failure(
        "lanr_already_registered",
        "Diese LANR ist bereits einem anderen Konto zugeordnet. Bitte prüfen Sie die Nummer.",
        409,
        { field: "doctor.lanr" }
      )
    }
    if (column) {
      return failure(
        "conflict",
        "Diese Angaben sind bereits einem anderen Konto zugeordnet.",
        409,
        { column }
      )
    }
    throw error
  }

  // 2. The organisation, named after the practice — created if the account has none.
  let organization: ResolvedOrganization
  try {
    organization = await ensureOrganization(
      session.session.activeOrganizationId ?? null,
      practice.practiceName,
      requestHeaders
    )
  } catch (error) {
    if (error instanceof APIError) {
      // Better Auth's own refusals, with their status: FORBIDDEN for a member who may not rename
      // the practice, and the organisation limit for an account creating too many. Its messages are
      // English and internal, so `details` carries it for a log and the rendered sentence is ours.
      const status = error.status === "FORBIDDEN" ? 403 : 400
      return failure(
        "organization_not_updated",
        status === 403
          ? "Sie sind nicht berechtigt, die Praxis dieser Organisation zu ändern. " +
              "Bitte wenden Sie sich an die Inhaberin oder den Inhaber der Organisation."
          : "Die Organisation konnte nicht angelegt oder umbenannt werden.",
        status,
        error.body?.message
      )
    }
    throw error
  }

  // 3. The practice. `organization_id` is the conflict target rather than a constraint that can be
  //    violated, so by this point there is nothing left to refuse.
  const stored = await upsertPractice(organization.id, practice)

  // Only now, with all three writes done, is this session onboarded — so this is the only place in
  // the success path that may say so. `middleware.ts` reads this cookie instead of the database on
  // every request; `lib/onboarding/cookie.ts` explains why that is safe and what refills it when
  // the same account signs in somewhere this cookie has never been set.
  return setOnboardingCookie(
    NextResponse.json(
      { doctor: profile, practice: stored, organization },
      { headers: { "Cache-Control": "no-store" } }
    )
  )
}
