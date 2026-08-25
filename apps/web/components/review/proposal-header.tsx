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
import { PROPOSAL_STATUS_LABEL, eur, timestamp } from "@/lib/review/format"
import type { Proposal, ProposalStatus } from "@/lib/review/types"

const STATUS_VARIANT: Record<ProposalStatus, "default" | "secondary" | "destructive" | "outline"> = {
  DRAFT: "secondary",
  APPROVED: "default",
  REJECTED: "destructive",
  EXPORTED: "outline",
}

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
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd
        className={mono ? "truncate font-mono text-xs" : "truncate text-sm"}
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
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5">
        <CopyableHash value={value} length={length} label={label} />
      </dd>
    </div>
  )
}

/**
 * One figure, sized by how much it matters.
 *
 * `tone` is the only place colour carries meaning on this screen: green for what is being charged,
 * red for what a rule removed. Everything else is the neutral palette, so that when a colour does
 * appear a reader can trust it means something.
 */
function Stat({
  label,
  value,
  hint,
  tone = "neutral",
  icon: Icon,
  large = false,
}: {
  label: string
  value: string
  hint?: string
  tone?: "neutral" | "accepted" | "blocked"
  icon?: React.ComponentType<{ className?: string }>
  large?: boolean
}) {
  const valueColor =
    tone === "accepted"
      ? "text-emerald-700 dark:text-emerald-400"
      : tone === "blocked"
        ? "text-destructive"
        : "text-foreground"

  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground flex items-center gap-1.5 text-xs">
        {Icon ? <Icon className="size-3.5 shrink-0" /> : null}
        {label}
      </dt>
      <dd
        className={`${large ? "text-3xl" : "text-2xl"} mt-1 font-semibold tabular-nums ${valueColor}`}
      >
        {value}
      </dd>
      {hint ? <p className="text-muted-foreground mt-0.5 text-xs">{hint}</p> : null}
    </div>
  )
}

/**
 * Who this proposal is, what it comes to, and what produced it.
 *
 * Three layers, in the order a reviewer needs them.
 *
 * **The result.** The total is the largest thing on the screen because it is the number the reader
 * came for and the one they are signing under. It is `coding.total.amount_eur` printed verbatim —
 * the engine computes in `Decimal` and serialises to a string precisely so that no client can
 * re-round it. Nothing here adds or formats a figure; the position counts are `length`, not sums.
 *
 * **The record.** Fall-ID, Vorschlags-ID, receipt hash, timestamps. These are what a dispute is
 * conducted with, so the identifiers are copyable in full rather than readable off the screen.
 *
 * **The provenance.** Catalog, rule tables, logic programs, solver, policy — collapsed, because a
 * reader checking an amount does not need eight version strings in the way, and *present on paper*,
 * because a printed proposal without them would carry a receipt hash nothing could be checked
 * against. Together they are what makes the result reproducible: same versions, same `receipt_hash`.
 */
export function ProposalHeader({ proposal }: { proposal: Proposal }) {
  const status = proposal.status ?? "DRAFT"
  const coding = proposal.solver_result.coding
  const total = coding.total
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
        <CardTitle className="flex flex-wrap items-center gap-2">
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

      <CardContent className="space-y-6">
        <dl className="bg-muted/40 grid grid-cols-2 gap-4 rounded-3xl border p-4 sm:gap-6 sm:p-5 lg:grid-cols-4 print:rounded-lg">
          <div className="col-span-2 lg:col-span-1">
            <Stat
              label="Gesamtbetrag"
              value={eur(total?.amount_eur)}
              hint={
                total
                  ? `${total.punkte} Punkte · Punktwert ${total.punktwert_cent} ct`
                  : "Die Engine hat keine Summe ausgewiesen."
              }
              large
            />
          </div>
          <Stat
            label="Berechnet"
            value={String(acceptedCount)}
            hint={acceptedCount === 1 ? "Position" : "Positionen"}
            tone="accepted"
            icon={CheckCircle2Icon}
          />
          <Stat
            label="Gesperrt"
            value={String(blockedCount)}
            hint={blockedCount === 1 ? "Position" : "Positionen"}
            tone="blocked"
            icon={BanIcon}
          />
          <div className="min-w-0">
            <dt className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <CalendarClockIcon className="size-3.5 shrink-0" />
              Erstellt
            </dt>
            <dd className="mt-1 text-sm">{timestamp(proposal.created_at)}</dd>
          </div>
        </dl>

        {/*
          The Vorschlags-ID is not repeated here — it is the card's title, which is what it is: the
          name of the record. These two are the ones a reader still has to be able to take with them.
        */}
        <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
          <Field label="Fall-ID" value={proposal.case_id || "—"} mono />
          <HashField label="Receipt-Hash (SHA-256)" value={proposal.receipt_hash} length={32} />
        </dl>

        <Disclosure label="Technische Herkunft und Versionen">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
            <Field label="Katalogversion" value={proposal.catalog_version} mono />
            <Field label="Regelversion" value={proposal.rules_version} mono />
            <HashField label="Logic-Version" value={proposal.logic_version} length={12} />
            <Field label="Solver (Clingo)" value={proposal.solver_version} mono />
            <Field label="Regel-Engine (Soufflé)" value={proposal.rules_engine_version || "—"} mono />
            <Field label="Solver-Status" value={solverStatus || "—"} mono />
            <HashField label="Katalog-SHA-256" value={proposal.catalog_sha256} length={12} />
          </dl>
        </Disclosure>
      </CardContent>
    </Card>
  )
}
