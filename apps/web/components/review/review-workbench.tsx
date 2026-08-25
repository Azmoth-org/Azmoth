"use client"

import { useRouter } from "next/navigation"
import {
  BanIcon,
  CheckCircle2Icon,
  DownloadIcon,
  FileTextIcon,
  InfoIcon,
  LockIcon,
  PlayIcon,
  ScrollTextIcon,
} from "lucide-react"
import * as React from "react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Badge } from "@workspace/ui/components/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from "@workspace/ui/components/empty"
import { Skeleton } from "@workspace/ui/components/skeleton"

import { AcceptedPositionsTable } from "@/components/review/accepted-positions-table"
import { AuditTrailPanel } from "@/components/review/audit-trail-panel"
import { BlockedPositionsTable } from "@/components/review/blocked-positions-table"
import { CaseSelector } from "@/components/review/case-selector"
import { CollapsibleSection, Disclosure } from "@/components/review/collapsible-section"
import { DecisionBar } from "@/components/review/decision-bar"
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

/**
 * One titled region of the proposal.
 *
 * `flush` drops the horizontal padding so a table can run to the card's edge — the zebra stripes and
 * the header rule read as the table's own structure that way, instead of as a box floating inside a
 * box. Prose sections keep their padding.
 */
function Section({
  title,
  description,
  count,
  icon: Icon,
  tone = "neutral",
  flush = false,
  className,
  children,
}: {
  title: string
  description?: string
  count?: number
  icon?: React.ComponentType<{ className?: string }>
  tone?: "neutral" | "accepted" | "blocked"
  flush?: boolean
  className?: string
  children: React.ReactNode
}) {
  const iconColor =
    tone === "accepted"
      ? "text-emerald-700 dark:text-emerald-400"
      : tone === "blocked"
        ? "text-destructive"
        : "text-muted-foreground"

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg font-semibold">
          {Icon ? <Icon className={`size-4 shrink-0 ${iconColor}`} /> : null}
          <span className="min-w-0 flex-1">{title}</span>
          {count !== undefined ? (
            <Badge variant="secondary" className="tabular-nums">
              {count}
            </Badge>
          ) : null}
        </CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className={flush ? "px-0" : undefined}>{children}</CardContent>
    </Card>
  )
}

/**
 * What a deep-linked proposal looks like while it is being fetched.
 *
 * Bars, never a number-shaped placeholder: this screen renders money and Steigerungsfaktoren, and a
 * grey rectangle where a figure belongs is the one placeholder a reader can mistake for a rendered
 * zero. Shaped like the header and the two position cards that are about to replace it, so the
 * layout does not jump when they arrive.
 */
function ProposalSkeleton() {
  return (
    <div className="space-y-8">
      <Card>
        <CardContent className="space-y-4">
          <span className="sr-only" role="status">
            Prüfung wird geladen …
          </span>
          <Skeleton className="h-5 w-64" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-3">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-40 w-full" />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-3">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-40 w-full" />
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * The review screen's only stateful component.
 *
 * State is deliberately shallow: one proposal, one error, one pending flag. There is no client-side
 * cache and no optimistic update — a decision changes the engine's record, and the screen shows what
 * the engine returned rather than what it hoped would happen.
 *
 * ## Layout: sections, not tabs
 *
 * The five parts of a proposal used to be five tabs, which meant that at any moment four fifths of
 * the result were not on the screen — including, by default, every blocked position. A tab strip is
 * right when the panels are alternatives; these are not alternatives, they are one document. What a
 * reviewer is doing is comparing them: this Ziffer was charged, that one was suppressed, and the
 * question is whether the suppression is correct.
 *
 * So the two tables are stacked, each the full width of the page. They were side by side at 3:2,
 * which left the blocked table 440px for a Ziffer, a GOÄ legend and a reason badge; measuring the
 * repair is what killed the whole idea, because the accepted table's six columns have an intrinsic
 * width of 647px and half of this page never exceeds 604px. Side by side, one of the two always
 * scrolls sideways. The two prose panels below *are* side by side — they are compact rows and they
 * fit — and the audit trail is last and collapsed: it is the longest section by far and it is
 * consulted, not read.
 *
 * It also makes the screen printable in one pass, which a tab strip cannot be: a printed proposal
 * that silently omitted the blocked positions would be a misleading document.
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
    <div className="space-y-8">
      {/*
        Picking and running a fixture is an input to the screen, not part of the document it
        produces — and it is a *development* input. It was the first card on the page, which meant
        the screen a physician uses to approve a bill opened with a test-case picker. It is filed
        under a collapsed disclosure now, in a dashed box that says at a glance it is tooling rather
        than a step of the workflow. Everyone who arrives from `/proposals` or the dashboard has a
        proposal already and never opens it.
      */}
      <div className="rounded-2xl border border-dashed px-4 py-3 print:hidden">
        <Disclosure label="Entwicklerwerkzeuge — synthetischen Fall ausführen" printOpen={false}>
          <CaseSelector
            selected={selected}
            onSelect={selectCase}
            onRun={run}
            pending={pending === "solving"}
          />
        </Disclosure>
      </div>

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
          {/*
            First, and sticky: what is being decided stays on screen while the positions scroll past
            it. The decision used to sit in a card here and be several screens above the reader by
            the time they had read the ninth position.
          */}
          <DecisionBar
            proposal={proposal}
            decision={
              <>
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
              </>
            }
          >
            <ExportDialog
              status={proposal.status}
              pending={pending === "exporting"}
              onExport={exportProposal}
            />
          </DecisionBar>

          {exported ? (
            <Alert className="print:hidden">
              <DownloadIcon />
              <AlertTitle>Export heruntergeladen</AlertTitle>
              <AlertDescription>
                <span className="font-mono text-xs">{exported}</span>
              </AlertDescription>
            </Alert>
          ) : !isDraft ? (
            <Alert className="print:hidden">
              <LockIcon />
              <AlertTitle>Bereits entschieden</AlertTitle>
              <AlertDescription>
                Der Status dieses Vorschlags steht fest. Ein erneuter Statuswechsel wird von der
                Engine mit HTTP 409 abgelehnt — Freigeben und Ablehnen sind deshalb deaktiviert.
              </AlertDescription>
            </Alert>
          ) : null}

          <ProposalHeader proposal={proposal} />
          <RuleCoverageBanner proposal={proposal} />

          {/*
            One under the other, each the full width of the page.

            They were side by side at 3:2, and the blocked table's Beschreibung column got 128px of
            it — three words to a line, with the reason badge hard against the right edge. Halving
            the split instead of ending it was the obvious repair and the measurements refuse it:
            the accepted table's six columns have an intrinsic width of **647px**, and half of this
            page is 472px at 1280 and 604px at the `max-w-7xl` cap. There is no viewport this
            application allows at which an invoice table and an exception table both fit in half of
            it — a 1:1 split just moves the horizontal scrollbar from one card to the other, onto
            the one carrying the money.

            Stacked, both get 1104px. Beschreibung goes from 128px to ~870px and nothing scrolls
            sideways at any width. The cost is about 400px of page height, on a screen that is
            already scrolled through top to bottom.

            The two prose panels below stay side by side: they are compact rows, not tables, and
            they were measured at half width and fit.
          */}
          <Section
            title="Akzeptierte Positionen"
            description="Berechnungsfähig nach den durchgesetzten Regeln. Beträge und Faktoren stammen unverändert aus der Engine."
            count={accepted.length}
            icon={CheckCircle2Icon}
            tone="accepted"
            flush
          >
            <AcceptedPositionsTable coding={coding} />
          </Section>

          <Section
            title="Blockierte Positionen"
            description="Von einer durchgesetzten Regel unterdrückt — mit Regel-ID und Rechtsgrundlage."
            count={blocked.length}
            icon={BanIcon}
            tone="blocked"
            flush
          >
            <BlockedPositionsTable coding={coding} />
          </Section>

          <div className="grid items-start gap-6 lg:grid-cols-2">
            <Section
              title="Dokumentationslücken"
              description="Positionen, deren angesetzter Faktor unter der gesetzlichen Obergrenze liegt."
              count={missing.length}
              icon={FileTextIcon}
            >
              <MissingDocumentationPanel entries={missing} />
            </Section>

            <Section
              title="Hinweise der Engine"
              description="Nach Dringlichkeit sortiert. Fehler und markierte Typen stehen oben."
              count={warnings.length}
              icon={InfoIcon}
            >
              <WarningsPanel warnings={warnings} />
            </Section>
          </div>

          {/*
            Collapsed on screen, expanded on paper. It is the longest section on the page and the one
            nobody reads until they are disputing something — but a printed proposal whose proof
            trees were silently missing would be the wrong document entirely.
          */}
          <CollapsibleSection
            title="Beweis und Audit-Trail"
            description="Was geprüft wurde, welche Regeln liefen, und der Beweisbaum je Position."
            icon={ScrollTextIcon}
          >
            <AuditTrailPanel auditTrail={auditTrail} />
          </CollapsibleSection>
        </>
      ) : null}

      {/*
        Unchanged for a plain visit to /review — the same card, the same words. The only addition is
        that it stays out of the way while a deep link is in flight, so a reader who clicked a row
        is never told there is nothing here before the fetch has answered.
      */}
      {!proposal && !shownError && !loadingDeepLink ? (
        <Empty className="border">
          <EmptyMedia variant="icon">
            <PlayIcon />
          </EmptyMedia>
          <EmptyTitle>Kein Vorschlag ausgewählt</EmptyTitle>
          <EmptyDescription>
            Öffnen Sie eine Prüfung über <strong>Alle Prüfungen</strong> in der Navigation oder über
            die Übersicht. Zum Ausprobieren lässt sich oben unter{" "}
            <strong>Entwicklerwerkzeuge</strong> ein synthetischer Fall ausführen; die Engine muss
            dafür unter <span className="font-mono text-xs">ENGINE_BASE_URL</span> erreichbar sein
            (Standard <span className="font-mono text-xs">http://localhost:8000</span>).
          </EmptyDescription>
        </Empty>
      ) : null}
    </div>
  )
}
