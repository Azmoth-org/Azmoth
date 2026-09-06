import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  LayersIcon,
  StethoscopeIcon,
} from "lucide-react"

import { METRIC_LABELS } from "@/components/dashboard/card-states"
import { MetricCard } from "@/components/dashboard/metric-card"
import {
  countBatches,
  countProposals,
  sumOrUnknown,
} from "@/lib/dashboard/counts"

/**
 * The four figures at the top of the dashboard: what is waiting, what is done, what is running,
 * what broke.
 *
 * **The screen had no numbers.** It opened with the engine's version strings and two lists of the
 * newest five records, and a reader who wanted to know whether anything needed them had to read
 * rows and then guess whether five was all of them. The list endpoints have carried a real `total`
 * since the pagination work; until now nothing asked for it except as "5 von 214" in a card
 * subtitle. This row is the reading of it.
 *
 * The four were chosen as the questions somebody actually opens this application to ask, in order:
 *
 * 1. **Is a draft waiting for me?** `DRAFT` is the review queue by definition — the state that
 *    means nobody has taken responsibility yet — and it is the only figure here that represents
 *    work owed by a *person* rather than by the machine.
 * 2. **What has been signed?** `APPROVED` is the one proposal state a named human put their name
 *    on, which is why it is the one painted green and why `EXPORTED` is not folded into it.
 * 3. **What is the engine chewing on?** `PENDING` + `PROCESSING`, because a reader waiting on an
 *    upload does not care which of the two it is in — both mean "not yet".
 * 4. **Did anything break?** `FAILED` batches, including every run the engine's startup recovery
 *    closed after a restart. This is the tile that has to be conspicuous, and it is the only one
 *    whose tone depends on its value: red at one or more, grey at zero. A permanently red zero is
 *    an alarm a reader learns to stop seeing.
 *
 * ## Five requests, in parallel, inside one Suspense boundary
 *
 * Each is `limit=1` and read only for its `total` — see `lib/dashboard/counts.ts` for why that is
 * the cheap shape and why the proposals ones would be expensive at any other limit. `Promise.all`
 * because they are independent and the row cannot render until the slowest has answered anyway; the
 * page's own `Suspense` boundary is what keeps that slowest call from delaying the header, the
 * banner or the three cards below.
 *
 * A failed read degrades to one em dash rather than to an error state. That is the difference
 * between this row and the cards under it: a card that cannot load has a whole card to explain
 * itself in, and a tile has one number — so the tile says "unknown" and the card below it, reading
 * the same dead engine, says why.
 */
/*
 * The tile names, from the same constant the loading skeleton renders, so the four labels a reader
 * sees while the counts are in flight are the four they see when the counts land. A skeleton that
 * says "Offene Prüfungen" and resolves to a tile called something else is a layout that appears to
 * reshuffle itself.
 */
const [DRAFTS, APPROVED, IN_FLIGHT, FAILED] = METRIC_LABELS

export async function MetricsRow() {
  const [drafts, approved, queued, running, failed] = await Promise.all([
    countProposals("DRAFT"),
    countProposals("APPROVED"),
    countBatches("PENDING"),
    countBatches("PROCESSING"),
    countBatches("FAILED"),
  ])

  const inFlight = sumOrUnknown(queued, running)

  return (
    <section
      aria-label="Kennzahlen"
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
    >
      <MetricCard
        label={DRAFTS}
        value={drafts}
        // "warten auf ärztliche Freigabe" and not "Entwürfe": the tile is read by the person the
        // wait is on, and the caption should say what is owed rather than restate the status name
        // the badge already carries three cards further down.
        caption={caption(drafts, "warten auf ärztliche Freigabe")}
        href="/proposals?status=DRAFT"
        icon={StethoscopeIcon}
        // Amber at any value above zero, because an unreviewed draft is not a neutral fact — it is
        // the queue this application exists to shorten. Grey at zero: an empty queue is not amber.
        tone={drafts !== null && drafts > 0 ? "attention" : "neutral"}
      />

      <MetricCard
        label={APPROVED}
        value={approved}
        caption={caption(approved, "ärztlich freigegeben")}
        href="/proposals?status=APPROVED"
        icon={CheckCircle2Icon}
        tone="positive"
      />

      <MetricCard
        label={IN_FLIGHT}
        value={inFlight}
        // The split, because "4 in Arbeit" and "4 in der Warteschlange, keiner läuft" are different
        // situations and the second one is a stuck worker. It is the one caption here that carries a
        // breakdown rather than a restatement, and it is the reason both counts are fetched.
        caption={batchCaption(queued, running)}
        href="/padnext/batch/history?status=PROCESSING"
        icon={LayersIcon}
        tone={inFlight !== null && inFlight > 0 ? "attention" : "neutral"}
      />

      <MetricCard
        label={FAILED}
        value={failed}
        caption={caption(failed, "abgebrochene Stapelprüfungen")}
        href="/padnext/batch/history?status=FAILED"
        icon={AlertTriangleIcon}
        tone={failed !== null && failed > 0 ? "critical" : "neutral"}
      />
    </section>
  )
}

/**
 * The line under a figure, including the one for a figure that is not there.
 *
 * A tile whose number failed to load must not keep a caption describing a count it does not have —
 * "— warten auf ärztliche Freigabe" reads as zero waiting, which is the exact misreading the `null`
 * was introduced to prevent. So the caption becomes the explanation instead.
 */
function caption(value: number | null, suffix: string): string {
  return value === null ? "Wert nicht abrufbar" : suffix
}

/** `2 wartend · 1 in Prüfung`, or the reason it is not known. */
function batchCaption(queued: number | null, running: number | null): string {
  if (queued === null || running === null) return "Wert nicht abrufbar"
  if (queued === 0 && running === 0) return "keine laufenden Stapelprüfungen"
  return `${queued} wartend · ${running} in Prüfung`
}
