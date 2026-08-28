/**
 * Reading the onboarding form's body into something that can be written to the database.
 *
 * Hand-written rather than a schema library, for the same reason the rest of `lib/` is: this
 * application has one endpoint that takes a structured body from a browser, and adding a validation
 * dependency to the web tier for it would put a second definition of "a valid case" next to the
 * Pydantic models that already own that question for everything the engine touches.
 *
 * ## The three formats that are checked, and why they are checked here
 *
 * A LANR, a BSNR and a PLZ are all fixed-width digit strings, and none of them is enforced by the
 * database — `apps/engine/app/db/models.py` stores all three as `String(16)`, because a column width
 * is a poor place to state a format and a wrong one there is a migration rather than a fix. So the
 * check lives at the edge, where a person is typing and can be told which field is wrong.
 *
 * That matters more here than validation usually does. A LANR and a BSNR are what identify the
 * physician and the premises on a claim, and a malformed one is not caught by anything downstream —
 * it is caught by the payer, weeks later, as a rejected invoice. Refusing "12345678" at the point
 * somebody types it is the only cheap moment there is.
 *
 * Digits only, and exactly nine: both numbers are defined that way (the LANR's last two digits are
 * the Fachgruppe, the BSNR's first two the KV-Bezirk). Spaces are stripped rather than rejected —
 * people read these numbers off a letter in groups, and refusing a copy-paste over its whitespace
 * would be pedantry rather than validation. A PLZ is five digits, leading zeros included, which is
 * exactly why it is carried as a string everywhere.
 */

/** The doctor half, as the database wants it: trimmed, checked, `title` absent rather than blank. */
export type DoctorInput = {
  title: string | null
  firstName: string
  lastName: string
  lanr: string
  specialty: string
}

/** The practice half. `practiceName` is also what the active organisation gets renamed to. */
export type PracticeInput = {
  practiceName: string
  bsnr: string
  city: string
  plz: string
}

export type OnboardingInput = {
  doctor: DoctorInput
  practice: PracticeInput
}

/** One thing wrong with the body, named by the path a form can highlight. */
export type FieldError = {
  field: string
  message: string
}

export type ParseResult =
  | { ok: true; value: OnboardingInput }
  | { ok: false; errors: FieldError[] }

/**
 * Column widths from `apps/engine/app/db/models.py`, restated so a too-long value is a 422 naming
 * the field rather than a driver error naming a constraint. They must not drift from the migration:
 * Postgres truncates nothing and refuses the write, SQLite ignores `VARCHAR(n)` entirely and would
 * silently store the overlong value until the same row failed to move to Postgres.
 */
const MAX = {
  title: 64,
  firstName: 128,
  lastName: 128,
  specialty: 128,
  practiceName: 256,
  city: 128,
} as const

/** `" 12 3456 789 "` → `"123456789"`. Whitespace only; anything else survives to fail the check. */
function digitsOnly(value: string): string {
  return value.replace(/\s+/g, "")
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

/**
 * Every problem with the body at once, or the parsed value.
 *
 * All of them, never the first: a form that reports one bad field per submit makes somebody who
 * mistyped two numbers submit twice to find that out.
 */
export function parseOnboarding(body: unknown): ParseResult {
  const root = asObject(body)
  const doctorRaw = asObject(root.doctor)
  const practiceRaw = asObject(root.practice)
  const errors: FieldError[] = []

  const required = (
    field: string,
    raw: unknown,
    max: number,
    label: string
  ): string => {
    const value = asString(raw)
    if (!value) {
      errors.push({ field, message: `${label} ist erforderlich.` })
      return ""
    }
    if (value.length > max) {
      errors.push({
        field,
        message: `${label} darf höchstens ${max} Zeichen lang sein.`,
      })
      return value.slice(0, max)
    }
    return value
  }

  const nineDigits = (field: string, raw: unknown, label: string): string => {
    const value = digitsOnly(asString(raw))
    if (!value) {
      errors.push({ field, message: `${label} ist erforderlich.` })
      return ""
    }
    if (!/^\d{9}$/.test(value)) {
      errors.push({
        field,
        message: `${label} besteht aus genau neun Ziffern.`,
      })
    }
    return value
  }

  const title = asString(doctorRaw.title)
  if (title.length > MAX.title) {
    errors.push({
      field: "doctor.title",
      message: `Der Titel darf höchstens ${MAX.title} Zeichen lang sein.`,
    })
  }

  const doctor: DoctorInput = {
    // Blank becomes `null`, not `""`. The column is nullable precisely so that "no academic title"
    // is a stored answer rather than an empty string nobody can distinguish from "not filled in".
    title: title ? title.slice(0, MAX.title) : null,
    firstName: required(
      "doctor.firstName",
      doctorRaw.firstName,
      MAX.firstName,
      "Der Vorname"
    ),
    lastName: required(
      "doctor.lastName",
      doctorRaw.lastName,
      MAX.lastName,
      "Der Nachname"
    ),
    lanr: nineDigits("doctor.lanr", doctorRaw.lanr, "Die LANR"),
    specialty: required(
      "doctor.specialty",
      doctorRaw.specialty,
      MAX.specialty,
      "Die Fachrichtung"
    ),
  }

  const plzRaw = digitsOnly(asString(practiceRaw.plz))
  if (!plzRaw) {
    errors.push({ field: "practice.plz", message: "Die PLZ ist erforderlich." })
  } else if (!/^\d{5}$/.test(plzRaw)) {
    errors.push({
      field: "practice.plz",
      message: "Die PLZ besteht aus genau fünf Ziffern.",
    })
  }

  const practice: PracticeInput = {
    practiceName: required(
      "practice.practiceName",
      practiceRaw.practiceName,
      MAX.practiceName,
      "Der Praxisname"
    ),
    bsnr: nineDigits("practice.bsnr", practiceRaw.bsnr, "Die BSNR"),
    city: required("practice.city", practiceRaw.city, MAX.city, "Der Ort"),
    plz: plzRaw,
  }

  if (errors.length > 0) return { ok: false, errors }
  return { ok: true, value: { doctor, practice } }
}
