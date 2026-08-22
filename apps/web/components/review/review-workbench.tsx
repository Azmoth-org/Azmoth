"use client"

import * as React from "react"

import { Badge } from "@workspace/ui/components/badge"
import { Card, CardContent } from "@workspace/ui/components/card"
import { Separator } from "@workspace/ui/components/separator"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@workspace/ui/components/tabs"

import { AcceptedPositionsTable } from "@/components/review/accepted-positions-table"
import { AuditTrailPanel } from "@/components/review/audit-trail-panel"
import { BlockedPositionsTable } from "@/components/review/blocked-positions-table"
import { CaseSelector } from "@/components/review/case-selector"
import {
  ApproveDialog,
  ExportButtonPlaceholder,
  RejectDialog,
} from "@/components/review/decision-dialogs"
import { ErrorPanel } from "@/components/review/error-panel"
import { MissingDocumentationPanel } from "@/components/review/missing-documentation-panel"
import { ProposalHeader } from "@/components/review/proposal-header"
import { RuleCoverageBanner } from "@/components/review/rule-coverage-banner"
import { WarningsPanel } from "@/components/review/warnings-panel"
import { SYNTHETIC_CASES, findSyntheticCase, type SyntheticCase } from "@/lib/fixtures"
import { approveProposal, rejectProposal, solveCase } from "@/lib/review/client"
import type { Proposal, ReviewError } from "@/lib/review/types"

type Pending = "idle" | "solving" | "approving" | "rejecting"

function TabLabel({ label, count }: { label: string; count: number }) {
  return (
    <span className="flex items-center gap-1.5">
      {label}
      {count > 0 ? (
        <Badge variant="secondary" className="tabular-nums">
          {count}
        </Badge>
      ) : null}
    </span>
  )
}

/**
 * The review screen's only stateful component.
 *
 * State is deliberately shallow: one proposal, one error, one pending flag. There is no client-side
 * cache and no optimistic update — a decision changes the engine's record, and the screen shows what
 * the engine returned rather than what it hoped would happen.
 */
export function ReviewWorkbench() {
  const [selected, setSelected] = React.useState<SyntheticCase>(SYNTHETIC_CASES[0])
  const [proposal, setProposal] = React.useState<Proposal | null>(null)
  const [error, setError] = React.useState<ReviewError | null>(null)
  const [pending, setPending] = React.useState<Pending>("idle")

  function selectCase(id: string) {
    const next = findSyntheticCase(id)
    if (!next) return
    setSelected(next)
    setProposal(null)
    setError(null)
  }

  async function run() {
    setPending("solving")
    setError(null)
    const result = await solveCase({
      extraction: selected.extraction,
      case_id: selected.id,
    })
    if (result.kind === "proposal") {
      setProposal(result.proposal)
    } else {
      setProposal(null)
      setError(result.error)
    }
    setPending("idle")
  }

  async function approve(approvedBy: string, note: string) {
    if (!proposal) return
    setPending("approving")
    const result = await approveProposal(proposal.proposal_id, {
      approved_by: approvedBy,
      note,
    })
    if (result.kind === "proposal") {
      setProposal(result.proposal)
      setError(null)
    } else {
      setError(result.error)
    }
    setPending("idle")
  }

  async function reject(rejectedBy: string, reason: string) {
    if (!proposal) return
    setPending("rejecting")
    const result = await rejectProposal(proposal.proposal_id, {
      rejected_by: rejectedBy,
      reason,
    })
    if (result.kind === "proposal") {
      setProposal(result.proposal)
      setError(null)
    } else {
      setError(result.error)
    }
    setPending("idle")
  }

  const coding = proposal?.solver_result.coding
  const auditTrail = proposal?.solver_result.audit_trail
  const accepted = coding?.proposed_codes ?? []
  const blocked = coding?.blocked_codes ?? []
  const warnings = coding?.warnings ?? []
  // `Coding.missing_documentation` and `Proposal.missing_documentation` carry the same list; the
  // coding one is the invoice's own copy, so it is preferred and the proposal one is the fallback.
  const missing = coding?.missing_documentation ?? proposal?.missing_documentation ?? []
  const isDraft = (proposal?.status ?? "DRAFT") === "DRAFT"

  return (
    <div className="space-y-6">
      <CaseSelector
        selected={selected}
        onSelect={selectCase}
        onRun={run}
        pending={pending === "solving"}
      />

      {error ? <ErrorPanel error={error} /> : null}

      {proposal && coding && auditTrail ? (
        <>
          <ProposalHeader proposal={proposal} />
          <RuleCoverageBanner proposal={proposal} />

          <Card>
            <CardContent className="flex flex-wrap items-center gap-3">
              <ApproveDialog
                disabled={!isDraft || pending !== "idle"}
                pending={pending === "approving"}
                onApprove={approve}
              />
              <RejectDialog
                disabled={!isDraft || pending !== "idle"}
                pending={pending === "rejecting"}
                onReject={reject}
              />
              <Separator orientation="vertical" className="h-6" />
              <ExportButtonPlaceholder />
              {!isDraft ? (
                <p className="text-muted-foreground text-sm">
                  Dieser Vorschlag ist bereits entschieden. Ein erneuter Statuswechsel wird von der
                  Engine mit HTTP 409 abgelehnt.
                </p>
              ) : null}
            </CardContent>
          </Card>

          <Tabs defaultValue="accepted">
            <TabsList>
              <TabsTrigger value="accepted">
                <TabLabel label="Berechnet" count={accepted.length} />
              </TabsTrigger>
              <TabsTrigger value="blocked">
                <TabLabel label="Gesperrt" count={blocked.length} />
              </TabsTrigger>
              <TabsTrigger value="documentation">
                <TabLabel label="Dokumentationslücken" count={missing.length} />
              </TabsTrigger>
              <TabsTrigger value="warnings">
                <TabLabel label="Hinweise" count={warnings.length} />
              </TabsTrigger>
              <TabsTrigger value="audit">
                <TabLabel label="Beweis / Audit-Trail" count={0} />
              </TabsTrigger>
            </TabsList>

            <TabsContent value="accepted" className="pt-4">
              <AcceptedPositionsTable coding={coding} />
            </TabsContent>
            <TabsContent value="blocked" className="pt-4">
              <BlockedPositionsTable coding={coding} />
            </TabsContent>
            <TabsContent value="documentation" className="pt-4">
              <MissingDocumentationPanel entries={missing} />
            </TabsContent>
            <TabsContent value="warnings" className="pt-4">
              <WarningsPanel warnings={warnings} />
            </TabsContent>
            <TabsContent value="audit" className="pt-4">
              <AuditTrailPanel auditTrail={auditTrail} />
            </TabsContent>
          </Tabs>
        </>
      ) : null}

      {!proposal && !error ? (
        <Card>
          <CardContent className="text-muted-foreground text-sm">
            Noch kein Vorschlag. Fall auswählen und <strong>Engine ausführen</strong> — die Engine muss
            dafür unter <span className="font-mono text-xs">ENGINE_BASE_URL</span> erreichbar sein
            (Standard <span className="font-mono text-xs">http://localhost:8000</span>).
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
