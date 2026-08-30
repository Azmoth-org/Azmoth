/**
 * Who may create an account. **Server-only.**
 *
 * Sign-up used to be open: anyone who could reach `/signup` got an account and an organisation.
 * That was acceptable while the deployment was a laptop holding synthetic fixtures, and stops being
 * acceptable the moment the application answers on a public hostname — at which point the gap is
 * not "no authorisation model" but "a stranger can provision themselves a tenant in a system built
 * for clinical billing data". `docs/compliance/PRIVATE_DATA_WARNING.md` tracks it as the first of
 * the four open items under *Access control*.
 *
 * This closes it the smallest way that actually closes it: a list of permitted addresses and
 * domains in the environment, checked before a user row is created. It is not an invitation system
 * — there is no SMTP relay to send an invitation with, and a pilot of two named reviewers does not
 * need one. What it is, is a door that is shut by default.
 *
 * ## The default is closed, and that is the whole design
 *
 * `SIGNUP_ALLOWLIST` unset means **nobody may register**, not everybody. A gate whose unset state
 * is "open" is a gate that is open on every deployment where someone forgot the variable, and the
 * failure is silent and permanent. So an unset variable refuses every sign-up with a message that
 * says what to do, and the operator has to state who is allowed in — which is the decision this
 * exists to force somebody to make.
 *
 * The one exception is development, where an unset list is permissive and says so in the server
 * log. `pnpm dev` and the test suite must not require configuration to create the first account,
 * and `NODE_ENV` is the only signal available that distinguishes the two.
 *
 * ## What an entry may be
 *
 *     SIGNUP_ALLOWLIST="anna@praxis-beispiel.de, @abrechnung-nord.de, dr.b@praxis-beispiel.de"
 *
 * An entry starting with `@` is a **domain**: every address at that domain is admitted. Anything
 * else is one **exact address**. Comparison is case-insensitive and trims whitespace, because an
 * operator pasting a list out of an email will produce both.
 *
 * A domain entry is a real widening — `@gmail.com` would readmit the whole internet — so it exists
 * for the case it was asked for (a billing centre whose staff all share a domain) and the log line
 * on refusal names the address so a legitimate person's failure is diagnosable in one grep.
 *
 * ## What this is not
 *
 * It is authentication's front door, not an authorisation model. Every account that gets through
 * still has every permission inside its own practice: there are no roles, and a reviewer and an
 * administrator are the same thing. That gap is deliberate for a two-person pilot and is tracked
 * in the same document. This file only decides who may exist.
 */

/** One parsed rule: an exact address, or a domain that admits everything at it. */
type Rule =
  | { kind: "address"; value: string }
  | { kind: "domain"; value: string }

function parse(raw: string): Rule[] {
  return raw
    .split(/[,\s]+/)
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean)
    .map((entry) =>
      entry.startsWith("@")
        ? ({ kind: "domain", value: entry.slice(1) } as const)
        : ({ kind: "address", value: entry } as const)
    )
}

/**
 * The configured rules, or `null` when the variable is unset or empty.
 *
 * `null` and `[]` mean different things and both are reachable: unset is "nobody decided", an
 * explicitly empty string is "somebody decided nobody". Both refuse in production; only the first
 * is permissive in development.
 */
export function signupAllowlist(): Rule[] | null {
  const raw = process.env.SIGNUP_ALLOWLIST
  if (raw === undefined) return null
  const rules = parse(raw)
  return rules.length > 0 ? rules : []
}

export type SignupDecision =
  | { allowed: true }
  | { allowed: false; reason: "not_configured" | "not_listed" }

/**
 * May this address create an account?
 *
 * Pure and synchronous so it can be unit-tested without a database or a Better Auth instance —
 * the hook in `lib/auth.ts` is a two-line wrapper around this, which keeps the rule itself
 * somewhere a test can reach.
 */
export function mayRegister(
  email: string,
  { isProduction = process.env.NODE_ENV === "production" } = {}
): SignupDecision {
  const rules = signupAllowlist()

  if (rules === null) {
    // Unset. Open in development so nothing needs configuring to create the first account; closed
    // in production, because an unset gate that defaults to open is one nobody notices is open.
    return isProduction ? { allowed: false, reason: "not_configured" } : { allowed: true }
  }

  const address = email.trim().toLowerCase()
  const domain = address.slice(address.lastIndexOf("@") + 1)

  const listed = rules.some((rule) =>
    rule.kind === "address" ? rule.value === address : rule.value === domain
  )

  return listed ? { allowed: true } : { allowed: false, reason: "not_listed" }
}

/**
 * The stable code the refusal travels under.
 *
 * Better Auth's own codes are its contract and are translated by code rather than by prose in
 * `components/auth/auth-messages.ts`; this one is ours and joins them there, so the sign-up form
 * renders the German sentence below instead of falling through to the generic
 * "Die Anmeldung ist fehlgeschlagen". Without a code the message would be correct on the wire and
 * invisible on the screen.
 */
export const SIGNUP_REFUSED_CODE = "SIGNUP_NOT_ALLOWED"

/**
 * What the sign-up form is told. German, and deliberately the same sentence for both refusals.
 *
 * A visitor must not be able to tell "this deployment has no allowlist configured" from "your
 * address is not on it" — the first is a fact about our operations that a stranger has no business
 * learning from a form, and telling the two apart would let someone probe for a misconfigured
 * deployment. The distinction is in the server log instead, where the operator can see it.
 *
 * It names the pilot path rather than dead-ending, because the most likely person to hit this is
 * exactly the customer the gate exists to make room for.
 */
export const SIGNUP_REFUSED_MESSAGE =
  "Die Registrierung ist derzeit auf freigeschaltete Pilot-Teilnehmer beschränkt. " +
  "Diese E-Mail-Adresse ist nicht freigegeben. Wenn Sie am Pilotprogramm teilnehmen " +
  "möchten, fordern Sie bitte einen Zugang an — wir schalten Ihre Adresse dann frei."
