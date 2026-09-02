/**
 * The one API call this site shows, and the excerpt of what it answers with.
 *
 * Both are lifted from `docs/api/PARTNER_API.md` — the versioned contract — rather than
 * written for the brochure. A marketing snippet that does not match the real endpoint is
 * worse than no snippet: the reader who tries it is the reader who was going to
 * integrate, and their first experience of the product is a 404.
 *
 * Deliberately *not* the demo endpoint. `/api/demo/audit` is the web application's own
 * and is session-shaped; `/api/v1/audit/single` is the partner surface, which is what an
 * integrator reading this section is evaluating.
 *
 * The response excerpt carries **no rule counts**. The contract's own worked example
 * prints them and is pinned by `test_published_numbers.py` for exactly that reason; a
 * second unpinned copy on a marketing page is how the two drift apart. Where a figure is
 * genuinely needed in the copy, it comes from `engine-facts.ts`.
 */

/**
 * The engine's host, as a shell variable rather than a literal.
 *
 * It read `https://api.azmoth.com` and that host has **no DNS record** — see `lib/site.ts`, where
 * two links to it were removed for the same reason. A literal is worse here than in a link,
 * because this block has a copy button next to it: the reader most likely to use it is an
 * integrator evaluating whether the API is real, and what they would get back is a name-resolution
 * failure. That is the exact impression this section exists to prevent.
 *
 * A placeholder is also simply more correct for a snippet that already parameterises the key. An
 * integrator is issued a base URL along with their credentials; the command shows the *shape* of
 * the call, which is what it was ever able to show. When the host is live, either inline it again
 * or keep the variable — but do not print a hostname that does not answer.
 */
const HOST = "$AZMOTH_API";

export const CURL_EXAMPLE = `curl -X POST ${HOST}/api/v1/audit/single \\
     -H "X-API-Key: $AZMOTH_KEY" \\
     -F "file=@00004711_20260726_ADL_000001_padx.xml"`;

export const RESPONSE_EXAMPLE = `{
  "source_name": "00004711_20260726_ADL_000001_padx.xml",
  "positions": [ /* Verdikt, Begründung, Beweis, Beträge */ ],
  "findings":  [ /* gesetzliche Grundlage, Regel-ID */ ],

  "claimed_total_eur":   "251.54",  // gefordert
  "confirmed_fine_eur":   "24.25",  // grün — belegt korrekt
  "confirmed_wrong_eur":  "88.49",  // rot  — belegt falsch
  "unconfirmed_eur":     "138.80",  // gelb — keine Regel greift

  "coverage_ratio": 0.4482,         // beurteilbarer Anteil
  "receipt_hash": "bd8abb06ef7f0a4b…",
  "catalog_version": "goae_official_snapshot_2026-07-25"
}`;
