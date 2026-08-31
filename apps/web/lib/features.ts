/**
 * Which optional surfaces this deployment shows.
 *
 * There is one flag here today and it exists for a product reason rather than a technical one:
 * `/rules` is the internal workflow for verifying machine-extracted GOÄ rules. It is real work and
 * it is valuable — every rule a reviewer confirms moves a position out of the *unbestätigt* bucket
 * and into a verdict the engine is allowed to assert — but it is **our** work, not a pilot
 * customer's. A billing expert who finds it reads it as an invitation to correct the engine, and
 * the pilot's whole proposition is that the engine's verdicts are not something a customer tunes.
 *
 * ## Default off
 *
 * A flag that has to be remembered is a flag that ships wrong once. The pilot deployment is the
 * one that must never show this screen, so *not configuring anything* is the state that hides it,
 * and the deployments that want the tool — a developer's machine, the internal instance — opt in.
 * The failure mode of forgetting is then a missing internal tool that somebody notices in a
 * minute, rather than a customer-facing screen nobody notices for a quarter.
 *
 * ## Why `NEXT_PUBLIC_`
 *
 * The sidebar is a client component, so the value has to survive into the browser bundle to keep a
 * nav entry from rendering. That is safe here because **this flag is not a security boundary and
 * must not be mistaken for one.** `/rules` is already behind `requireSession()` in the `(app)`
 * layout and behind the signup allowlist before that; the flag decides visibility, not access.
 * What actually stops a request is `notFound()` on the page and on the two API routes that serve
 * it, both of which run on the server and neither of which trusts this constant to have been
 * honoured by the client.
 *
 * `NEXT_PUBLIC_*` is inlined at build time, so a change requires a rebuild — correct for a flag
 * that describes what a deployment *is* rather than something an operator toggles at runtime.
 */

/**
 * Whether the GOÄ rule-verification workbench (`/rules`) is part of this deployment.
 *
 * Opt-in, and strictly: anything other than `"1"` or `"true"` is off, so a typo, an empty string
 * or a stray `"false"` all fail closed rather than exposing the screen.
 */
export const RULE_REVIEW_ENABLED =
  process.env.NEXT_PUBLIC_RULE_REVIEW_ENABLED === "1" ||
  process.env.NEXT_PUBLIC_RULE_REVIEW_ENABLED === "true"
