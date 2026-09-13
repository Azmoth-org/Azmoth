"use client"

import { FileUpIcon, FlagIcon, Loader2Icon } from "lucide-react"
import { useRef, useState } from "react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"

import { AnonymisationGate } from "@/components/padnext/anonymisation-gate"
import { BucketSummary } from "@/components/padnext/bucket-summary"
import { CatalogScopeNotice } from "@/components/padnext/catalog-scope-notice"
import { FindingsPanel } from "@/components/padnext/findings-panel"
import { PilotWarningsPanel } from "@/components/padnext/pilot-warnings-panel"
import { PositionsTable } from "@/components/padnext/positions-table"
import { SinglePruefberichtButton } from "@/components/padnext/pruefbericht-button"
import { ReportProvenance } from "@/components/padnext/report-provenance"
import {
  ReportSectionNav,
  type ReportSection,
} from "@/components/padnext/report-section-nav"
import { ValidationErrorList } from "@/components/padnext/validation-error-list"
import { ErrorPanel } from "@/components/review/error-panel"
import { ZifferReportDialog } from "@/components/rules/ziffer-report-dialog"
import { auditPadnextFile } from "@/lib/padnext/client"
import { toValidationReport, type PadnextResult } from "@/lib/padnext/types"
import { pruefenButtonState } from "@/lib/padnext/upload-state"

/** What the engine's reader accepts: a `.padx` container, or a bare payload/order file. */
const ACCEPTED = ".padx,.xml,.auf"

/**
 * Upload a PADnext delivery and render the audit.
 *
 * The file's *bytes* never touch component state — they are read straight into the request body
 * once the reader submits. What is kept, for exactly as long as a report is on screen, is the
 * `File` handle itself, and only so `SinglePruefberichtButton` can produce the printable
 * Prüfbericht from the same delivery. A `File` is a reference to bytes the browser already holds on
 * behalf of the file input, not a second copy in JavaScript memory, and the next upload replaces it
 * — so the window in which this page can name a billing document is the window in which it is
 * displaying one.
 *
 * The alternative was to have the PDF button re-open the file picker, which asks a user to find the
 * same file twice to get two views of one audit. The one it was weighed against — caching the
 * rendered report on the server — is the option that would actually change what this endpoint is:
 * the single audit stores nothing, and that is what keeps it outside tenancy.
 *
 * ## Selecting a file is not submitting it
 *
 * Choosing a file only stores its handle and its name; the engine is not called until the reader
 * presses "PADnext-Datei prüfen", and that button stays disabled until a file is selected *and*
 * `AnonymisationGate` is checked — see `pruefenButtonState`. That is a deliberate act placed between
 * "I have a file" and "the engine reads it", for the failure that actually happens in a pilot: not
 * somebody defeating a control, but somebody exporting from their PVS, forgetting the anonymisation
 * step, and uploading out of habit. Both the file and the confirmation are cleared after every
 * submission, per `AnonymisationGate`'s own note on why it resets per file rather than per session.
 *
 * **It is not what enforces the rule.** The engine refuses a delivery flagged `echtdaten="true"`
 * with `REAL_DATA_REFUSED` before it reads a position, and that refusal is not reachable from this
 * browser. If both were somehow bypassed the engine would still say no; if this checkbox were
 * removed the engine would still say no. What the checkbox adds is the moment of deliberation and
 * a written record of whose obligation the pseudonymisation is.
 *
 * A refusal arrives here as a normal error panel carrying the engine's own German message, which
 * names the anonymisation script — so the reader is told what to do rather than only what failed.
 *
 * ## One refusal, one surface
 *
 * A validation failure renders as `ValidationErrorList` and nothing else. It replaced a layout
 * that showed both — `ErrorPanel` above, the list below — on the reasoning that the panel names
 * the `error_code` and the HTTP status while the list carries the problems. In front of a real
 * refusal that reasoning does not survive: the engine adopts the *primary* problem's message for
 * the envelope, so the panel's title was the first card restated, in full, in both languages, as
 * an unwrapped red paragraph, above a "Details (unverändert)" dump of the identical payload the
 * cards below were rendering. Every failure was shown twice, and the worse copy was on top.
 *
 * The `error_code` was not lost with it — it is the badge on the card it belongs to, which is
 * also the only place it is unambiguous once a delivery has four problems with four codes. The
 * payload an integrator diffs against the API is still one click away, at the bottom of the list
 * (`raw`, below), rather than open by default in the middle of the page.
 *
 * ## What still renders the legacy panel
 *
 * Everything that is not a batched validation failure: a quota refusal, an unreachable engine, a
 * 5xx, an engine old enough not to send the list. Those carry no `errors` array, so
 * `toValidationReport` returns null, and they render exactly as they always have — a screen that
 * assumed the list was present would answer a 503 with an empty "0 Fehler" card.
 *
 * The switch is `errors.length`, not the presence of a report: a report whose blocking list is
 * empty says nothing about what failed, so the panel stays as the thing that names it.
 */
export function AuditWorkbench() {
  const [result, setResult] = useState<PadnextResult | null>(null)
  const [pending, setPending] = useState(false)
  // The file chosen but not yet submitted. Cleared, along with `confirmed`, after every submission
  // attempt — see `AnonymisationGate`'s note on why the confirmation is per file, not per session.
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  // The delivery the report on screen describes, kept so it can be rendered as a PDF. Cleared
  // whenever the report it belongs to is — see the note above.
  const [audited, setAudited] = useState<File | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // The "Regel fehlt?" dialog — one instance shared by the page-level button (manual entry) and
  // every row's own flag icon (prefilled). `reportZiffer` is intentionally separate from `result`:
  // opening the dialog must not touch the report on screen.
  const [reportDialogOpen, setReportDialogOpen] = useState(false)
  const [reportZiffer, setReportZiffer] = useState("")

  function openZifferReport(ziffer: string) {
    setReportZiffer(ziffer)
    setReportDialogOpen(true)
  }

  // Derived rather than stored: it is a projection of `result`, and a second piece of state that
  // had to be cleared alongside it is a second piece of state that will one day not be.
  const validation =
    result?.kind === "error" ? toValidationReport(result.error) : null
  // Whether the list is allowed to *be* the error surface rather than sit beneath one. It can
  // only replace the panel when it has something blocking to show; see the note above.
  const batched =
    validation && (validation.errors?.length ?? 0) > 0 ? validation : null

  function onSelect(file: File | undefined) {
    if (!file) return
    setSelectedFile(file)
    // A newly chosen file is a new statement: any confirmation or report about a previous one no
    // longer applies to it.
    setConfirmed(false)
    setResult(null)
    setAudited(null)
  }

  async function onSubmit() {
    if (!selectedFile || !confirmed || pending) return
    setPending(true)
    try {
      const outcome = await auditPadnextFile(selectedFile)
      setResult(outcome)
      // Only alongside a report. A refusal has no document to export, and holding the file after
      // one would keep a delivery around for a screen that is showing an error.
      setAudited(outcome.kind === "report" ? selectedFile : null)
    } finally {
      setPending(false)
      // Per file, not per session — see `AnonymisationGate`. The next upload is a new statement.
      setSelectedFile(null)
      setConfirmed(false)
      // Without this, picking the same file twice in a row fires no `change` event and the second
      // attempt looks like a dead button.
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  const buttonState = pruefenButtonState({
    hasFile: selectedFile !== null,
    confirmed,
    pending,
  })

  // `Befunde` only exists on screen when `FindingsPanel` actually renders something — a report
  // with no findings renders no such section, and a nav link to a heading that is not on the page
  // would just be a dead click.
  const reportSections: ReportSection[] =
    result?.kind === "report"
      ? [
          { id: "padnext-buckets-heading", label: "Bewertung" },
          { id: "padnext-positions-heading", label: "Positionen" },
          ...((result.report.findings?.length ?? 0) > 0
            ? [{ id: "padnext-findings-heading", label: "Befunde" }]
            : []),
          { id: "padnext-meta-heading", label: "Meta" },
        ]
      : []

  return (
    <div className="space-y-6">
      <CatalogScopeNotice />

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="flex flex-wrap items-center gap-4">
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED}
              className="hidden"
              onChange={(event) => onSelect(event.target.files?.[0])}
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => inputRef.current?.click()}
              disabled={pending}
            >
              <FileUpIcon aria-hidden />
              Datei auswählen
            </Button>
            <div className="min-w-0 text-xs text-muted-foreground">
              {selectedFile ? (
                <span className="font-mono break-all">
                  {selectedFile.name}
                </span>
              ) : (
                <span>
                  <span className="font-mono">.padx</span>-Container oder{" "}
                  <span className="font-mono">*_padx.xml</span>-Nutzdaten. Nur
                  pseudonymisierte Testdaten.
                </span>
              )}
            </div>
          </div>

          <AnonymisationGate
            checked={confirmed}
            onCheckedChange={setConfirmed}
            disabled={selectedFile === null}
          />

          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={() => void onSubmit()}
              disabled={buttonState.disabled}
            >
              {pending ? (
                <>
                  <Loader2Icon className="animate-spin" aria-hidden />
                  Prüfung läuft…
                </>
              ) : (
                <>
                  <FileUpIcon aria-hidden />
                  PADnext-Datei prüfen
                </>
              )}
            </Button>
            {buttonState.reason ? (
              <span className="text-xs text-muted-foreground">
                {buttonState.reason}
              </span>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {result?.kind === "error" ? (
        batched ? (
          // The whole failure, once. `raw` is what the panel's "Details (unverändert)" block used
          // to show — same payload, same completeness, collapsed and at the bottom.
          <ValidationErrorList report={batched} raw={result.error.details} />
        ) : (
          <>
            <ErrorPanel error={result.error} />
            {/*
              A report with no blocking problem, beside a refusal that is not about the delivery —
              the anonymisation gate raises on a file the validator itself calls valid. The panel
              names that refusal; the list is here for the warnings and the preview, which are the
              only thing in the report and would otherwise be dropped. No `raw`: the panel's own
              "Details (unverändert)" block is already showing it.
            */}
            {validation ? <ValidationErrorList report={validation} /> : null}
          </>
        )
      ) : null}

      {result?.kind === "report" ? (
        <>
          <div className="flex flex-wrap justify-end gap-2 print:hidden">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => openZifferReport("")}
            >
              <FlagIcon aria-hidden />
              Regel fehlt? Ziffer melden
            </Button>
            {audited ? <SinglePruefberichtButton file={audited} /> : null}
          </div>
          <ReportSectionNav
            sections={reportSections}
            trailing={
              <Badge variant="outline" className="font-mono">
                Katalogstand {result.report.catalog_version || "—"}
              </Badge>
            }
          />
          <PilotWarningsPanel report={result.report} />
          <BucketSummary report={result.report} />
          <ReportProvenance report={result.report} />
          <PositionsTable report={result.report} onReportZiffer={openZifferReport} />
          <FindingsPanel report={result.report} />
          <ZifferReportDialog
            open={reportDialogOpen}
            onOpenChange={setReportDialogOpen}
            initialZiffer={reportZiffer}
            receiptHash={result.report.receipt_hash}
          />
        </>
      ) : null}

      {result === null && !pending ? (
        <Alert>
          <AlertTitle>Noch keine Prüfung</AlertTitle>
          <AlertDescription>
            Eine PADnext-Lieferung enthält bereits kodierte Positionen. Diese
            Prüfung rechnet sie gegen den eigenen Katalog nach und trennt das
            Ergebnis in drei Gruppen: nachweislich falsch, bestätigt korrekt,
            und unbestätigt. Die dritte Gruppe ist kein Befund gegen die Praxis,
            sondern die Grenze unserer Regelabdeckung.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
