import { DatabaseZapIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

import { PROPOSAL_STATUS_LABEL, shortHash, timestamp } from "@/lib/review/format"
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
          <span className="font-mono text-sm">{proposal.proposal_id}</span>
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
          <Field
            label="Receipt-Hash (SHA-256)"
            value={shortHash(proposal.receipt_hash, 24)}
            title={proposal.receipt_hash}
            mono
          />
          <Field label="Katalogversion" value={proposal.catalog_version} mono />
          <Field label="Regelversion" value={proposal.rules_version} mono />
          <Field
            label="Logic-Version"
            value={shortHash(proposal.logic_version, 12)}
            title={proposal.logic_version}
            mono
          />
          <Field label="Solver (Clingo)" value={proposal.solver_version} mono />
          <Field
            label="Regel-Engine (Soufflé)"
            value={proposal.rules_engine_version || "—"}
            mono
          />
          <Field label="Solver-Status" value={solverStatus || "—"} mono />
          <Field
            label="Katalog-SHA-256"
            value={shortHash(proposal.catalog_sha256, 12)}
            title={proposal.catalog_sha256}
            mono
          />
        </dl>
      </CardContent>
    </Card>
  )
}
