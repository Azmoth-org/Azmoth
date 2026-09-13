/**
 * Which section of a long report is "active" for a sticky nav, given each section's vertical
 * offset and the current scroll position.
 *
 * Kept as a pure function, separate from the `IntersectionObserver`/`scroll` plumbing in
 * `ReportSectionNav`, so the one part of "which link lights up" that has actual logic in it can be
 * tested without a DOM, a browser, or a fake observer.
 */

export type SectionOffset = {
  id: string
  /** Distance from the top of the document to the section's heading, in document pixels. */
  top: number
}

/**
 * The last section (in document order) whose top has scrolled past `scrollY + threshold`.
 *
 * `threshold` is how far below the very top of the viewport a section must have scrolled before it
 * counts as "reached" — normally the sticky nav's own height plus a little headroom, so a heading
 * tucked directly under the nav still reads as active rather than as the section above it.
 *
 * Returns `null` only when no section has been reached yet (at the very top of the page) — the
 * caller is expected to keep whatever was active before rather than clear the highlight, since a
 * user is never looking at "no section".
 */
export function activeSectionId(
  offsets: readonly SectionOffset[],
  scrollY: number,
  threshold = 0
): string | null {
  let active: string | null = null
  for (const offset of offsets) {
    if (offset.top - threshold <= scrollY) {
      active = offset.id
    } else {
      break
    }
  }
  return active
}
