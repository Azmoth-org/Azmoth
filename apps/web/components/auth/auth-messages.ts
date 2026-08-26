/**
 * Better Auth's error codes, in German.
 *
 * The library answers with a stable `code` and an English `message`. Rendering the English one on a
 * German compliance tool is the failure this map exists to prevent — and the codes are the right
 * thing to translate rather than the prose, because the prose is the library's to change between
 * versions and the codes are its contract.
 *
 * **Sign-in never says which half was wrong.** `INVALID_EMAIL_OR_PASSWORD` and a nonexistent
 * account produce the same sentence, deliberately: a login form that distinguishes them is a tool
 * for confirming whether a given address has an account here, and on an application whose user list
 * is a list of people auditing medical invoices that is not a question to answer for free.
 */
const MESSAGES: Record<string, string> = {
  INVALID_EMAIL_OR_PASSWORD: "E-Mail-Adresse oder Passwort ist falsch.",
  INVALID_EMAIL: "Diese E-Mail-Adresse ist nicht gültig.",
  INVALID_PASSWORD: "E-Mail-Adresse oder Passwort ist falsch.",
  USER_NOT_FOUND: "E-Mail-Adresse oder Passwort ist falsch.",
  USER_ALREADY_EXISTS: "Für diese E-Mail-Adresse besteht bereits ein Konto.",
  USER_EMAIL_NOT_FOUND: "E-Mail-Adresse oder Passwort ist falsch.",
  PASSWORD_TOO_SHORT: "Das Passwort ist zu kurz. Es sind mindestens 12 Zeichen erforderlich.",
  PASSWORD_TOO_LONG: "Das Passwort ist zu lang.",
  EMAIL_NOT_VERIFIED: "Diese E-Mail-Adresse ist noch nicht bestätigt.",
  SESSION_EXPIRED: "Die Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
}

/** The German sentence for a Better Auth failure, or a truthful fallback when the code is new. */
export function authErrorMessage(error: { code?: string; message?: string } | null | undefined): string {
  const code = error?.code
  if (code && code in MESSAGES) return MESSAGES[code]!
  // Not the library's English message: a sentence in the wrong language reads as a bug in the
  // application rather than as a problem with what was typed, and it can name internals.
  return "Die Anmeldung ist fehlgeschlagen. Bitte versuchen Sie es erneut."
}

/** The same, for a request that never reached the server at all. */
export const NETWORK_ERROR_MESSAGE =
  "Der Server ist nicht erreichbar. Bitte prüfen Sie die Verbindung und versuchen Sie es erneut."
