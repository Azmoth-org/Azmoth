/**
 * Where to send somebody after they sign in.
 *
 * `/login?next=…` carries the screen the middleware interrupted, so signing in resumes the work
 * instead of dumping every reader on the dashboard. That parameter is attacker-controlled — it is
 * in a URL anyone can send — so it is *validated*, never merely used.
 *
 * The rule is: a same-site absolute path, and nothing else. `//evil.example` is rejected explicitly
 * because it is a protocol-relative URL that starts with a slash and would otherwise pass the naive
 * check; so is anything containing a backslash, which some browsers normalise to a slash. What is
 * left cannot leave this origin, which is the property an open-redirect bug on a login page
 * destroys — and a phishing link that genuinely came from the application's own domain is the most
 * convincing kind there is.
 */

/** The dashboard. Where a sign-in with no destination lands. */
export const DEFAULT_REDIRECT = "/"

export function safeNext(next: string | undefined | null): string {
  if (!next) return DEFAULT_REDIRECT
  if (!next.startsWith("/")) return DEFAULT_REDIRECT
  if (next.startsWith("//")) return DEFAULT_REDIRECT
  if (next.includes("\\")) return DEFAULT_REDIRECT
  // The auth screens themselves, which would bounce straight back here and look like a loop.
  if (next === "/login" || next === "/signup") return DEFAULT_REDIRECT
  return next
}
