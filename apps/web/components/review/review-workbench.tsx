"use client"

import { useRouter } from "next/navigation"
import * as React from "react"

import { Badge } from "@workspace/ui/components/badge"
import { Card, CardContent } from "@workspace/ui/components/card"
import { Separator } from "@workspace/ui/components/separator"
import { Skeleton } from "@workspace/ui/components/skeleton"
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
  ExportDialog,
  RejectDialog,
} from "@/components/review/decision-dialogs"
import { ErrorPanel } from "@/components/review/error-panel"
import { MissingDocumentationPanel } from "@/components/review/missing-documentation-panel"
import { ProposalHeader } from "@/components/review/proposal-header"
import { RuleCoverageBanner } from "@/components/review/rule-coverage-banner"
import { WarningsPanel } from "@/components/review/warnings-panel"
import { isRetryable, isWellFormedId, malformedIdError, toDeepLinkError } from "@/lib/deep-link"
import { downloadProposalExport } from "@/lib/download"
import { SYNTHETIC_CASES, findSyntheticCase, type SyntheticCase } from "@/lib/fixtures"
import { approveProposal, fetchProposal, rejectProposal, solveCase } from "@/lib/review/client"
import type { Proposal, ReviewError } from "@/lib/review/types"

type Pending = "idle" | "solving" | "approving" | "rejecting" | "exporting"

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
 * What a deep-linked proposal looks like while it is being fetched.
 *
 * Bars, never a number-shaped placeholder: this screen renders money and Steigerungsfaktoren, and a
 * grey rectangle where a figure belongs is the one placeholder a reader can mistake for a rendered
 * zero. Shaped like the header and the tab strip that are about to replace it, so the layout does
 * not jump when they arrive.
 */
function ProposalSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <span className="sr-only" role="status">
          Prüfung wird geladen …
        </span>
        <Skeleton className="h-5 w-64" />
        <Skeleton className="h-4 w-40" />
        <div className="flex gap-2 pt-2">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-32" />
        </div>
        <Skeleton className="h-32 w-full" />
      </CardContent>
    </Card>
  )
}

/**
 * The review screen's only stateful component.
 *
 * State is deliberately shallow: one proposal, one error, one pending flag. There is no client-side
 * cache and no optimistic update — a decision changes the engine's record, and the screen shows what
 * the engine returned rather than what it hoped would happen.
 *
 * ## `deepLinkId` — arriving from a link rather than from the case selector
 *
 * `/review?id=prop_…` is what the dashboard's "Letzte Prüfungen" card and every row of `/proposals`
 * link to. The page reads the parameter and hands the id down; this component fetches it through the
 * same proxy every other call here uses, so `ENGINE_BASE_URL` still never reaches the browser.
 *
 * **Fetched here rather than on the server** on purpose. The alternative — `callEngine` in the page
 * and an `initialProposal` prop — would give this component two sources for the same field, one of
 * which cannot be refreshed without a navigation, and "retry" would mean a full page reload. The
 * screen already owns a proposal that changes under it four other ways (solve, approve, reject,
 * re-read after export); a deep link is a fifth, not a different kind of thing.
 *
 * A failed deep link does **not** take the screen over. The case selector stays usable and the
 * normal empty state is still reachable, because a stale bookmark should not turn `/review` into a
 * dead end — the reader who followed it is usually one click from doing something useful instead.
 */
export function ReviewWorkbench({ deepLinkId = null }: { deepLinkId?: string | null }) {
  const [selected, setSelected] = React.useState<SyntheticCase>(SYNTHETIC_CASES[0])
  const [proposal, setProposal] = React.useState<Proposal | null>(null)
  const [error, setError] = React.useState<ReviewError | null>(null)
  const [pending, setPending] = React.useState<Pending>("idle")
  // The name of the last file saved, so the screen confirms the download happened. A browser
  // download is silent — without this a successful export is indistinguishable from a dead button.
  const [exported, setExported] = React.useState<string | null>(null)
  // Bumped by "Erneut versuchen". It is part of the request key below, which is what makes a retry
  // a genuinely new request rather than a state reset that happens to look like one.
  const [reloads, setReloads] = React.useState(0)
  // The deep-link request the screen has already answered, as `<id>#<attempt>`.
  //
  // Compared against the current one to *derive* "is a deep link still loading", rather than a
  // `loading` flag assigned at the top of the effect. The flag was the obvious first version and it
  // is a synchronous `setState` inside an effect body — a second render on every navigation, and
  // the thing `react-hooks/set-state-in-effect` exists to catch. Every write below happens in the
  // async continuation, after an `await`, which is the case the rule is fine with.
  const [resolvedRequest, setResolvedRequest] = React.useState<string | null>(null)

  const router = useRouter()

  /**
   * A link whose id cannot be one this engine issued, refused without a request.
   *
   * Derived rather than stored: it is a pure function of the URL, nothing but a navigation can
   * change it, and putting it in state would mean an effect to keep the two in step.
   */
  const malformedError = React.useMemo(
    () =>
      deepLinkId !== null && !isWellFormedId("proposal", deepLinkId)
        ? malformedIdError("proposal", deepLinkId)
        : null,
    [deepLinkId],
  )

  const request = deepLinkId !== null && malformedError === null ? `${deepLinkId}#${reloads}` : null
  const loadingDeepLink = request !== null && resolvedRequest !== request

  React.useEffect(() => {
    if (request === null || deepLinkId === null) return

    let cancelled = false
    void (async () => {
      const result = await fetchProposal(deepLinkId)
      // The id can change under an in-flight request — a reader clicking a second row on the
      // dashboard — and the loser must not paint over the winner.
      if (cancelled) return
      if (result.kind === "proposal") {
        setProposal(result.proposal)
        setError(null)
      } else {
        setProposal(null)
        setError(toDeepLinkError("proposal", result.error))
      }
      setResolvedRequest(request)
    })()

    return () => {
      cancelled = true
    }
  }, [request, deepLinkId])

  /**
   * Drop `?id=` once the screen stops showing what it points at.
   *
   * Without this, running a different case leaves the address bar claiming a proposal that is no
   * longer on screen — and a reload would silently swap the reader back to the old one. The URL is
   * the state of this screen or it is nothing; `replace` rather than `push` so the back button still
   * goes back to wherever the link was followed from, not to a stale copy of this page.
   */
  const clearDeepLink = React.useCallback(() => {
    if (deepLinkId !== null) router.replace("/review", { scroll: false })
  }, [deepLinkId, router])

  function selectCase(id: string) {
    const next = findSyntheticCase(id)
    if (!next) return
    setSelected(next)
    setProposal(null)
    setError(null)
    setExported(null)
    clearDeepLink()
  }

  async function run() {
    setPending("solving")
    setError(null)
    setExported(null)
    clearDeepLink()
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

  async function exportProposal(exportedBy: string, note: string) {
    if (!proposal) return
    setPending("exporting")
    const result = await downloadProposalExport(proposal.proposal_id, {
      exported_by: exportedBy,
      note,
    })

    if (result.kind === "error") {
      setError(result.error)
      setPending("idle")
      return
    }

    setError(null)
    setExported(result.filename)

    // The export moved the proposal to EXPORTED in the engine, and the download response is the
    // file rather than the proposal, so the screen has to read the record back. Re-fetching rather
    // than patching local state is the same rule the rest of this component follows: show what the
    // engine says, not what the click hoped for. It costs a `VIEWED` audit row, which is accurate
    // — the screen did read the proposal again.
    const refreshed = await fetchProposal(proposal.proposal_id)
    if (refreshed.kind === "proposal") setProposal(refreshed.proposal)
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
  // A malformed link outranks whatever the last engine call said, because it is the reason nothing
  // was asked of the engine in the first place.
  const shownError = malformedError ?? error

  return (
    <div className="space-y-6">
      <CaseSelector
        selected={selected}
        onSelect={selectCase}
        onRun={run}
        pending={pending === "solving"}
      />

      {shownError ? (
        <ErrorPanel
          error={shownError}
          // Offered only for a deep link, and only when a second attempt could answer differently.
          // A retry on the solve path already has a button — "Engine ausführen" — and a second one
          // saying the same thing in a red box is noise.
          onRetry={
            deepLinkId !== null && isRetryable(shownError)
              ? () => setReloads((n) => n + 1)
              : undefined
          }
          pending={loadingDeepLink}
        />
      ) : null}

      {loadingDeepLink ? <ProposalSkeleton /> : null}

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
              <ExportDialog
                status={proposal.status}
                pending={pending === "exporting"}
                onExport={exportProposal}
              />
              {exported ? (
                <p className="text-muted-foreground text-sm">
                  Heruntergeladen: <span className="font-mono text-xs">{exported}</span>
                </p>
              ) : !isDraft ? (
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

      {/*
        Unchanged for a plain visit to /review — the same card, the same words. The only addition is
        that it stays out of the way while a deep link is in flight, so a reader who clicked a row
        is never told there is nothing here before the fetch has answered.
      */}
      {!proposal && !shownError && !loadingDeepLink ? (
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
