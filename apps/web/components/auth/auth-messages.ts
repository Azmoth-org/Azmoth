import { MIN_PASSWORD_LENGTH } from "@/lib/password-policy"

/**
 * Better Auth's error codes, in German.
 *
 * The library answers with a stable `code` and an English `message`. Rendering the English one on a
 * German compliance tool is the failure this map exists to prevent — and the codes are the right
 * thing to translate rather than the prose, because the prose is the library's to change between
 * versions and the codes are its contract.
 *
 * The codes below are enumerated from the installed `better-auth@1.7.1` itself (`grep -r
 * BASE_ERROR_CODES` / `ORGANIZATION_ERROR_CODES` under `node_modules/@better-auth/core` and
 * `node_modules/better-auth`), not guessed — a code this map does not recognise falls through to
 * the honest fallback at the bottom rather than to a wrong sentence.
 *
 * **Sign-in never says which half was wrong.** `INVALID_EMAIL_OR_PASSWORD` and a nonexistent
 * account produce the same sentence, deliberately: a login form that distinguishes them is a tool
 * for confirming whether a given address has an account here, and on an application whose user list
 * is a list of people auditing medical invoices that is not a question to answer for free.
 */

/**
 * The one code `signup-form.tsx` reacts to on its own, beyond translating it: a duplicate address
 * is the one failure on that form with a next step ("Stattdessen anmelden") rather than just a
 * sentence. Exported so the form can recognise it without repeating the string.
 */
export const DUPLICATE_EMAIL_CODE = "USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL"

const DUPLICATE_EMAIL_MESSAGE =
  "Diese E-Mail-Adresse ist bereits registriert. Bitte melden Sie sich an."

const MESSAGES: Record<string, string> = {
  INVALID_EMAIL_OR_PASSWORD: "E-Mail-Adresse oder Passwort ist falsch.",
  INVALID_EMAIL: "Diese E-Mail-Adresse ist nicht gültig.",
  INVALID_PASSWORD: "E-Mail-Adresse oder Passwort ist falsch.",
  USER_NOT_FOUND: "E-Mail-Adresse oder Passwort ist falsch.",
  /**
   * The one sign-up actually throws — `USER_ALREADY_EXISTS` (no suffix) is a code this library
   * defines but its `sign-up/email` route never raises; only the longer name below comes back over
   * the wire. It stayed mapped here too, as a harmless synonym, in case a future version starts
   * throwing the shorter one — but it was the reason a duplicate-email sign-up used to fall through
   * to the generic fallback message below instead of this one.
   */
  [DUPLICATE_EMAIL_CODE]: DUPLICATE_EMAIL_MESSAGE,
  USER_ALREADY_EXISTS: DUPLICATE_EMAIL_MESSAGE,
  USER_EMAIL_NOT_FOUND: "E-Mail-Adresse oder Passwort ist falsch.",
  PASSWORD_TOO_SHORT: `Das Passwort ist zu kurz. Es sind mindestens ${MIN_PASSWORD_LENGTH} Zeichen erforderlich.`,
  PASSWORD_TOO_LONG: "Das Passwort ist zu lang.",
  /**
   * Should never reach a person on this deployment — `requireEmailVerification` is off (see
   * `lib/auth.ts`), so no sign-in ever raises it. Mapped anyway, in the pilot's own terms, in case a
   * stale account or a future config change ever makes it happen for real.
   */
  EMAIL_NOT_VERIFIED:
    "Pilotbetrieb: E-Mail-Verifizierung deaktiviert. Bitte schreiben Sie an " +
    "support@azmoth.com, falls Sie keine Einladung erhalten haben.",
  SESSION_EXPIRED:
    "Die Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
  PROVIDER_NOT_FOUND:
    "Die Anmeldung mit Google ist auf diesem Server nicht eingerichtet.",
  SOCIAL_ACCOUNT_ALREADY_LINKED:
    "Dieses Google-Konto ist bereits mit einem anderen Konto verknüpft.",
  // Both from the `organization()` plugin — `signup-form.tsx` calls `organization.create` in the
  // same submit as `signUp.email`, so a name collision surfaces through this same map.
  ORGANIZATION_ALREADY_EXISTS: "Eine Organisation mit diesem Namen besteht bereits.",
  ORGANIZATION_SLUG_ALREADY_TAKEN:
    "Dieser Organisationsname ist bereits vergeben. Bitte wählen Sie einen anderen.",
  /**
   * Ours, not the library's — `lib/auth-allowlist.ts` raises it when an address is not on
   * `SIGNUP_ALLOWLIST`. It is here for the same reason every other entry is: without a mapping the
   * form would render the generic fallback below and a legitimate pilot participant would have no
   * idea that the fix is to ask us to add their address.
   *
   * Deliberately identical for "no allowlist configured" and "address not on it". A stranger must
   * not be able to probe for a misconfigured deployment through a sign-up form; the operator sees
   * the distinction in the server log.
   */
  SIGNUP_NOT_ALLOWED:
    "Die Registrierung ist derzeit auf freigeschaltete Pilot-Teilnehmer beschränkt. " +
    "Diese E-Mail-Adresse ist nicht freigegeben. Wenn Sie am Pilotprogramm teilnehmen " +
    "möchten, fordern Sie bitte einen Zugang an — wir schalten Ihre Adresse dann frei.",
}

/** The German sentence for a Better Auth failure, or a truthful fallback when the code is new. */
export function authErrorMessage(
  error: { code?: string; message?: string } | null | undefined
): string {
  const code = error?.code
  if (code && code in MESSAGES) return MESSAGES[code]!
  // Not the library's English message: a sentence in the wrong language reads as a bug in the
  // application rather than as a problem with what was typed, and it can name internals. Names a
  // way out (support@azmoth.com) rather than just "try again", because a code missing from
  // `MESSAGES` is by definition one this map's author never anticipated.
  return (
    "Anmeldung momentan nicht möglich. Bitte versuchen Sie es erneut " +
    "oder schreiben Sie an support@azmoth.com."
  )
}

/** The same, for a request that never reached the server at all. */
export const NETWORK_ERROR_MESSAGE =
  "Der Server ist nicht erreichbar. Bitte prüfen Sie die Verbindung und versuchen Sie es erneut."

/**
 * The other half: the `?error=<code>` a failed OAuth round-trip comes back with.
 *
 * These are **not** the codes above. Better Auth answers an API call with a SCREAMING_SNAKE `code`
 * in a JSON body, but the Google callback is a browser redirect — it cannot return a body, so it
 * appends a lowercase, URL-safe code to `errorCallbackURL` instead. Two vocabularies for two
 * transports, and a single map covering both would quietly translate neither.
 *
 * Google's own failures arrive here too, unchanged, because the callback forwards the provider's
 * `error` parameter as it stands. `access_denied` is the one a person actually causes — it is what
 * "Abbrechen" on Google's consent screen sends — and it is not an error to apologise for.
 *
 * ## `account_not_linked` is the one worth reading twice
 *
 * It means: this Google address already has a password account here, and Better Auth will not
 * attach a Google identity to a local user whose own email address was never verified. Since this
 * deployment has no mail transport, *no* password account is verified, so this is what every such
 * collision produces. It is a deliberate gate, not a defect — `lib/auth.ts` explains what relaxing
 * it would allow — and the only useful thing to tell the person in front of it is to use the
 * password they already have.
 */
const OAUTH_MESSAGES: Record<string, string> = {
  access_denied: "Die Anmeldung mit Google wurde abgebrochen.",
  account_not_linked:
    "Für diese E-Mail-Adresse besteht hier bereits ein Konto mit Passwort. " +
    "Bitte melden Sie sich mit Ihrem Passwort an.",
  unable_to_link_account:
    "Das Google-Konto konnte nicht mit einem Konto in dieser Anwendung verknüpft werden.",
  account_already_linked_to_different_user:
    "Dieses Google-Konto ist bereits mit einem anderen Konto verknüpft.",
  email_does_not_match:
    "Die E-Mail-Adresse des Google-Kontos stimmt nicht mit der des vorhandenen Kontos überein.",
  email_not_found:
    "Google hat keine E-Mail-Adresse übermittelt. Eine Anmeldung ist so nicht möglich.",
  email_not_verified:
    "Die E-Mail-Adresse dieses Google-Kontos ist nicht bestätigt.",
  signup_disabled:
    "Für diese E-Mail-Adresse besteht noch kein Konto, und die Registrierung über Google ist deaktiviert.",
  unable_to_create_user:
    "Das Konto konnte nicht angelegt werden. Bitte versuchen Sie es erneut.",
  unable_to_create_session:
    "Die Anmeldung war erfolgreich, die Sitzung konnte aber nicht erstellt werden. Bitte versuchen Sie es erneut.",
  // The state cookie is how the callback proves the response belongs to the request that started
  // it. Gone means the flow took too long, or the browser dropped the cookie — starting over is
  // genuinely the fix, so the sentence says that rather than blaming anyone.
  state_not_found:
    "Die Anmeldung mit Google ist abgelaufen. Bitte starten Sie sie erneut.",
  invalid_callback_request:
    "Die Antwort von Google war unvollständig. Bitte versuchen Sie es erneut.",
  no_code:
    "Die Antwort von Google war unvollständig. Bitte versuchen Sie es erneut.",
  invalid_code:
    "Die Antwort von Google konnte nicht überprüft werden. Bitte versuchen Sie es erneut.",
  oauth_provider_not_found:
    "Die Anmeldung mit Google ist auf diesem Server nicht eingerichtet.",
  unable_to_get_user_info:
    "Die Kontodaten konnten nicht von Google abgerufen werden.",
}

/**
 * The German sentence for an OAuth callback failure, or `null` when there was none.
 *
 * `null` rather than a fallback sentence for a *missing* code, because the caller is a page reading
 * a query parameter that is usually absent — "no error" has to be distinguishable from "an error I
 * do not recognise", and only the second one deserves a red box.
 *
 * The code itself is never rendered. It is an internal identifier, it can be anything at all since
 * it partly comes from Google, and putting attacker-influenced text from a URL into the page is how
 * a login screen ends up displaying whatever a phishing link put there.
 */
export function oauthErrorMessage(
  code: string | undefined | null
): string | null {
  if (!code) return null
  if (code in OAUTH_MESSAGES) return OAUTH_MESSAGES[code]!
  return "Die Anmeldung mit Google ist fehlgeschlagen. Bitte versuchen Sie es erneut."
}
