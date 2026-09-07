"use client"

import { createContext, useContext, useState, type ReactNode } from "react"

import type { PadnextValidationIssue } from "@/lib/padnext/types"

/**
 * Which language the validation issues render in, for one findings list.
 *
 * ## Why a toggle rather than both languages at once
 *
 * The engine sends every issue twice — German for the practice, English for the PVS integrator
 * reading over their shoulder — and the first version of this UI rendered both, stacked. That
 * doubled the height of a list whose whole problem is height, and it did it by adding text that
 * *no single reader wanted*: the practice does not read the English, the integrator does not need
 * the German, and each of them scrolls past half the page to find their own half. A toggle shows
 * one reader exactly what they came for.
 *
 * German is the default and stays the default. The reader of an error here is a German medical
 * practice; English is the fallback for a minority of the audience, and a language switch that
 * had to be set every time would make the majority pay for the minority.
 *
 * ## Why context rather than a prop
 *
 * The toggle sits on `ValidationErrorList` and the text is read three levels down, in an
 * `ErrorDetail` inside a collapsed section. Threading it through would put a `language` prop on
 * every component in between, none of which have any use for it. It is deliberately NOT persisted:
 * a reader who switches to English for one confusing message should not find the next upload's
 * report in a language their colleague cannot read.
 */
export type IssueLanguage = "de" | "en"

const IssueLanguageContext = createContext<IssueLanguage>("de")

export function IssueLanguageProvider({
  language,
  children,
}: {
  language: IssueLanguage
  children: ReactNode
}) {
  return (
    <IssueLanguageContext.Provider value={language}>
      {children}
    </IssueLanguageContext.Provider>
  )
}

export function useIssueLanguage(): IssueLanguage {
  return useContext(IssueLanguageContext)
}

/** The list's own toggle state. Kept here so the component and the reader agree on the default. */
export function useIssueLanguageState() {
  return useState<IssueLanguage>("de")
}

/**
 * One issue's text in the chosen language, falling back down the chain the engine guarantees.
 *
 * **English is never assumed to exist.** Issues lifted from the reader's own findings
 * (`padnext_position_without_ziffer` and its siblings) carry German only — machine-translating a
 * legally-adjacent message would be worse than showing the German a reader can paste into a
 * search. So every English field falls back to its German twin, and only then to the code, which
 * is ugly and readable where an empty string is a blank card.
 */
export function issueTexts(
  issue: PadnextValidationIssue,
  language: IssueLanguage
) {
  const de = {
    summary: issue.summary_de || issue.message_de || issue.code,
    message: issue.message_de || issue.code,
    why: issue.why_de ?? "",
    fix: issue.fix ?? "",
  }
  if (language === "de") return de

  return {
    summary: issue.summary_en || issue.message_en || de.summary,
    message: issue.message_en || de.message,
    why: issue.why_en || de.why,
    fix: issue.fix_en || de.fix,
  }
}
