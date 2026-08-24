/**
 * Small display helpers the dashboard's activity rows need, and nothing else.
 *
 * The status badge maps used to live here and now live in `lib/status.ts`, because the list pages
 * paint the same statuses and two colour maps for one enum is how a reader ends up learning two
 * colour languages for one fact. They are re-exported so the dashboard's own imports read as one
 * module.
 */

export {
  BATCH_STATUS,
  PROPOSAL_STATUS,
  statusPresentation,
  type StatusPresentation,
} from "@/lib/status"

/**
 * `prop_ed6e3e687ce24f16` → `prop_ed6e3e68…`.
 *
 * Truncated for a dashboard row and never for anything else. The full id is the link's target and
 * the row's `title`, so a reader who needs the whole thing can still get at it. Where the value has
 * to *leave* the browser — a ticket, an email to a Rechnungsprüfer, a `psql` query — the list pages
 * use `CopyableHash` instead, which copies the untruncated string.
 */
export function shortId(id: string, keep = 13): string {
  return id.length <= keep ? id : `${id.slice(0, keep)}…`
}

/** `3` → `"3 Dateien"`, and `1` → `"1 Datei"`. */
export function fileCount(count: number | null | undefined): string {
  const n = typeof count === "number" && Number.isFinite(count) ? count : 0
  return n === 1 ? "1 Datei" : `${n} Dateien`
}
