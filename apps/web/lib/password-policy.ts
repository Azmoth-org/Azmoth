/**
 * The pilot's password policy: at least {@link MIN_PASSWORD_LENGTH} characters, and at least
 * {@link REQUIRED_CLASS_COUNT} of the four character classes below.
 *
 * One function computes it and both `signup-form.tsx` consumers — the live strength meter and the
 * submit-time rejection message — call it, so the two can't quietly disagree about what "strong
 * enough" means.
 *
 * **This is enforced here, client-side, rather than by Better Auth.** The installed version
 * (`better-auth@1.7.1`) only exposes `minPasswordLength` / `maxPasswordLength` on
 * `emailAndPassword` — there is no character-class option to hand it (see that package's
 * `EmailAndPasswordOptions` type). `lib/auth.ts` still enforces the length floor server-side, so a
 * request that bypasses this form entirely is still rejected for a too-short password; only the
 * class-diversity rule lives only here.
 */
export const MIN_PASSWORD_LENGTH = 12

const REQUIRED_CLASS_COUNT = 3

const CLASS_PATTERNS = {
  Kleinbuchstaben: /[a-z]/,
  Großbuchstaben: /[A-Z]/,
  Ziffern: /[0-9]/,
  Sonderzeichen: /[^A-Za-z0-9]/,
} as const

type PasswordClass = keyof typeof CLASS_PATTERNS

const CLASS_NAMES = Object.keys(CLASS_PATTERNS) as PasswordClass[]

export type PasswordCheck = {
  meetsLength: boolean
  matchedClasses: PasswordClass[]
  missingClasses: PasswordClass[]
  satisfiesPolicy: boolean
  strength: "Schwach" | "Okay" | "Stark"
}

export function checkPassword(password: string): PasswordCheck {
  const matchedClasses = CLASS_NAMES.filter((name) => CLASS_PATTERNS[name].test(password))
  const missingClasses = CLASS_NAMES.filter((name) => !matchedClasses.includes(name))
  const meetsLength = password.length >= MIN_PASSWORD_LENGTH
  const satisfiesPolicy = meetsLength && matchedClasses.length >= REQUIRED_CLASS_COUNT

  // "Stark" asks for more than the bare minimum on top of the policy, so the meter still has
  // somewhere to go once the password merely passes — a password that only just clears the floor
  // reads as "Okay", not as the same "Stark" a much longer, more varied one earns.
  const strength: PasswordCheck["strength"] =
    !meetsLength || matchedClasses.length <= 1
      ? "Schwach"
      : satisfiesPolicy && password.length >= MIN_PASSWORD_LENGTH + 4
        ? "Stark"
        : "Okay"

  return { meetsLength, matchedClasses, missingClasses, satisfiesPolicy, strength }
}

/** The German sentence naming exactly what a rejected password is still missing, or `""` if none. */
export function passwordPolicyMessage(password: string): string {
  const check = checkPassword(password)
  if (!check.meetsLength) {
    return `Das Passwort muss mindestens ${MIN_PASSWORD_LENGTH} Zeichen lang sein.`
  }
  if (!check.satisfiesPolicy) {
    const needed = REQUIRED_CLASS_COUNT - check.matchedClasses.length
    return (
      `Das Passwort braucht noch ${needed === 1 ? "eine weitere Zeichenart" : `${needed} weitere Zeichenarten`} von: ` +
      `${check.missingClasses.join(", ")}.`
    )
  }
  return ""
}
