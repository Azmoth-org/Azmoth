import {
  CircleAlertIcon,
  CircleCheckIcon,
  CircleHelpIcon,
  InfoIcon,
} from "lucide-react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

import {
  BUCKET,
  BUCKET_ORDER,
  BUCKET_TONE_CLASS,
  UNCONFIRMED_DISCLAIMER,
  eur,
  percent,
  segmentWidths,
  type BucketFigures,
} from "@/lib/padnext/format"
import type {
  PadnextAuditReport,
  PadnextPositionBucket,
} from "@/lib/padnext/types"

const BUCKET_ICON = {
  confirmed_wrong: CircleAlertIcon,
  confirmed_fine: CircleCheckIcon,
  unconfirmed: CircleHelpIcon,
} as const

export type BucketCounts = Record<PadnextPositionBucket, number>

export function countBuckets(report: PadnextAuditReport): BucketCounts {
  const counts: BucketCounts = {
    confirmed_wrong: 0,
    confirmed_fine: 0,
    unconfirmed: 0,
  }
  for (const position of report.positions ?? []) {
    counts[position.bucket] += 1
  }
  return counts
}

/**
 * The bucket's amount, by an explicit mapping rather than a computed key.
 *
 * It keeps the three field names visible to a reader and to `tsc`, so renaming one in the contract
 * breaks this build instead of quietly rendering an em dash where a five-figure sum belongs.
 *
 * Takes `BucketFigures` rather than a report so the batch dashboard can hand it the aggregate. The
 * two shapes carry the same four field names on purpose — that is what makes one set of cards able
 * to state a single invoice's position and a whole practice's without a second implementation that
 * could word the amber bucket differently.
 */
function amountFor(
  figures: BucketFigures,
  bucket: PadnextPositionBucket
): string {
  if (bucket === "confirmed_wrong") return figures.confirmed_wrong_eur
  if (bucket === "confirmed_fine") return figures.confirmed_fine_eur
  return figures.unconfirmed_eur
}

function BucketCard({
  figures,
  bucket,
  count,
  unit,
}: {
  figures: BucketFigures
  bucket: PadnextPositionBucket
  count: number
  unit: readonly [string, string]
}) {
  const presentation = BUCKET[bucket]
  const tone = BUCKET_TONE_CLASS[presentation.tone]
  const Icon = BUCKET_ICON[bucket]

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Icon className={`size-4 shrink-0 ${tone.text}`} aria-hidden />
          <span>{presentation.label}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className={`text-3xl font-semibold tabular-nums ${tone.text}`}>
          {eur(amountFor(figures, bucket))}
        </div>
        <div className="text-xs text-muted-foreground">
          {count} {count === 1 ? unit[0] : unit[1]} · {presentation.headline}
        </div>
        <p className="text-xs text-foreground/80">{presentation.action}</p>
      </CardContent>
    </Card>
  )
}

/**
 * How much of the claim the audit could actually reach a verdict on.
 *
 * Deliberately not a pie chart of the three buckets. A pie invites the reader to compare red
 * against green and draw a conclusion about the *invoice*. This bar puts the two verdicts next to
 * the gap and says something about the *audit* — which is the honest comparison, because the amber
 * segment is our missing rule coverage, not the practice's billing.
 */
export function CoverageBar({
  figures,
  totalLabel = "berechnet insgesamt",
}: {
  figures: BucketFigures
  totalLabel?: string
}) {
  const amounts = BUCKET_ORDER.map((bucket) => amountFor(figures, bucket))
  const widths = segmentWidths(amounts)

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-medium">
          Prüfabdeckung {percent(figures.coverage_ratio)}
        </span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {totalLabel} {eur(figures.claimed_total_eur)}
        </span>
      </div>

      <div
        className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={
          `Prüfabdeckung ${percent(figures.coverage_ratio)} der berechneten Summe. ` +
          BUCKET_ORDER.map(
            (bucket) =>
              `${BUCKET[bucket].label}: ${eur(amountFor(figures, bucket))}`
          ).join(". ")
        }
      >
        {BUCKET_ORDER.map((bucket, index) =>
          widths[index] === 0 ? null : (
            <div
              key={bucket}
              className={BUCKET_TONE_CLASS[BUCKET[bucket].tone].bar}
              style={{ width: `${widths[index]}%` }}
            />
          )
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        Der Anteil der berechneten Summe, zu dem diese Prüfung überhaupt eine
        Aussage treffen konnte. Er sagt <strong>nicht</strong>, wie viel davon
        falsch ist.
      </p>
    </div>
  )
}

/** The disclaimer that must accompany any presentation of the three buckets, single or aggregate. */
export function UnconfirmedNotice() {
  return (
    <Alert>
      <InfoIcon />
      <AlertTitle>Unbestätigt ist kein Befund</AlertTitle>
      <AlertDescription className="space-y-2">
        <p>{UNCONFIRMED_DISCLAIMER}</p>
        <p className="text-foreground/80">
          Nur <strong>nachweislich falsch</strong> beruht auf verifizierten
          Regeln, dem versionierten Katalog oder der Nachrechnung nach § 5 Abs.
          1 GOÄ und ist damit gegenüber einem Kostenträger belastbar.{" "}
          <strong>Unbestätigt</strong> bedeutet, dass für diese Ziffer keine von
          einem Menschen geprüfte Regel vorliegt — die Position ist damit weder
          bestätigt noch beanstandet.
        </p>
      </AlertDescription>
    </Alert>
  )
}

/**
 * The three cards, the coverage bar and the disclaimer — the whole financial statement.
 *
 * Shared by the single-file audit and the batch dashboard, and that sharing is a safeguard rather
 * than a convenience. This block is the reason the engine's schema changed, so it is worth stating
 * what it must never do: it must not add the three buckets back together into a single "at risk"
 * figure, and it must not colour `unconfirmed` as a defect. `unconfirmed` is the engine admitting
 * the limit of its own rule coverage — 837 of 869 exclusion rules are machine-extracted and
 * unenforced under the default policy — and presenting that as the practice's problem is the
 * overclaim the split exists to prevent. One implementation means that prohibition cannot be
 * honoured on one screen and quietly dropped on the other.
 */
export function BucketBoard({
  figures,
  counts,
  heading,
  headingId,
  unit = ["Position", "Positionen"],
  totalLabel,
}: {
  figures: BucketFigures
  counts: BucketCounts
  heading: string
  headingId: string
  /** Singular and plural of whatever the counts are counting — positions here, positions there. */
  unit?: readonly [string, string]
  totalLabel?: string
}) {
  return (
    <section className="space-y-4" aria-labelledby={headingId}>
      <h2 id={headingId} className="text-lg font-semibold tracking-tight">
        {heading}
      </h2>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {BUCKET_ORDER.map((bucket) => (
          <BucketCard
            key={bucket}
            figures={figures}
            bucket={bucket}
            count={counts[bucket]}
            unit={unit}
          />
        ))}
      </div>

      <Card>
        <CardContent className="pt-6">
          <CoverageBar figures={figures} totalLabel={totalLabel} />
        </CardContent>
      </Card>

      <UnconfirmedNotice />
    </section>
  )
}

/** The single-file audit's financial summary. Unchanged in what it renders. */
export function BucketSummary({ report }: { report: PadnextAuditReport }) {
  return (
    <BucketBoard
      figures={report}
      counts={countBuckets(report)}
      heading="Finanzielle Bewertung"
      headingId="padnext-buckets-heading"
    />
  )
}
