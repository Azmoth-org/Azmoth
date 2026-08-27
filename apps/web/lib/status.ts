/**
 * How this application paints a lifecycle status, in one place.
 *
 * Shared by the dashboard's activity cards and the two list pages, and that sharing is the point.
 * The same `APPROVED` proposal appears on three screens; if each one picked its own green, a reader
 * would be learning three colour languages for one fact. It is also why the maps are exhaustive over
 * the contract's closed unions rather than `Record<string, …>`: adding a fifth proposal status to the
 * engine fails this build instead of rendering `EXPORTED` at a physician in whatever the default is.
 *
 * Colour is never the only signal. Every badge carries a German label, so a reader with a
 * colour-vision deficiency, a greyscale print of a dispute letter and a screen reader all get the
 * same answer. The palettes are literal because the design system is monochrome apart from
 * `destructive`, and each carries an explicit `dark:` variant — the app is theme-aware and a green
 * that only works on white reads as a different status at night. They are the same amber, emerald and
 * sky the audit and rule screens already use (`lib/padnext/format.ts`, `lib/rules/format.ts`).
 */

import type { BatchAuditJobSummary, Proposal } from "@workspace/contracts"

export type StatusPresentation = {
  label: string
  variant: "default" | "secondary" | "destructive" | "outline"
  /** Extra classes, for the states the design system has no token for. */
  className?: string
}

const GRAY = "bg-muted text-muted-foreground"
const YELLOW =
  "bg-amber-500/10 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300"
const BLUE = "bg-sky-500/10 text-sky-700 dark:bg-sky-400/15 dark:text-sky-300"
const GREEN =
  "bg-emerald-500/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300"

/**
 * Grey, green, red, blue — and the greys and the reds are the load-bearing ones.
 *
 * `DRAFT` is grey and deliberately not a colour with a mood. It is the state that means *nobody has
 * taken responsibility for this yet*, and a draft dressed in green or amber invites a reader to treat
 * it as a verdict. `APPROVED` is the only proposal state painted green, because it is the only one a
 * named human has signed. `EXPORTED` is blue rather than a second green: it is terminal and it means
 * the record left the system, which is a different fact from "a physician accepted it".
 */
export const PROPOSAL_STATUS: Record<Proposal["status"], StatusPresentation> = {
  DRAFT: { label: "Entwurf", variant: "secondary", className: GRAY },
  APPROVED: { label: "Freigegeben", variant: "secondary", className: GREEN },
  REJECTED: { label: "Abgelehnt", variant: "destructive" },
  EXPORTED: { label: "Exportiert", variant: "secondary", className: BLUE },
}

/**
 * Yellow, blue, green, red.
 *
 * `FAILED` is the one that has to be conspicuous, and it carries more meaning than "an error
 * happened": it means the run itself broke and there is no roll-up, which includes every batch the
 * engine's startup recovery closed after a restart. A reader scanning this column for "did my upload
 * finish" must not be able to mistake it for `COMPLETED`.
 */
export const BATCH_STATUS: Record<
  BatchAuditJobSummary["status"],
  StatusPresentation
> = {
  PENDING: {
    label: "In Warteschlange",
    variant: "secondary",
    className: YELLOW,
  },
  PROCESSING: { label: "Wird geprüft", variant: "secondary", className: BLUE },
  COMPLETED: { label: "Abgeschlossen", variant: "secondary", className: GREEN },
  FAILED: { label: "Fehlgeschlagen", variant: "destructive" },
}

/**
 * A status the map knows, or the raw value in an outline badge.
 *
 * The maps are exhaustive, so this fallback is unreachable through the type system and reachable at
 * runtime: the engine can be a newer build than the committed contract. Printing the raw identifier
 * is the right failure — it is obviously a gap, and it does not claim the record is in a state it is
 * not. It is also why an unknown status degrades one badge rather than the whole screen.
 */
export function statusPresentation<T extends string>(
  map: Record<T, StatusPresentation>,
  status: string
): StatusPresentation {
  return map[status as T] ?? { label: status, variant: "outline" }
}
