import { BanIcon, CalendarClockIcon, CheckCircle2Icon, DatabaseZapIcon } from "lucide-react"
import type * as React from "react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

import { CopyableHash } from "@/components/common/copyable-hash"
import { Disclosure } from "@/components/review/collapsible-section"
import { PROPOSAL_STATUS_LABEL, timestamp } from "@/lib/review/format"
import type { Proposal, ProposalStatus } from "@/lib/review/types"

const STATUS_VARIANT: Record<ProposalStatus, "default" | "secondary" | "destructive" | "outline"> = {
  DRAFT: "secondary",
  APPROVED: "default",
  REJECTED: "destructive",
  EXPORTED: "outline",
}

/** The one caption style every small label on this card uses: 12px, muted, one line. */
const LABEL = "text-muted-foreground text-xs font-medium"

function Field({
  label,
  value,
  mono = false,
  title,
}: {
  label: string
  value: string
  mono?: boolean
  title?: string
}) {
  return (
    <div className="min-w-0">
      <dt className={LABEL}>{label}</dt>
      <dd
        className={mono ? "mt-1 truncate font-mono text-xs" : "mt-1 truncate text-sm"}
        title={title ?? value}
      >
        {value}
      </dd>
    </div>
  )
}

/**
 * An identifier field. The value is truncated for display and copied in full.
 *
 * Separate from `Field` because these are the ones that leave the screen — into a ticket, a dispute
 * letter, or a `psql` query. `Field` is for values that are read, not taken.
 */
function HashField({
  label,
  value,
  length = 24,
}: {
  label: string
  value: string | null | undefined
  length?: number
}) {
  return (
    <div className="min-w-0">
      <dt className={LABEL}>{label}</dt>
      <dd className="mt-1">
        <CopyableHash value={value} length={length} label={label} />
      </dd>
    </div>
  )
}

/**
 * One counted line in the Positionen column.
 *
 * `tone` is the only place colour carries meaning on this card: green for what is being charged, red
 * for what a rule removed. Everything else is the neutral palette, so that when a colour does appear
 * a reader can trust it means something.
 */
function CountLine({
  label,
  count,
  tone,
  icon: Icon,
}: {
  label: string
  count: number
  tone: "accepted" | "blocked"
  icon: React.ComponentType<{ className?: string }>
}) {
  // Zero is not a finding. A green tick over "0 Positionen berechnet" and a red bar over "0
  // gesperrt" both claim a state that is not there; colour is reserved for a count that exists.
  const color =
    count === 0
      ? "text-muted-foreground"
      : tone === "accepted"
        ? "text-emerald-700 dark:text-emerald-400"
        : "text-destructive"

  return (
    <div className="flex items-baseline gap-2">
      <Icon className={`${color} size-4 shrink-0 translate-y-0.5`} />
      <span className="text-muted-foreground text-sm">{label}</span>
      <span className="text-foreground text-base font-semibold tabular-nums">{count}</span>
      <span className="text-muted-foreground text-sm">
        {count === 1 ? "Position" : "Positionen"}
      </span>
    </div>
  )
}

/**
 * Who this proposal is, what it comes to, and what produced it.
 *
 * Three layers, in the order a reviewer needs them.
 *
 * **Not the amount.** This card carried a tinted band whose largest element was the total, 100px
 * under a 48px copy of the same figure in the sticky bar. Two heroes is no hero — the reader had to
 * check that the two agreed, which is work the screen invented and then handed them. The amount is
 * now on the page exactly twice: in the bar, and in the table footer that adds up to it.
 *
 * **The record.** What is left is the only question this card is for: *which record is this?* The
 * position counts as sentences rather than as more large figures, the timestamp, the Fall-ID and the
 * receipt hash. Nothing here adds or formats a figure; the counts are `length`, not sums. The
 * identifiers are copyable in full rather than readable off the screen, because they leave for a
 * ticket, a dispute letter or a `psql` query.
 *
 * **The provenance.** Catalog, rule tables, logic programs, solver, policy — collapsed, because a
 * reader checking an amount does not need eight version strings in the way, and *present on paper*,
 * because a printed proposal without them would carry a receipt hash nothing could be checked
 * against. Together they are what makes the result reproducible: same versions, same `receipt_hash`.
 */
export function ProposalHeader({ proposal }: { proposal: Proposal }) {
  const status = proposal.status ?? "DRAFT"
  const coding = proposal.solver_result.coding
  const acceptedCount = (coding.proposed_codes ?? []).length
  const blockedCount = (coding.blocked_codes ?? []).length
  // Read from the proposal, not from solver_result.audit_trail two levels down. The engine promotes
  // it because it qualifies the whole proposal; the audit trail keeps its own copy as the record.
  const solverStatus = proposal.solver_status
  const timedOut = proposal.solver_timed_out === true
  const decided = Boolean(proposal.approved_by || proposal.rejected_reason)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-lg font-semibold">
          <span className="text-muted-foreground text-sm font-normal">Vorschlag</span>
          <CopyableHash
            value={proposal.proposal_id}
            length={32}
            label="Vorschlags-ID"
            className="text-sm"
          />
          <Badge variant={STATUS_VARIANT[status]}>{PROPOSAL_STATUS_LABEL[status]}</Badge>
          {proposal.cached ? (
            <Badge variant="outline" className="gap-1">
              <DatabaseZapIcon />
              aus Cache
            </Badge>
          ) : null}
          {timedOut ? (
            <Badge variant="destructive">Solver abgebrochen — Optimalität nicht bewiesen</Badge>
          ) : null}
        </CardTitle>
        {/*
          The decision, and only the decision. Fall-ID, creation time and status each have exactly
          one home below — a header that repeated all three read as three different facts at a
          glance and cost the reader a second look to find out they were not.
        */}
        {decided ? (
          <CardDescription>
            {proposal.approved_by ? (
              <>
                Freigegeben von <strong>{proposal.approved_by}</strong>{" "}
                {timestamp(proposal.approved_at)}
              </>
            ) : null}
            {proposal.approved_by && proposal.rejected_reason ? " · " : null}
            {proposal.rejected_reason ? (
              <>
                Ablehnungsgrund: <strong>{proposal.rejected_reason}</strong>
              </>
            ) : null}
          </CardDescription>
        ) : null}
      </CardHeader>

      <CardContent>
        {/*
          Four facts, one row, no repetition of the amount.
          
          This card used to open with a tinted band whose largest element was the total — 100px
          under a 48px copy of the same figure in the sticky bar. Two heroes is no hero: the reader
          had to check whether the two numbers agreed, which is work the screen created and then
          asked them to do. The amount now appears exactly twice on this page, in the bar and in the
          table footer that adds up to it, and this card answers the only question left: *which
          record is this?* Positionen, Datum, Fall-ID, Receipt-Hash — what a dispute is conducted
          with.
        */}
        <dl className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
          <div className="min-w-0">
            <dt className={LABEL}>Positionen</dt>
            <dd className="mt-2 space-y-1.5">
              <CountLine
                label="Berechnet"
                count={acceptedCount}
                tone="accepted"
                icon={CheckCircle2Icon}
              />
              <CountLine label="Gesperrt" count={blockedCount} tone="blocked" icon={BanIcon} />
            </dd>
          </div>

          <div className="min-w-0">
            <dt className={`${LABEL} flex items-center gap-1.5`}>
              <CalendarClockIcon className="size-3.5 shrink-0" />
              Erstellt
            </dt>
            <dd className="mt-2 text-sm">{timestamp(proposal.created_at)}</dd>
          </div>

          {/*
            The Vorschlags-ID is not here — it is the card's title, which is what it is: the name of
            the record. These two are the ones a reader still has to be able to take with them.
          */}
          <Field label="Fall-ID" value={proposal.case_id || "—"} mono />
          <HashField label="Receipt-Hash (SHA-256)" value={proposal.receipt_hash} length={24} />
        </dl>

        {/*
          Collapsed, and staying collapsed. Eight version strings are what makes the result
          reproducible — same versions, same `receipt_hash` — and they are consulted during a
          dispute, never while reading an amount. Present on paper regardless: a printed proposal
          carrying a receipt hash that nothing could be checked against would be worse than one
          carrying no hash at all.
        */}
        <div className="mt-8 border-t pt-6">
          <Disclosure label="Technische Herkunft und Versionen">
            <dl className="grid grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-3 lg:grid-cols-4">
              <Field label="Katalogversion" value={proposal.catalog_version} mono />
              <Field label="Regelversion" value={proposal.rules_version} mono />
              <HashField label="Logic-Version" value={proposal.logic_version} length={12} />
              <Field label="Solver (Clingo)" value={proposal.solver_version} mono />
              <Field
                label="Regel-Engine (Soufflé)"
                value={proposal.rules_engine_version || "—"}
                mono
              />
              <Field label="Solver-Status" value={solverStatus || "—"} mono />
              <HashField label="Katalog-SHA-256" value={proposal.catalog_sha256} length={12} />
            </dl>
          </Disclosure>
        </div>
      </CardContent>
    </Card>
  )
}
