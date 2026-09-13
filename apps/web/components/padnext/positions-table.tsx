"use client"

import {
  ChevronDownIcon,
  ChevronUpIcon,
  CircleAlertIcon,
  CircleCheckIcon,
  CircleHelpIcon,
  FlagIcon,
} from "lucide-react"
import { Fragment, useEffect, useRef, useState } from "react"

import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import {
  BUCKET,
  BUCKET_ORDER,
  BUCKET_TONE_CLASS,
  VERDICT_LABEL,
  eur,
  primaryBewertungText,
  verifiedDefectCodes,
} from "@/lib/padnext/format"
import type {
  PadnextAuditReport,
  PadnextAuditedPosition,
} from "@/lib/padnext/types"

const BUCKET_ICON = {
  confirmed_wrong: CircleAlertIcon,
  confirmed_fine: CircleCheckIcon,
  unconfirmed: CircleHelpIcon,
} as const

/**
 * Columns that only fit beside Regelurteil and Regeln on a wide screen. Below it the two live in
 * the expansion instead — see `RowDetails`. One constant rather than two independent Tailwind
 * arbitrary breakpoints, so the inline columns and the expansion's own visibility can never drift
 * to different widths.
 */
const WIDE_ONLY = "hidden min-[1680px]:table-cell"
const NARROW_ONLY = "min-[1680px]:hidden"

/** How many `<td>`s a detail row must span — every column, including the toggle. */
const COLUMN_COUNT = 10

function BucketBadge({ bucket }: { bucket: PadnextAuditedPosition["bucket"] }) {
  const presentation = BUCKET[bucket]
  const Icon = BUCKET_ICON[bucket]
  return (
    <Badge className={BUCKET_TONE_CLASS[presentation.tone].badge}>
      <Icon aria-hidden />
      {presentation.label}
    </Badge>
  )
}

/** The rules that bore on a position, with their verification status made explicit. */
function RuleIds({ position }: { position: PadnextAuditedPosition }) {
  const verified = position.verified_rule_ids ?? []
  const advisory = position.advisory_rule_ids ?? []

  if (verified.length === 0 && advisory.length === 0) {
    return (
      <span className="text-xs text-muted-foreground">
        keine Regel anwendbar
      </span>
    )
  }

  return (
    <div className="flex flex-wrap gap-1">
      {verified.map((id) => (
        <Badge
          key={id}
          variant="outline"
          className="font-mono text-[0.7rem]"
          title="verifizierte Regel"
        >
          ✓ {id}
        </Badge>
      ))}
      {advisory.map((id) => (
        <Badge
          key={id}
          variant="outline"
          className="font-mono text-[0.7rem] text-muted-foreground"
          title="nicht verifiziert — blockiert unter der aktuellen Policy nicht"
        >
          ? {id}
        </Badge>
      ))}
    </div>
  )
}

/** "Regelurteil": the engine's rule-level verdict, plus which Ziffer it lost to, if any. */
function Regelurteil({ position }: { position: PadnextAuditedPosition }) {
  return (
    <>
      {VERDICT_LABEL[position.verdict]}
      {position.blocked_by ? (
        <div className="font-mono text-[0.7rem] text-muted-foreground">
          neben {position.blocked_by}
        </div>
      ) : null}
    </>
  )
}

/**
 * Everything that does not fit beside the primary row: the full Bewertung explanation, the
 * Regelurteil and Regel chips at narrower widths, the legal basis, and the raw finding code —
 * present only when `verifiedDefectCodes` could actually pull one out of `bucket_reason`.
 *
 * Regelurteil and Regeln are duplicated between here and the inline columns rather than moved
 * conditionally, so the two never fall out of sync: `WIDE_ONLY`/`NARROW_ONLY` decide which copy
 * paints, in pure CSS, at exactly the breakpoint the brief specifies (1680px).
 */
function RowDetails({ position }: { position: PadnextAuditedPosition }) {
  const rawCodes = verifiedDefectCodes(position.bucket_reason)

  return (
    <TableRow className="bg-muted/20 hover:bg-muted/20">
      <TableCell colSpan={COLUMN_COUNT} className="whitespace-normal">
        <div className="grid gap-3 py-1 text-xs sm:grid-cols-2 lg:grid-cols-3">
          <div className="min-w-0 sm:col-span-2 lg:col-span-1">
            <div className="font-medium text-foreground">Bewertung</div>
            <p className="text-muted-foreground">
              {position.bucket_reason || "—"}
            </p>
          </div>
          <div className={`min-w-0 ${NARROW_ONLY}`}>
            <div className="font-medium text-foreground">Regelurteil</div>
            {/* `div`, not `p`: `Regelurteil` renders its own `div` for "neben X" when
                `blocked_by` is set, and a `div` inside a `p` is invalid HTML. */}
            <div className="text-muted-foreground">
              <Regelurteil position={position} />
            </div>
          </div>
          <div className={`min-w-0 ${NARROW_ONLY}`}>
            <div className="mb-1 font-medium text-foreground">Regeln</div>
            <RuleIds position={position} />
          </div>
          {position.legal_basis ? (
            <div className="min-w-0">
              <div className="font-medium text-foreground">
                Rechtsgrundlage
              </div>
              <p className="text-muted-foreground">{position.legal_basis}</p>
            </div>
          ) : null}
          {rawCodes ? (
            <div className="min-w-0">
              <div className="font-medium text-foreground">
                Rohcode (Engine)
              </div>
              <p
                data-testid="raw-reason-code"
                className="font-mono text-muted-foreground break-all"
              >
                {rawCodes.join(", ")}
              </p>
            </div>
          ) : null}
        </div>
      </TableCell>
    </TableRow>
  )
}

function PositionRow({
  position,
  expanded,
  onToggle,
  onReportZiffer,
}: {
  position: PadnextAuditedPosition
  expanded: boolean
  onToggle: () => void
  onReportZiffer?: (ziffer: string) => void
}) {
  const primaryText = primaryBewertungText(position.bucket_reason)

  return (
    <Fragment>
      <TableRow>
        <TableCell
          data-testid="pos-cell"
          className="sticky left-0 z-10 w-12 bg-background font-mono text-xs"
        >
          {position.positionsnr}
        </TableCell>
        <TableCell
          data-testid="ziffer-cell"
          className="sticky left-12 z-10 min-w-28 bg-background"
        >
          <div className="flex items-center gap-1">
            <span className="font-mono text-sm whitespace-nowrap">
              {position.go} {position.ziffer}
            </span>
            {onReportZiffer ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                className="text-muted-foreground hover:text-foreground"
                title="Regel fehlt? Ziffer melden"
                onClick={() => onReportZiffer(position.ziffer)}
              >
                <FlagIcon aria-hidden />
                <span className="sr-only">
                  Regel für Ziffer {position.ziffer} melden
                </span>
              </Button>
            ) : null}
          </div>
        </TableCell>
        <TableCell
          data-testid="leistung-cell"
          className="max-w-56 min-w-40 align-top whitespace-normal"
        >
          <p
            data-testid="leistung-text"
            className="line-clamp-2 break-words"
            title={position.official_text || undefined}
          >
            {position.official_text || "—"}
          </p>
        </TableCell>
        <TableCell className="text-right font-mono text-xs tabular-nums">
          {position.claimed_faktor ?? "—"}
        </TableCell>
        <TableCell className="text-right font-mono text-xs tabular-nums">
          {eur(position.claimed_amount_eur)}
        </TableCell>
        <TableCell className="text-right font-mono text-xs tabular-nums">
          {eur(position.recomputed_amount_eur)}
        </TableCell>
        <TableCell
          data-testid="bewertung-cell"
          className="max-w-56 min-w-36 align-top whitespace-normal"
        >
          <div className="space-y-1">
            <BucketBadge bucket={position.bucket} />
            <p
              data-testid="bewertung-text"
              className="line-clamp-2 break-words text-xs text-muted-foreground"
              title={position.bucket_reason || undefined}
            >
              {primaryText}
            </p>
          </div>
        </TableCell>
        <TableCell className={`${WIDE_ONLY} align-top text-xs`}>
          <Regelurteil position={position} />
        </TableCell>
        <TableCell className={`${WIDE_ONLY} align-top`}>
          <RuleIds position={position} />
        </TableCell>
        <TableCell className="text-right">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="whitespace-nowrap text-xs"
            aria-expanded={expanded}
            onClick={onToggle}
          >
            {expanded ? (
              <ChevronUpIcon aria-hidden />
            ) : (
              <ChevronDownIcon aria-hidden />
            )}
            {expanded ? "Details ausblenden" : "Details anzeigen"}
          </Button>
        </TableCell>
      </TableRow>
      {expanded ? <RowDetails position={position} /> : null}
    </Fragment>
  )
}

/**
 * Every claimed position, grouped by bucket.
 *
 * Grouped rather than sorted, and in `BUCKET_ORDER`, so the reader's first screen is what needs
 * action. The engine's `verdict` is shown next to the bucket rather than instead of it: they answer
 * different questions, and a position that reads `unbestätigt` / `durch Regel entfernt` is exactly
 * the case this refactor exists to make legible — a rule removed it, but no verified rule did.
 *
 * ## The layout
 *
 * Seven data columns in the primary row — Pos, Ziffer, Leistung, Faktor, berechnet, nachgerechnet,
 * Bewertung — plus Regelurteil and Regeln, which only join them at ≥1680px (`WIDE_ONLY`); below
 * that they move into a per-position expansion (`RowDetails`) along with the full Bewertung text,
 * the legal basis and the raw finding code. Pos and Ziffer are `sticky` so they stay in view while
 * the row scrolls horizontally; every other cell wraps inside its own `max-w-*` rather than
 * spilling into its neighbour — `TableCell` sets `whitespace-nowrap` by default, which is inherited
 * by any child that does not explicitly turn wrapping back on, so any cell holding prose overrides
 * it with `whitespace-normal`.
 */
export function PositionsTable({
  report,
  onReportZiffer,
}: {
  report: PadnextAuditReport
  /** Opens the "Regel fehlt? Ziffer melden" dialog, prefilled with one position's Ziffer. */
  onReportZiffer?: (ziffer: string) => void
}) {
  const positions = report.positions ?? []
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const scrollRef = useRef<HTMLDivElement>(null)
  const [canScrollRight, setCanScrollRight] = useState(false)

  function toggle(key: string) {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  // A wide report can arrive already scrolled — some browsers restore a mid-scroll position on
  // navigation, and a table that opens mid-word on "Ziffer" is the exact defect this component
  // exists to fix. Reasserted on every render of a new report rather than only on mount, since a
  // second upload replaces the positions without unmounting this component.
  useEffect(() => {
    const node = scrollRef.current
    if (node) node.scrollLeft = 0
  }, [report])

  useEffect(() => {
    const node = scrollRef.current
    if (!node) return
    function update() {
      if (!node) return
      setCanScrollRight(node.scrollWidth - node.clientWidth - node.scrollLeft > 1)
    }
    update()
    node.addEventListener("scroll", update)
    window.addEventListener("resize", update)
    return () => {
      node.removeEventListener("scroll", update)
      window.removeEventListener("resize", update)
    }
  }, [report])

  return (
    <section className="space-y-4" aria-labelledby="padnext-positions-heading">
      <h2
        id="padnext-positions-heading"
        className="text-lg font-semibold tracking-tight"
      >
        Positionen ({positions.length})
      </h2>

      <div className="relative">
        <div
          ref={scrollRef}
          data-testid="positions-scroll"
          className="overflow-x-auto rounded-md border border-border [&::-webkit-scrollbar]:h-2.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-track]:bg-transparent"
          style={{ scrollbarColor: "var(--border) transparent", scrollbarWidth: "auto" }}
        >
          <table className="w-full caption-bottom text-sm">
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 z-20 w-12 bg-background">
                  Pos
                </TableHead>
                <TableHead className="sticky left-12 z-20 min-w-28 bg-background">
                  Ziffer
                </TableHead>
                <TableHead className="max-w-56 min-w-40">Leistung</TableHead>
                <TableHead className="text-right">Faktor</TableHead>
                <TableHead className="text-right">berechnet</TableHead>
                <TableHead className="text-right">nachgerechnet</TableHead>
                <TableHead className="max-w-56 min-w-36">Bewertung</TableHead>
                <TableHead className={WIDE_ONLY}>Regelurteil</TableHead>
                <TableHead className={WIDE_ONLY}>Regeln</TableHead>
                <TableHead className="w-0">
                  <span className="sr-only">Details</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {BUCKET_ORDER.flatMap((bucket) =>
                positions
                  .filter((position) => position.bucket === bucket)
                  .map((position) => {
                    const key = `${position.positionsnr}-${position.ziffer}`
                    return (
                      <PositionRow
                        key={key}
                        position={position}
                        expanded={expanded.has(key)}
                        onToggle={() => toggle(key)}
                        onReportZiffer={onReportZiffer}
                      />
                    )
                  })
              )}
            </TableBody>
          </table>
        </div>
        {canScrollRight ? (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-background to-transparent"
          />
        ) : null}
      </div>

      <p className="text-xs text-muted-foreground">
        <span className="font-mono">✓</span> verifizierte Regel ·{" "}
        <span className="font-mono">?</span> nicht verifiziert, blockiert unter
        der aktuellen Policy nicht. Eine Position ohne verifizierte Regel kann
        nicht als bestätigt gelten, auch wenn an ihr nichts auffällig ist.
      </p>
    </section>
  )
}
