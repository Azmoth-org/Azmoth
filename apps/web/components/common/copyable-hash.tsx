"use client"

import { CheckIcon, CopyIcon } from "lucide-react"
import * as React from "react"

import { cn } from "@workspace/ui/lib/utils"

/** How long the confirmation stays up. Long enough to read, short enough not to need dismissing. */
const CONFIRMATION_MS = 1_600

/**
 * An identifier a reviewer has to be able to take with them: shown truncated, copied in full.
 *
 * This exists because of what these strings are *for*. A `receipt_hash` is the evidence that a
 * proposal was produced by one exact engine state — the catalog, the rule tables, the logic
 * programs, the solver versions and the policy — and a `proposal_id` or `batch_id` is how a record
 * is found again. All three end up in a ticket, an email to a Rechnungsprüfer, or a `psql` query.
 * Rendering 64 characters that can only be read off the screen by hand made the audit trail
 * technically present and practically unusable.
 *
 * **The full value is what gets copied, never the truncation.** The visible text is display only;
 * `value` goes to the clipboard whole. A partially-copied hash proves nothing and would be worse
 * than no copy button, because it looks like it worked.
 *
 * The confirmation is inline rather than a toast, deliberately: it needs no provider, no portal and
 * no new dependency, and it appears at the thing that was copied instead of in a corner of a screen
 * that may be scrolled somewhere else entirely.
 */
export function CopyableHash({
  value,
  length = 16,
  label,
  className,
}: {
  /** The full identifier. This is what is copied, whatever is displayed. */
  value: string | null | undefined
  /** Characters to show before the ellipsis. The whole value is shown if it is shorter. */
  length?: number
  /** Accessible name, e.g. "Receipt-Hash". Falls back to a generic German label. */
  label?: string
  className?: string
}) {
  const [copied, setCopied] = React.useState(false)
  const [failed, setFailed] = React.useState(false)
  const timer = React.useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined
  )

  React.useEffect(() => () => clearTimeout(timer.current), [])

  // Nothing to copy, and nothing to pretend is copyable. An em dash reads as "not present", which
  // is what a missing hash means; a dead button next to it would read as broken.
  if (!value) {
    return (
      <span
        className={cn("font-mono text-xs text-muted-foreground", className)}
      >
        —
      </span>
    )
  }

  // Bound to a const before the closure below. A narrowed *parameter* does not stay narrowed inside
  // a function declared later, so `value` would be `string | null | undefined` again inside `copy`.
  const full: string = value
  const shown = full.length <= length ? full : `${full.slice(0, length)}…`
  const name = label ?? "Wert"

  async function copy() {
    clearTimeout(timer.current)
    try {
      // `navigator.clipboard` is unavailable on an insecure origin that is not localhost, and can be
      // denied by permission policy. Either way the click must not fail silently: the reader is told
      // to select the text by hand rather than left believing a copy happened.
      await navigator.clipboard.writeText(full)
      setCopied(true)
      setFailed(false)
    } catch {
      setCopied(false)
      setFailed(true)
    }
    timer.current = setTimeout(() => {
      setCopied(false)
      setFailed(false)
    }, CONFIRMATION_MS)
  }

  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5", className)}>
      <span className="truncate font-mono text-xs" title={full}>
        {shown}
      </span>
      <button
        type="button"
        onClick={() => void copy()}
        // The full value is in the accessible name because a screen-reader user cannot read the
        // truncation off the screen and then decide whether to copy it.
        aria-label={`${name} in die Zwischenablage kopieren: ${full}`}
        className="shrink-0 cursor-pointer rounded text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        {copied ? (
          <CheckIcon className="size-3.5" aria-hidden />
        ) : (
          <CopyIcon className="size-3.5" aria-hidden />
        )}
      </button>
      {/* Announced, not just shown: the icon swap alone is invisible to a screen reader. */}
      <span aria-live="polite" className="text-xs text-muted-foreground">
        {copied ? "Kopiert" : failed ? "Kopieren nicht möglich" : null}
      </span>
    </span>
  )
}
