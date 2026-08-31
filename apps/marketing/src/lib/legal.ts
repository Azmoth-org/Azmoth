/**
 * The marker every unfilled legal detail carries, and the switch that keeps the pages
 * carrying it out of search results.
 *
 * The Impressum and the Datenschutzerklärung ship with placeholders rather than with
 * plausible-looking invented details. Both halves of that are deliberate: an Impressum
 * naming a company that does not exist at an address nobody occupies is a worse legal
 * position than an obviously unfinished one, and a `TODO` in a source comment is
 * invisible to the person who has to sign it off.
 *
 * So the marker does three things at once. It is visible in the rendered German text; it
 * raises a banner at the top of the page saying the page is a draft; and it sets
 * `noindex`, so an unfinished Impressum cannot be the first thing a search engine learns
 * about this company.
 *
 * When the real details land, the string disappears from `messages/de.json` and all
 * three consequences disappear with it — one edit in one file, with nothing to remember
 * to switch on afterwards.
 */
export const PLACEHOLDER = "[BITTE ERGÄNZEN]";

/**
 * Whether a catalogue subtree still contains an unfilled field.
 *
 * Serialising and searching the whole subtree, rather than walking it: the shape differs
 * between the two pages (the Impressum has `zeilen`, the privacy notice has `absaetze`)
 * and a structural walk would need updating for a third. What matters is only whether
 * the marker survives anywhere below the node.
 */
export function hasPlaceholder(subtree: unknown): boolean {
  return JSON.stringify(subtree ?? null).includes(PLACEHOLDER);
}
