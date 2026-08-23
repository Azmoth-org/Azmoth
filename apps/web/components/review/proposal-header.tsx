import { DatabaseZapIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

import { CopyableHash } from "@/components/common/copyable-hash"
import { PROPOSAL_STATUS_LABEL, timestamp } from "@/lib/review/format"
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
 * Separate from `Field` because these four are the ones that leave the screen — into a ticket, a
 * dispute letter, or a `psql` query. `Field` is for values that are read, not taken.
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
 * Identity of the run. Every field here comes from the proposal itself, and together they are what
 * makes the result reproducible: same catalog, same rule tables, same logic programs, same solver —
 * same `receipt_hash`.
 */
export function ProposalHeader({ proposal }: { proposal: Proposal }) {
  const status = proposal.status ?? "DRAFT"
  // Read from the proposal, not from solver_result.audit_trail two levels down. The engine promotes
  // it because it qualifies the whole proposal; the audit trail keeps its own copy as the record.
  const solverStatus = proposal.solver_status
  const timedOut = proposal.solver_timed_out === true

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
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
        <CardDescription>
          {proposal.case_id ? (
            <>
              Fall-ID <span className="font-mono">{proposal.case_id}</span> ·{" "}
            </>
          ) : null}
          Erstellt {timestamp(proposal.created_at)}
          {proposal.approved_by ? (
            <>
              {" "}
              · Freigegeben von <strong>{proposal.approved_by}</strong>{" "}
              {timestamp(proposal.approved_at)}
            </>
          ) : null}
          {proposal.rejected_reason ? (
            <>
              {" "}
              · Ablehnungsgrund: <strong>{proposal.rejected_reason}</strong>
            </>
          ) : null}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
          <HashField label="Receipt-Hash (SHA-256)" value={proposal.receipt_hash} />
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
      </CardContent>
    </Card>
  )
}
