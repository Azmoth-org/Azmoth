/**
 * The name a practice's organisation is given when nobody has typed one yet.
 *
 * This exists because an account without an organisation is an account that cannot use the
 * product at all. `lib/engine.ts` refuses every proxied call whose session carries no
 * `activeOrganizationId` with a `403`, and the engine refuses it again on its own side — so a user
 * who reached the dashboard before choosing a practice name saw every panel fail at once. The
 * `user.create.after` hook in `lib/auth.ts` closes that by creating one for *every* account at the
 * moment the account comes into existence, and this module is where the name for it comes from.
 *
 * ## Why the email domain
 *
 * It is the only thing known at `user.create.after`. There is no session yet, no form state and no
 * onboarding answer — just the address that was registered. A practice signing up as
 * `dr.mueller@praxis-mueller.de` gets "Praxis Mueller", which is recognisable in the organisation
 * rail on the first load and is very often simply correct.
 *
 * **It is a placeholder with a real name's shape, not a claim.** `/onboarding` renames it (see
 * `app/api/onboarding/route.ts`, which updates the active organisation rather than creating a
 * second one), and the rail can rename it too. Nothing downstream reads meaning into it: the
 * tenant boundary is the organisation *id*, never its name.
 *
 * ## What it refuses to guess
 *
 * A domain that cannot name a practice falls back to `Organisation von <email>` rather than to
 * something invented. "Invalid" here means: no `@`, an empty domain, a single label with no dot
 * (`user@localhost` — a hostname, not an organisation), or a domain whose labels carry no letters
 * at all (`user@192.168.0.1`). Each of those would otherwise produce a name that looks derived from
 * something when it is not, and a wrong-looking name is worse than an obviously provisional one.
 *
 * The public suffix is dropped because nobody calls their practice "Praxis Mueller De". Only the
 * last label goes — this is deliberately not a public-suffix-list lookup, which would be a
 * dependency and a data file to keep current for a string the user is invited to change.
 */

/** How long an organisation name may be. Past this it is truncated at a word boundary. */
const MAX_NAME_LENGTH = 64

/**
 * Non-alphanumeric runs become one space. Unicode-aware on purpose: `[^a-z0-9]` would shred
 * "münchen" into "m nchen", and German practice domains are the common case here.
 */
const NON_ALPHANUMERIC = /[^\p{L}\p{N}]+/gu

/** At least one letter. A label of pure digits is an IP octet or a ticket number, not a name. */
const HAS_LETTER = /\p{L}/u

/**
 * Title-case each word, collapse everything else to single spaces, and cap the length.
 *
 * Truncation happens at a word boundary when there is one, because "Gemeinschaftspraxis Dr Med
 * Mue" reads as corrupted while a shorter clean name reads as a name.
 */
export function sanitizeOrganizationName(raw: string): string {
  const words = raw
    .replace(NON_ALPHANUMERIC, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())

  const joined = words.join(" ")
  if (joined.length <= MAX_NAME_LENGTH) return joined

  const clipped = joined.slice(0, MAX_NAME_LENGTH)
  const lastSpace = clipped.lastIndexOf(" ")
  return (lastSpace > 0 ? clipped.slice(0, lastSpace) : clipped).trim()
}

/**
 * The organisation name for a freshly registered address.
 *
 * `praxis-mueller.de` → `Praxis Mueller`. `user@localhost` → `Organisation von user@localhost`.
 * Never throws and never returns an empty string: this runs inside account creation, and a name
 * this function could not produce would mean an account that could not be created.
 */
export function organizationNameForEmail(email: string): string {
  const address = (email ?? "").trim()

  const at = address.lastIndexOf("@")
  if (at < 0) return fallbackFor(address)

  const domain = address.slice(at + 1).trim().toLowerCase()
  // A single label is a hostname on a local network, not an organisation. `localhost` is the one
  // that actually shows up — in development, and in any deployment addressed by container name.
  const labels = domain.split(".").filter(Boolean)
  if (labels.length < 2) return fallbackFor(address)

  // Everything but the public suffix. A subdomain is kept: `mail.praxis-mueller.de` naming itself
  // "Mail Praxis Mueller" is odd but honest, and the user renames it in one click.
  const derived = sanitizeOrganizationName(labels.slice(0, -1).join(" "))
  if (!derived || !HAS_LETTER.test(derived)) return fallbackFor(address)

  return derived
}

/**
 * `Organisation von dr.mueller@localhost` — the address printed as an address.
 *
 * **Deliberately not routed through `sanitizeOrganizationName`.** That function replaces every
 * non-alphanumeric character with a space and title-cases the result, which is right for a domain
 * and wrong here: it turns `user@localhost` into "Organisation Von User Localhost", a string that
 * reads like a name somebody chose rather than like the placeholder it is. The whole value of this
 * fallback is that it is visibly provisional and contains the address it was derived from, so the
 * reader knows immediately what to rename.
 *
 * Only the two things that must hold are enforced: nothing unprintable reaches the name, and the
 * length cap applies. The final `|| "Organisation"` covers an address that is empty or entirely
 * unprintable — which Better Auth's own email validation should already have refused, and which is
 * handled anyway because the alternative is an organisation whose name is the empty string.
 */
function fallbackFor(address: string): string {
  const printable = address.replace(/[\p{C}]/gu, "").trim()
  const name = printable ? `Organisation von ${printable}` : ""
  return name.slice(0, MAX_NAME_LENGTH).trim() || "Organisation"
}
