"use client"

import { useEffect, useRef, useState } from "react"
import type * as React from "react"

import { cn } from "@workspace/ui/lib/utils"

import { activeSectionId, type SectionOffset } from "@/lib/padnext/section-nav"

export type ReportSection = {
  id: string
  label: string
}

/**
 * Sticky in-page nav for a long audit report — Bewertung, Positionen, Befunde, Meta.
 *
 * The report is one scroll: five sections, the longest of which (Positionen, Befunde) can each run
 * to dozens of rows. Nothing on the page previously said which section a reader was inside once
 * they had scrolled past the first one, or offered a way back to an earlier one short of scrolling.
 *
 * The active link is computed from each heading's own document offset, not from a per-section
 * `IntersectionObserver` — a report section's height varies from three lines (an empty Meta card)
 * to several screens (a long Positionen table), so "is the heading visible" answers a different
 * question at the top of a short section than at the top of a long one. `activeSectionId` in
 * `lib/padnext/section-nav.ts` is the one part of this with actual logic, and is tested there
 * without a DOM.
 *
 * `sections` may omit a section that did not render — `FindingsPanel` renders nothing for a report
 * with no findings — so the nav never links to an anchor that is not on the page.
 */
export function ReportSectionNav({
  sections,
  trailing,
}: {
  sections: readonly ReportSection[]
  /** Rendered at the trailing edge of the bar — the Katalogstand chip, kept visible while scrolling. */
  trailing?: React.ReactNode
}) {
  const [active, setActive] = useState<string | null>(null)
  const frameRef = useRef<number | null>(null)
  // A ref rather than a `useEffect` dependency: `sections` is a fresh array literal every render
  // (built inline by the caller), and re-subscribing the scroll listener on every render to chase
  // an identity that never carries different ids would cost more than it fixes.
  const sectionsRef = useRef(sections)
  useEffect(() => {
    sectionsRef.current = sections
  })

  useEffect(() => {
    function measure() {
      const offsets: SectionOffset[] = []
      for (const section of sectionsRef.current) {
        const el = document.getElementById(section.id)
        if (!el) continue
        offsets.push({ id: section.id, top: el.getBoundingClientRect().top + window.scrollY })
      }
      offsets.sort((a, b) => a.top - b.top)
      // 112px: this nav's own height (56px) plus the app shell's sticky header (56px) above it, so
      // a heading tucked directly underneath still counts as reached.
      const next = activeSectionId(offsets, window.scrollY, 112)
      setActive((prev) => next ?? prev)
    }

    function onScroll() {
      if (frameRef.current !== null) return
      frameRef.current = requestAnimationFrame(() => {
        frameRef.current = null
        measure()
      })
    }

    measure()
    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("resize", onScroll)
    return () => {
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onScroll)
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    }
  }, [])

  if (sections.length === 0) return null

  return (
    <nav
      aria-label="Abschnitte dieser Prüfung"
      className="sticky top-14 z-10 -mx-4 flex items-center gap-1 overflow-x-auto border-b bg-background/95 px-4 py-2 backdrop-blur supports-[backdrop-filter]:bg-background/80 print:hidden sm:-mx-6 sm:px-6"
    >
      {sections.map((section) => (
        <a
          key={section.id}
          href={`#${section.id}`}
          aria-current={active === section.id ? "true" : undefined}
          className={cn(
            "shrink-0 rounded-full px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors",
            active === section.id
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          {section.label}
        </a>
      ))}
      {trailing ? <div className="ml-auto shrink-0 pl-2">{trailing}</div> : null}
    </nav>
  )
}
