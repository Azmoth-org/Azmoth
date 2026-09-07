"use client"

import {
  AlertTriangleIcon,
  ChevronRightIcon,
  InfoIcon,
  XCircleIcon,
} from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@workspace/ui/components/collapsible"

import { FixSuggestion } from "@/components/padnext/fix-suggestion"
import {
  issueTexts,
  useIssueLanguage,
} from "@/lib/padnext/issue-language"
import type { PadnextValidationIssue } from "@/lib/padnext/types"

/**
 * One validation problem as a single closed line, opening to the reasoning and the fix.
 *
 * ## The wall this replaced
 *
 * The first version rendered, for every issue, all at once: the long message, the paragraph of
 * legal reasoning, the numbered fix, the command, and the whole thing again in English. Four
 * problems produced roughly two screens of prose with no visual hierarchy — and the failure of
 * that layout is not that it is ugly. It is that a reader cannot *count* their problems. Before
 * deciding what to do they need to know whether they are looking at one thing or four, and a wall
 * of text answers that question only by scrolling to the bottom of it. Everything past the first
 * sentence, including the reasoning this codebase deliberately sends, was making the first
 * sentence harder to find.
 *
 * So: closed is one line — icon, code, `summary_de`, location. Four problems are four lines, and
 * the reader picks. Open is message → why → fix → command, in that order, for the one they picked.
 *
 * ## Why the reasoning survives the collapse
 *
 * It would have been simpler to delete `why_de`. It is not decoration: `echtdaten="1"` is one
 * character from `echtdaten="0"`, and an instruction without a reason does not distinguish
 * "declare what your file is" from "make the error go away" — the second reading ends with real
 * patient data in a system that has no lawful basis for it. Collapsing it keeps that argument one
 * click from the reader who is about to take the shortcut, while charging nothing to the reader
 * who already knows. Deleting it would have removed the argument.
 *
 * ## Colour follows severity, grouping follows `blocking`
 *
 * Different fields, and the gap between them is the engine's central rule: a claimed position that
 * cannot be checked is `severity: "error"` and `blocking: false`, because refusing a delivery over
 * one unreadable line would refuse exactly the invoices worth auditing. This component colours by
 * severity and never decides where an issue belongs — `ValidationErrorList` groups by `blocking`.
 */
const TONE = {
  error: {
    Icon: XCircleIcon,
    badge: "destructive" as const,
    row: "border-destructive/30 bg-destructive/[0.03] hover:bg-destructive/[0.06]",
    icon: "text-destructive",
  },
  warning: {
    Icon: AlertTriangleIcon,
    badge: "secondary" as const,
    row: "border-amber-300/60 bg-amber-50/60 hover:bg-amber-50 dark:border-amber-500/25 dark:bg-amber-500/[0.06] dark:hover:bg-amber-500/10",
    icon: "text-amber-600 dark:text-amber-400",
  },
  info: {
    Icon: InfoIcon,
    badge: "outline" as const,
    row: "border-border bg-muted/30 hover:bg-muted/50",
    icon: "text-muted-foreground",
  },
}

export function ErrorDetail({ issue }: { issue: PadnextValidationIssue }) {
  const language = useIssueLanguage()
  const text = issueTexts(issue, language)
  const tone = TONE[issue.severity ?? "error"] ?? TONE.error
  const { Icon } = tone

  return (
    <Collapsible
      // Closed for every issue, including blocking ones. An earlier version opened the blocking
      // ones by default, which reproduced the wall on exactly the report that has the most of
      // them — four blocking problems is four expanded cards, which is where this started.
      className={`rounded-lg border transition-colors ${tone.row}`}
    >
      <CollapsibleTrigger className="group flex w-full items-start gap-2 p-2.5 text-left sm:gap-2.5 sm:p-3">
        <ChevronRightIcon
          className="mt-0.5 size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90"
          aria-hidden
        />
        <Icon className={`mt-0.5 size-4 shrink-0 ${tone.icon}`} aria-hidden />

        {/*
          `min-w-0` on the growing child is what actually makes this responsive: without it a flex
          item refuses to shrink below its content's intrinsic width, and a long summary pushes the
          location chip off the right edge instead of wrapping. Same reason `break-words` is on the
          text — a German compound or an XML path has no spaces to break at.
        */}
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm leading-snug break-words">{text.summary}</p>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Badge
              variant={tone.badge}
              className="px-1.5 py-0 font-mono text-[10px] font-normal"
            >
              {issue.code}
            </Badge>
            {issue.location ? (
              <span className="font-mono text-[10px] break-all text-muted-foreground">
                {issue.location}
              </span>
            ) : null}
            {issue.severity === "error" && issue.blocking === false ? (
              // The one label the two fields make necessary: red, and yet not what is stopping
              // the upload. Without it a reader reasonably concludes that it is.
              <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-normal">
                nicht blockierend
              </Badge>
            ) : null}
          </div>
        </div>
      </CollapsibleTrigger>

      <CollapsibleContent className="space-y-3 border-t px-2.5 pt-3 pb-3 sm:px-3 sm:pl-11">
        {text.message && text.message !== text.summary ? (
          <p className="text-sm leading-relaxed whitespace-pre-line break-words">
            {text.message}
          </p>
        ) : null}

        {text.why ? (
          // A native <details>, not a third Collapsible. The reasoning is a paragraph a minority
          // of readers open, and a summary/details pair is keyboard- and screen-reader-accessible
          // without any state of its own — and it prints open, which matters because these
          // reports get printed.
          <details className="group/why rounded-md border bg-background/60">
            <summary className="cursor-pointer list-none px-2.5 py-2 text-xs font-medium text-muted-foreground marker:content-none hover:text-foreground">
              <span className="inline-flex items-center gap-1.5">
                <ChevronRightIcon
                  className="size-3 transition-transform group-open/why:rotate-90"
                  aria-hidden
                />
                {language === "de" ? "Warum das wichtig ist" : "Why this matters"}
              </span>
            </summary>
            <p className="px-2.5 pb-2.5 text-xs leading-relaxed whitespace-pre-line break-words text-foreground/75">
              {text.why}
            </p>
          </details>
        ) : null}

        {text.fix ? (
          <div className="space-y-1.5">
            <p className="text-xs font-medium">
              {language === "de" ? "Lösung" : "How to fix it"}
            </p>
            <p className="text-xs leading-relaxed whitespace-pre-line break-words text-foreground/75">
              {text.fix}
            </p>
          </div>
        ) : null}

        {issue.command ? (
          <FixSuggestion
            command={issue.command}
            label={language === "de" ? "Befehl" : "Command"}
          />
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  )
}
