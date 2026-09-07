import { ChevronRightIcon } from "lucide-react"
import Link from "next/link"
import type * as React from "react"

import { Card } from "@workspace/ui/components/card"
import { cn } from "@workspace/ui/lib/utils"

/**
 * One figure, large, with the one line of context that makes it mean something.
 *
 * The dashboard had no figures. It opened with three cards of *rows* — the newest five drafts, the
 * newest five batches, the engine's version strings — every one of which has to be read to be
 * understood. Nothing on the screen answered "is anything waiting for me" without reading. This is
 * the row that does, and the whole design follows from that one job: a reader glances, and either
 * looks away or clicks.
 *
 * ## The number is the content; everything else is a label
 *
 * `text-display-xl` is DESIGN.md's 48px display tier, which is weight **300** and not bold. That is
 * deliberate and it is the brand's tell rather than an oversight: the display scale carries negative
 * tracking, and `@workspace/ui`'s own `.azm-display` note says that at weight 600 the tracking reads
 * as a rendering fault. A large light numeral is what financial software looks like; a large bold
 * one is what a marketing page looks like.
 *
 * 48px and not the 32px tier below it, which is what this started at. At 32px the figure and the
 * 14px label read as two lines of similar weight and the tile has to be *read* — which is the one
 * thing this row exists not to require. The scale has no step between them, so the choice was the
 * larger one; every count these tiles can hold is at most four digits, and four digits at 48px fit
 * the narrowest cell in the grid with room to spare.
 *
 * `azm-tnum` is not optional here. These four tiles sit in a grid and their digits have to line up
 * column-to-column — DESIGN.md calls tabular figures the one non-negotiable micro-detail, and a row
 * of proportional numerals is the fastest way to make a dashboard look assembled rather than
 * designed.
 *
 * ## The whole tile is a link, and it goes somewhere useful
 *
 * A tile that states a count a reader cannot then look at is a dead end — the same objection the two
 * activity cards answer with their header links. Each of these lands on the *filtered* list rather
 * than the list: "7 offene Prüfungen" goes to `/proposals?status=DRAFT`, which is the query the
 * number is the answer to. Both list pages keep their filters in the URL, so those links are exactly
 * the ones a reader could have built by hand (`lib/lists/params.ts`).
 *
 * An `<a>` wrapping the card rather than a click handler, for the reason `ActivityRow` gives at
 * length: middle-click, ctrl-click and "copy link address" are free, keyboard focus is free, and
 * nothing here has to become a client component to get them.
 *
 * ## Colour is never the only signal
 *
 * `tone` tints the icon chip and, for `critical` only, the numeral. The state is also *named* in the
 * caption underneath — "3 fehlgeschlagen", not a red number and nothing else — so a reader with a
 * colour-vision deficiency, a greyscale print and a screen reader all get the same answer. That is
 * the rule `lib/status.ts` sets for the badges, applied to the tiles.
 *
 * The palette is the same amber/emerald/sky/destructive as the status badges, and it is the same
 * literals rather than a shared constant on purpose: those are `bg`+`text` pairs sized for a badge,
 * and these are a chip and a numeral. Sharing the strings would mean sharing padding decisions too.
 */

/** What the figure means, in the four moods this application already paints. */
export type MetricTone = "neutral" | "positive" | "attention" | "critical"

const TONE: Record<MetricTone, { chip: string; value: string }> = {
  neutral: {
    chip: "bg-muted text-muted-foreground",
    value: "text-foreground",
  },
  positive: {
    chip: "bg-emerald-500/10 text-emerald-700",
    value: "text-foreground",
  },
  attention: {
    chip: "bg-amber-500/10 text-amber-700",
    value: "text-foreground",
  },
  critical: {
    chip: "bg-destructive/10 text-destructive",
    /*
     * Lightened in dark mode, the same move `lib/status.ts` makes for every one of its badge
     * palettes. `--destructive` is tuned against the light canvas; on the dark shell's navy it
     * lands near the 3:1 floor that a 48px numeral only just clears, and "only just" is not where
     * the one figure on this row that means *something broke* should sit.
     */
    value: "text-destructive",
  },
}

export function MetricCard({
  label,
  value,
  caption,
  href,
  icon: Icon,
  tone = "neutral",
}: {
  /** What is being counted, in the reader's words. Short enough not to wrap at the grid's narrowest. */
  label: string
  /**
   * The figure, already formatted — or `null` when the engine did not answer.
   *
   * `null` renders an em dash, and that distinction is the reason this is not a `number`. A tile that
   * printed `0` for a failed read would tell a reader that nothing is waiting on a screen whose
   * entire job is to say whether something is. An unknown count must look unknown.
   */
  value: number | null
  /** The one line under the figure: the breakdown, or what the figure is of. */
  caption: string
  /** The filtered list this number is the answer to. */
  href: string
  icon: React.ComponentType<{ className?: string }>
  tone?: MetricTone
}) {
  const unknown = value === null
  const palette = TONE[unknown ? "neutral" : tone]

  return (
    <Link
      href={href}
      className="group rounded-4xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none"
    >
      <Card
        size="sm"
        // The lift is two pixels and 150ms. Anything more on a tile this size reads as a toy;
        // `motion-reduce` drops the transform entirely, because a grid of four cards that all
        // move is exactly the pattern a vestibular disorder is triggered by.
        //
        // `gap-2` rather than the card's own `--card-spacing`: at 24px the label, the figure and
        // the caption read as three separate blocks that happen to share a border. They are one
        // statement — "offene Prüfungen: 7, warten auf ärztliche Freigabe" — and the figure only
        // dominates the tile if the two lines of type are close enough to it to be its caption
        // rather than its neighbours.
        className="h-full gap-2 transition-[box-shadow,transform] duration-150 ease-out group-hover:-translate-y-0.5 group-hover:shadow-lg motion-reduce:transform-none motion-reduce:transition-none"
      >
        <div className="flex items-start justify-between gap-3 px-(--card-spacing)">
          <span className="text-sm font-medium text-muted-foreground">
            {label}
          </span>
          <span
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-full",
              palette.chip
            )}
            aria-hidden
          >
            <Icon className="size-4" />
          </span>
        </div>

        <div className="px-(--card-spacing)">
          <p
            className={cn(
              "azm-tnum text-display-xl leading-none",
              palette.value
            )}
          >
            {/*
              An em dash, and the reason spelled out for a screen reader rather than left as a
              character it will read as "dash". A sighted reader gets the same sentence from the
              caption below, which says the count could not be loaded.
            */}
            {unknown ? <span aria-label="unbekannt">—</span> : value}
          </p>
          <p className="mt-2.5 flex items-start gap-1 text-xs text-muted-foreground">
            {/*
              `line-clamp-2`, not `truncate`. Four tiles across a 1440px window are about 290px
              wide, and a single-line caption clipped every German phrase this row has to say —
              "2 in der Warteschlange · 1 lä…" is not a shorter sentence, it is an unreadable one.
              Two lines fit every caption here; the clamp is the guard against a longer one
              somebody adds later, and the grid's `h-full` keeps a one-line tile the same height
              as a two-line one so the row's baselines still agree.
            */}
            <span className="line-clamp-2 min-w-0">{caption}</span>
            <ChevronRightIcon
              className="mt-0.5 size-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
              aria-hidden
            />
          </p>
        </div>
      </Card>
    </Link>
  )
}
