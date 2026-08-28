/**
 * The only SQL this application runs against `doctor_profiles` and `practices`. **Server-only.**
 *
 * Both writes are upserts, and that is the interesting decision here. Onboarding is not a one-shot
 * event: somebody abandons the form and comes back, mistypes a LANR and fixes it, or is sent the
 * link again after a practice moves. `INSERT` alone would make the second attempt a duplicate-key
 * error on a screen that has no way to explain it, and a read-then-branch would be the same race
 * with extra steps — two tabs submitting at once would both read "no row" and both insert.
 * `ON CONFLICT … DO UPDATE` makes "save this practice's details" idempotent, which is what the
 * caller actually means, and it is one statement so the database resolves the race rather than
 * this code. Both backends have supported it for years (`apps/web/lib/db.ts` on the dialect split).
 *
 * `created_at` is written on insert and deliberately **not** touched by the update branch — the
 * `excluded` row carries a fresh value and assigning it would quietly reset when a practice first
 * registered every time somebody corrected a typo. `updated_at` gets the new stamp, which is the
 * distinction between the two columns.
 *
 * `RETURNING` on both branches, so the caller answers with the row that is actually in the database
 * rather than echoing back what it was sent. On a conflict those differ in exactly the way that
 * matters: the id and `created_at` belong to the original row, not to this request.
 */

import {
  formatUuid,
  newId,
  nowStamp,
  query,
  toIso,
  type SqlRow,
} from "@/lib/db"
import type { DoctorInput, PracticeInput } from "@/lib/onboarding/validate"

/**
 * What onboarding has stored for one session, and whether that is the whole of it.
 *
 * `complete` is both halves present, and it is the authoritative answer the `onboarding_complete`
 * cookie is a cache of — see `lib/onboarding/cookie.ts`. A profile without a practice is a real
 * state rather than a corrupt one: the two rows are written by one request but not in one
 * transaction (they cannot be — the organisation between them goes through Better Auth's adapter),
 * so a request refused at step two leaves exactly this. The form then re-opens with step one
 * already filled in, which is the correct way to finish something half-finished.
 */
export type OnboardingState = {
  doctor: DoctorProfile | null
  practice: Practice | null
  complete: boolean
}

/** A stored doctor profile, in the shape the API answers with. */
export type DoctorProfile = {
  id: string
  userId: string
  title: string | null
  firstName: string
  lastName: string
  lanr: string
  specialty: string
  createdAt: string
  updatedAt: string
}

/** A stored practice, in the shape the API answers with. */
export type Practice = {
  id: string
  organizationId: string
  practiceName: string
  bsnr: string
  city: string
  plz: string
  createdAt: string
  updatedAt: string
}

/** `snake_case` in the database, `camelCase` on the wire. The mapping is written out, once, here. */
function text(row: SqlRow, column: string): string {
  const value = row[column]
  return typeof value === "string" ? value : String(value ?? "")
}

function optionalText(row: SqlRow, column: string): string | null {
  const value = row[column]
  return typeof value === "string" && value !== "" ? value : null
}

/**
 * Create or update the profile for one Better Auth user.
 *
 * Keyed on `user_id`, which carries the unique index the conflict target needs. The LANR carries
 * one too and is *not* the conflict target: a second account claiming a LANR that already belongs
 * to somebody else must fail rather than silently move the number across, so that write raises and
 * the route turns it into a 409 (`uniqueViolationColumn` in `lib/db.ts` is what names the column).
 */
export async function upsertDoctorProfile(
  userId: string,
  input: DoctorInput
): Promise<DoctorProfile> {
  const stamp = nowStamp()

  const rows = await query(
    `INSERT INTO doctor_profiles
       (id, user_id, title, first_name, last_name, lanr, specialty, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (user_id) DO UPDATE SET
       title      = excluded.title,
       first_name = excluded.first_name,
       last_name  = excluded.last_name,
       lanr       = excluded.lanr,
       specialty  = excluded.specialty,
       updated_at = excluded.updated_at
     RETURNING id, user_id, title, first_name, last_name, lanr, specialty,
               created_at, updated_at`,
    [
      newId(),
      userId,
      input.title,
      input.firstName,
      input.lastName,
      input.lanr,
      input.specialty,
      stamp,
      stamp,
    ]
  )

  const row = rows[0]
  // Unreachable in practice — an upsert with RETURNING either produces a row or throws — but the
  // alternative is a non-null assertion, and `noUncheckedIndexedAccess` is on for good reasons.
  if (!row) throw new Error("doctor_profiles upsert returned no row")

  return toDoctorProfile(row)
}

/** One `doctor_profiles` row, in the shape the API and the form both speak. */
function toDoctorProfile(row: SqlRow): DoctorProfile {
  return {
    id: formatUuid(row.id),
    userId: text(row, "user_id"),
    title: optionalText(row, "title"),
    firstName: text(row, "first_name"),
    lastName: text(row, "last_name"),
    lanr: text(row, "lanr"),
    specialty: text(row, "specialty"),
    createdAt: toIso(row.created_at),
    updatedAt: toIso(row.updated_at),
  }
}

/**
 * Create or update the practice behind one Better Auth organisation.
 *
 * Keyed on `organization_id`. Nothing else here is unique — a BSNR names premises that several
 * organisations may legitimately bill from, and the migration says why at length.
 */
export async function upsertPractice(
  organizationId: string,
  input: PracticeInput
): Promise<Practice> {
  const stamp = nowStamp()

  const rows = await query(
    `INSERT INTO practices
       (id, organization_id, practice_name, bsnr, city, plz, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (organization_id) DO UPDATE SET
       practice_name = excluded.practice_name,
       bsnr          = excluded.bsnr,
       city          = excluded.city,
       plz           = excluded.plz,
       updated_at    = excluded.updated_at
     RETURNING id, organization_id, practice_name, bsnr, city, plz,
               created_at, updated_at`,
    [
      newId(),
      organizationId,
      input.practiceName,
      input.bsnr,
      input.city,
      input.plz,
      stamp,
      stamp,
    ]
  )

  const row = rows[0]
  if (!row) throw new Error("practices upsert returned no row")

  return toPractice(row)
}

/** One `practices` row, likewise. */
function toPractice(row: SqlRow): Practice {
  return {
    id: formatUuid(row.id),
    organizationId: text(row, "organization_id"),
    practiceName: text(row, "practice_name"),
    bsnr: text(row, "bsnr"),
    city: text(row, "city"),
    plz: text(row, "plz"),
    createdAt: toIso(row.created_at),
    updatedAt: toIso(row.updated_at),
  }
}

/**
 * Everything onboarding has stored for this session, for the form to open on.
 *
 * Two queries rather than a join, and deliberately: the practice is keyed on the *organisation* and
 * the profile on the *user*, so there is no column to join them on — the pairing exists only in the
 * session that holds both ids. A `null` `organizationId` (an account that has not been through
 * onboarding, and therefore has no organisation — see `app/(auth)/signup/page.tsx`) skips the second
 * query rather than running one that could not match.
 *
 * Both lookups are on unique indexes, which is what makes this cheap enough to run on every render
 * of `/onboarding`. It is deliberately *not* run on every render of the application: that is what
 * the cookie is for.
 */
export async function readOnboarding(
  userId: string,
  organizationId: string | null
): Promise<OnboardingState> {
  const profiles = await query<SqlRow>(
    `SELECT id, user_id, title, first_name, last_name, lanr, specialty, created_at, updated_at
       FROM doctor_profiles
      WHERE user_id = ?`,
    [userId]
  )

  const practices = organizationId
    ? await query<SqlRow>(
        `SELECT id, organization_id, practice_name, bsnr, city, plz, created_at, updated_at
           FROM practices
          WHERE organization_id = ?`,
        [organizationId]
      )
    : []

  const profileRow = profiles[0]
  const practiceRow = practices[0]

  const doctor = profileRow ? toDoctorProfile(profileRow) : null
  const practice = practiceRow ? toPractice(practiceRow) : null

  return { doctor, practice, complete: doctor !== null && practice !== null }
}
