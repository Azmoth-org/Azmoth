/**
 * How the dashboard labels a status, and nothing else.
 *
 * Display only. Nothing here computes anything a decision depends on, and no amount is touched —
 * the dashboard shows counts and statuses, never money. The euro figures live on the audit screens,
 * where `lib/padnext/format.ts` states the rule they follow.
 *
 * The German labels for a batch status also exist in `components/padnext/batch-progress.tsx`, and
 * that is deliberate rather than an oversight. That module is a client component inside the batch
 * workbench, so importing its map here would pull the workbench's client boundary into a server
 * component — and its strings are sentence fragments for a progress line ("wird geprüft"), where a
 * badge needs a standalone noun ("Wird geprüft"). Two presentations of one enum, not two copies of
 * one string.
 */

import type { BatchAuditJobSummary, Proposal } from "@/lib/dashboard/types"

/** The colour a status badge carries, expressed as a `Badge` variant plus an optional override. */
export type StatusPresentation = {
  label: string
  variant: "default" | "secondary" | "destructive" | "outline"
  /**
   * Extra classes, for the two states the design system has no token for.
   *
   * The palette is monochrome apart from `destructive`, so "done and fine" and "still running" are
   * literal colours — each with a `dark:` variant, because the app is theme-aware and an emerald
   * that only works on white reads as a different status at night. Taken from
   * `lib/padnext/format.ts`, so the green and amber on this screen are the green and amber a reader
   * has already learned on the audit screens.
   */
  className?: string
}

const RUNNING = "bg-amber-500/10 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300"
const DONE = "bg-emerald-500/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300"

/**
 * Exhaustive over the contract's closed union, so a fifth proposal status fails this build rather
 * than rendering `EXPORTED` at a physician.
 *
 * `DRAFT` is `outline` and not a colour on purpose. It is the state that means *nobody has taken
 * responsibility for this yet*, and a draft dressed in green or amber invites a reader to treat it
 * as a verdict. Freigegeben is the only proposal state this screen paints green, because it is the
 * only one a human has signed.
 */
export const PROPOSAL_STATUS: Record<Proposal["status"], StatusPresentation> = {
  DRAFT: { label: "Entwurf", variant: "outline" },
  APPROVED: { label: "Freigegeben", variant: "secondary", className: DONE },
  REJECTED: { label: "Abgelehnt", variant: "destructive" },
  EXPORTED: { label: "Exportiert", variant: "secondary" },
}

/**
 * Exhaustive over `BatchJobStatus`.
 *
 * `FAILED` is the one that has to be conspicuous: it means the run itself broke and there is no
 * roll-up, which includes a batch the engine's startup recovery closed after a restart. A reader
 * scanning this card for "did my upload finish" must not mistake it for `COMPLETED`.
 */
export const BATCH_STATUS: Record<BatchAuditJobSummary["status"], StatusPresentation> = {
  PENDING: { label: "In Warteschlange", variant: "outline" },
  PROCESSING: { label: "Wird geprüft", variant: "secondary", className: RUNNING },
  COMPLETED: { label: "Abgeschlossen", variant: "secondary", className: DONE },
  FAILED: { label: "Fehlgeschlagen", variant: "destructive" },
}

/**
 * A status the map knows, or the raw value in an outline badge.
 *
 * The maps above are exhaustive, so this fallback is unreachable through the type system and
 * reachable at runtime: the engine can be a newer build than the committed contract. Printing the
 * raw identifier is the right failure — it is ugly, it is obviously a gap, and it does not claim the
 * record is in a state it is not.
 */
export function statusPresentation<T extends string>(
  map: Record<T, StatusPresentation>,
  status: string,
): StatusPresentation {
  return map[status as T] ?? { label: status, variant: "outline" }
}

/**
 * `prop_ed6e3e687ce24f16` → `prop_ed6e3e68…`.
 *
 * Truncated for the row and never for anything else. The full id is the link's target and the row's
 * `title`, so a reader who needs the whole thing can still get at it — unlike a hash rendered
 * short with no way back to the original, which is what `CopyableHash` exists to avoid on the
 * screens where the value has to leave the browser.
 */
export function shortId(id: string, keep = 13): string {
  return id.length <= keep ? id : `${id.slice(0, keep)}…`
}

/** `"3"` → `"3 Dateien"`, and `"1"` → `"1 Datei"`. */
export function fileCount(count: number | null | undefined): string {
  const n = typeof count === "number" && Number.isFinite(count) ? count : 0
  return n === 1 ? "1 Datei" : `${n} Dateien`
}
