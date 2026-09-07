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
 * A key that survives the list changing under it.
 *
 * `code` alone is not unique and never was: one systematic export mistake produces one issue per
 * position, so a refused delivery routinely carries forty issues all coded
 * `padnext_position_without_ziffer`. `location` is what separates them — it is the XML path of the
 * position the finding is about, which is exactly the identity a reader would use.
 *
 * The index stays as the last resort rather than as the key. Two issues can share a code *and* a
 * location (a position that is both unreadable and mispriced), and a duplicate key is a React
 * warning and a reconciliation that reuses the wrong node — which is the failure class this file
 * was audited for. Position is the only thing left that distinguishes those two, and within one
 * response it is stable: the array is rendered in the order the engine sent it and is never sorted,
 * filtered or reordered in the browser.
 */
function issueKey(
  issue: { code: string; location?: string },
  index: number
): string {
  return `${issue.code}::${issue.location ?? ""}::${index}`
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
      {/*
        ## `translate="no"` is what stops this screen crashing, and it is not a workaround

        The reported failure was `NotFoundError: Failed to execute 'insertBefore' on 'Node'`,
        intermittently, after a 422. Nothing in this subtree renders differently on the server than
        on the client — no clock, no `localStorage`, no `typeof window`, no random key — and it does
        not have to for that error to happen. It happens when something *outside* React edits the
        document: Chrome's built-in translator replaces every text node with a `<font>` wrapper of
        its own, so the sibling React kept a reference to is no longer a child of the parent it asks
        to insert before, and the call throws. Intermittent, because it is a race between the
        translator's pass and React's.

        The trigger is this component specifically. `<html lang="de">` on a browser set to any other
        language is exactly the condition Chrome offers to translate on, and a refusal report is the
        largest block of German prose the application ever renders — several hundred words arriving
        at once, which is also what makes the translator's pass long enough to overlap a render.

        `translate="no"` is the standards-defined way to say this subtree must not be rewritten, and
        it is the correct answer here on the merits rather than merely the convenient one. What is
        inside is a GOÄ code, an XML path, a shell command, and a legally-adjacent message the engine
        deliberately ships in both languages — a machine translation of any of those is wrong, and of
        the command it is actively harmful. The reader who wants English has the toggle, which serves
        the engine's own English text.

        `notranslate` alongside it: the attribute is what the HTML spec defines, the class is what
        Google's translator has honoured for longer, and neither costs anything.

        `suppressHydrationWarning` covers the residue. It stops React tearing down and regenerating
        this whole tree over a text node some extension has already touched — the regeneration being
        the step that turns a cosmetic difference into a thrown `insertBefore`.
      */}
      <div
        className="notranslate space-y-4"
        translate="no"
        suppressHydrationWarning
      >
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
            <h3 className="text-sm font-medium" lang={language}>
              {language === "de"
                ? "Das muss geändert werden, damit die Datei geprüft werden kann"
                : "This must change before the file can be audited"}
            </h3>
            <div className="space-y-1.5">
              {errors.map((issue, index) => (
                <ErrorDetail key={issueKey(issue, index)} issue={issue} />
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
              <span
                className="min-w-0 flex-1 text-sm font-medium"
                lang={language}
              >
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
                <ErrorDetail key={issueKey(issue, index)} issue={issue} />
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
