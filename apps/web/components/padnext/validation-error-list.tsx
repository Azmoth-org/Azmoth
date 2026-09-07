"use client"

import { AlertTriangleIcon, ChevronRightIcon, XCircleIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@workspace/ui/components/collapsible"
import { Button } from "@workspace/ui/components/button"

import { ErrorDetail } from "@/components/padnext/error-detail"
import { ParsedPreview } from "@/components/padnext/parsed-preview"
import {
  IssueLanguageProvider,
  useIssueLanguageState,
} from "@/lib/padnext/issue-language"
import type { PadnextValidationReport } from "@/lib/padnext/types"

/** `JSON.stringify` that cannot throw: a payload with a cycle must still render as *something*. */
function formatRaw(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? String(value)
  } catch {
    return String(value)
  }
}

/**
 * Every problem with one delivery: blocking ones listed, notes folded away, preview underneath.
 *
 * ## The grouping is by `blocking`, not by `severity`
 *
 * They are different fields on purpose. A claimed position with no `@ziffer` arrives as
 * `severity: "error"` and `blocking: false` — a serious finding that does *not* refuse the
 * delivery, because refusing over it would refuse exactly the export a practice most needs read
 * ("framing is fatal, positions are advisory", see `app/padnext/schema.py`). Grouping by severity
 * would put it in the top box, where a reader would take it as one of the things standing between
 * them and a report, and go and fix something that was never blocking.
 *
 * So: the first group is what must change before this file can be audited. The second is what the
 * report will say about it once it is — and that second group is **closed by default**, with its
 * count on the trigger. It is routinely the longer of the two (one note per unreadable position),
 * and it is by definition not what the reader has to act on now.
 *
 * ## Why the counts come from the report and not from the arrays
 *
 * `error_count` is the honest total; `errors` is capped at a hundred, because one systematic
 * export mistake produces one issue per position and a response carrying nine hundred helps
 * nobody. Counting the array would quietly under-report a flood — the reader would be told there
 * are a hundred problems in a file that has nine hundred, act on the hundred, and be refused
 * again. `*_omitted` is rendered for the same reason.
 *
 * ## Layout
 *
 * One column at every width. The content is prose and code, both of which read worse in a narrow
 * measure, and there is nothing here to compare side by side. What changes with width is padding
 * and the header, which wraps the language toggle under the counts rather than shrinking it.
 */
export function ValidationErrorList({
  report,
  raw,
}: {
  report: PadnextValidationReport
  /**
   * The untouched `details` payload, rendered collapsed at the very bottom.
   *
   * Passed only when this list is the *whole* error surface — see `AuditWorkbench`. When the
   * legacy `ErrorPanel` renders instead, it already carries its own "Details (unverändert)"
   * block, and two raw dumps on one screen is the wall this component exists to remove.
   *
   * Omitted, nothing is rendered: the escape hatch is for the reader who has to compare what the
   * cards say against what the engine actually sent, and it costs them one click rather than
   * costing every other reader a screen of JSON.
   */
  raw?: unknown
}) {
  const [language, setLanguage] = useIssueLanguageState()

  const errors = report.errors ?? []
  const warnings = report.warnings ?? []
  const errorCount = report.error_count ?? errors.length
  const warningCount = report.warning_count ?? warnings.length

  return (
    <IssueLanguageProvider language={language}>
      <div className="space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {errorCount > 0 ? (
              <Badge variant="destructive" className="gap-1.5">
                <XCircleIcon className="size-3" aria-hidden />
                {errorCount} {errorCount === 1 ? "Fehler" : "Fehler"}
              </Badge>
            ) : null}
            {warningCount > 0 ? (
              <Badge variant="secondary" className="gap-1.5">
                <AlertTriangleIcon className="size-3" aria-hidden />
                {warningCount} {warningCount === 1 ? "Hinweis" : "Hinweise"}
              </Badge>
            ) : null}
            {report.status === "parse_failed" ? (
              <span className="text-xs text-muted-foreground">
                Die Datei konnte nicht als Dokument gelesen werden.
              </span>
            ) : null}
          </div>

          {/*
            German is the default and the first item. The toggle exists so that one reader sees
            exactly the language they came for, instead of both stacked — see
            `lib/padnext/issue-language.tsx`.

            Two buttons rather than a ToggleGroup: this control has exactly two mutually exclusive
            values that can never both be off, and a group primitive built around a set of
            selections has to be guarded against deselecting the active item — which would blank
            every message on the page. `aria-pressed` carries the state to a screen reader, and
            `role="group"` with a label says what the pair is for.
          */}
          <div
            role="group"
            aria-label="Sprache der Meldungen"
            className="flex shrink-0 gap-0.5 rounded-md border p-0.5"
          >
            {(["de", "en"] as const).map((option) => (
              <Button
                key={option}
                type="button"
                variant={language === option ? "secondary" : "ghost"}
                size="sm"
                aria-pressed={language === option}
                onClick={() => setLanguage(option)}
                className="h-6 px-2 text-[11px] font-medium"
              >
                {option.toUpperCase()}
              </Button>
            ))}
          </div>
        </header>

        {errors.length > 0 ? (
          <section className="space-y-2">
            <h3 className="text-sm font-medium">
              {language === "de"
                ? "Das muss geändert werden, damit die Datei geprüft werden kann"
                : "This must change before the file can be audited"}
            </h3>
            <div className="space-y-1.5">
              {errors.map((issue, index) => (
                <ErrorDetail key={`${issue.code}-${index}`} issue={issue} />
              ))}
            </div>
            {report.errors_omitted ? (
              <p className="text-xs text-muted-foreground">
                {report.errors_omitted} weitere Fehler werden nicht einzeln
                aufgeführt. Sie haben vermutlich dieselbe Ursache — beheben Sie
                die oben genannten und laden Sie die Datei erneut hoch.
              </p>
            ) : null}
          </section>
        ) : null}

        {warnings.length > 0 ? (
          // Closed by default: usually the longer list, and by definition not what has to change
          // now. The count is on the trigger so folding it away never hides how much is in there.
          <Collapsible className="rounded-lg border">
            <CollapsibleTrigger className="group flex w-full items-center gap-2 p-3 text-left">
              <ChevronRightIcon
                className="size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90"
                aria-hidden
              />
              <span className="min-w-0 flex-1 text-sm font-medium">
                {language === "de"
                  ? "Hinweise — sie verhindern die Prüfung nicht"
                  : "Notes — these do not block the audit"}
              </span>
              <Badge variant="secondary" className="shrink-0">
                {warningCount}
              </Badge>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-1.5 border-t p-3">
              {warnings.map((issue, index) => (
                <ErrorDetail key={`${issue.code}-${index}`} issue={issue} />
              ))}
              {report.warnings_omitted ? (
                <p className="text-xs text-muted-foreground">
                  {report.warnings_omitted} weitere Hinweise werden nicht
                  einzeln aufgeführt.
                </p>
              ) : null}
            </CollapsibleContent>
          </Collapsible>
        ) : null}

        {report.parsed_preview ? (
          <ParsedPreview preview={report.parsed_preview} />
        ) : null}

        {raw === undefined || raw === null ? null : (
          /*
            The developer escape hatch, and the reason the cards above are allowed to be a
            summary. Closed by default and last on the page: an open dump is what made the
            previous version of this screen unreadable, and a payload carrying one issue object
            per position is thousands of lines that no practice will ever read.

            A native <details> rather than a Collapsible — no state of its own, keyboard- and
            screen-reader-accessible as it stands, and it prints open, which is the one time
            somebody wants the payload beside the report.

            The wrapper, not the <pre>, owns the scrolling: `max-w-full` gives it a definite width
            to scroll *within*, so an unbroken 400-character JSON line moves this box's own
            scrollbar instead of widening the page under it.
          */
          <details className="group/raw max-w-full rounded-lg border bg-muted/30">
            <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-muted-foreground marker:content-none hover:text-foreground">
              <span className="inline-flex items-center gap-1.5">
                <ChevronRightIcon
                  className="size-3 shrink-0 transition-transform group-open/raw:rotate-90"
                  aria-hidden
                />
                Rohdetails (JSON)
              </span>
            </summary>
            <div className="max-h-96 max-w-full overflow-x-auto overflow-y-auto border-t">
              <pre className="w-max min-w-full p-3 font-mono text-xs leading-relaxed text-foreground">
                {formatRaw(raw)}
              </pre>
            </div>
          </details>
        )}
      </div>
    </IssueLanguageProvider>
  )
}
