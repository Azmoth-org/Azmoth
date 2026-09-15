"use client"

import { AlertTriangleIcon, RotateCwIcon } from "lucide-react"
import * as React from "react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"

import type { ReviewError } from "@/lib/review/types"

/** The sentence shown for anything not named below, and for anything that has no useful advice. */
const GENERIC_MESSAGE =
  "Ein technischer Fehler ist aufgetreten. Bitte versuchen Sie es erneut oder " +
  "kontaktieren Sie den Support."

/**
 * What each failure means to the person who hit it. German, specific, and actionable or silent.
 *
 * Every entry here is a promise that the reader can do something with the sentence. A failure whose
 * only honest description is "our software broke" is deliberately absent and falls through to
 * `GENERIC_MESSAGE` — an entry that restates the error code in longer words is worse than no entry,
 * because it costs the reader the time to find out it says nothing.
 */
const MESSAGES: Record<string, string> = {
  // Infrastructure. The reader cannot fix any of these and must not be told to try; what they can
  // do is wait or call us, and that is what these say.
  engine_unreachable:
    "Der Prüfdienst ist zurzeit nicht erreichbar. Bitte versuchen Sie es in einigen Minuten " +
    "erneut — falls das Problem bestehen bleibt, kontaktieren Sie den Support.",
  engine_unreachable_timeout:
    "Der Prüfdienst antwortet zurzeit nicht. Bitte versuchen Sie es in einigen Minuten erneut — " +
    "falls das Problem bestehen bleibt, kontaktieren Sie den Support.",
  proxy_unreachable:
    "Die Verbindung zum Server ist unterbrochen. Bitte prüfen Sie Ihre Internetverbindung und " +
    "laden Sie die Seite neu.",
  rules_engine_failed: GENERIC_MESSAGE,
  validation_failed: GENERIC_MESSAGE,
  empty_response: GENERIC_MESSAGE,
  unparsable_response: GENERIC_MESSAGE,
  unexpected_response_shape: GENERIC_MESSAGE,

  // The solver gave up. Worth its own sentence because the *absence* of a draft is deliberate here
  // and a reader who is not told that will read it as a lost result.
  solver_timeout:
    "Die Prüfung hat zu lange gedauert und wurde abgebrochen. Es wird bewusst kein " +
    "unvollständiger Entwurf ausgegeben. Bitte versuchen Sie es erneut oder prüfen Sie die " +
    "Rechnung in kleineren Teilen.",

  // The reader's own input or their own workflow. These are the ones where a specific sentence
  // actually saves them something.
  validation_error:
    "Die hochgeladene Datei entspricht nicht dem erwarteten Format. Bitte prüfen Sie die Datei " +
    "und laden Sie sie erneut hoch.",
  illegal_transition:
    "Dieser Schritt ist für den aktuellen Status nicht möglich. Ein abgelehnter oder bereits " +
    "exportierter Vorschlag kann nicht erneut entschieden werden, und ein Export ist nur einmal " +
    "möglich.",
  proposal_not_found:
    "Unter dieser Adresse ist kein Vorschlag gespeichert. Bitte prüfen Sie den Link oder suchen " +
    "Sie den Vorschlag über „Alle Prüfungen“.",
  malformed_proposal_id:
    "Der Link ist unvollständig. Bitte öffnen Sie den Vorschlag über „Alle Prüfungen“.",
  malformed_batch_id:
    "Der Link ist unvollständig. Bitte öffnen Sie den Stapel über die Stapel-Historie.",
  batch_not_found:
    "Unter dieser Adresse ist kein Stapel gespeichert. Bitte prüfen Sie den Link oder laden Sie " +
    "die Dateien erneut hoch.",
  batch_not_completed:
    "Der Stapel ist noch nicht vollständig geprüft. Der Export ist erst möglich, wenn alle " +
    "Dateien abgeschlossen sind.",
  unreadable_request_body:
    "Für den Export wird ein Name benötigt. Bitte tragen Sie ein, wer den Export vornimmt.",
  no_active_organization:
    "Diese Sitzung ist keiner Praxis zugeordnet. Bitte wählen Sie oben links eine Organisation " +
    "aus oder legen Sie eine an.",
  unauthenticated:
    "Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
}

/**
 * One failure, in the same shape everywhere the app can fail — written for the person who hit it.
 *
 * ## What this panel used to show, and why none of it belongs here
 *
 * It showed the reader three things they could do nothing with:
 *
 *   - **Shell commands.** `engine_unreachable` answered with *"Engine starten: cd apps/engine &&
 *     .venv/bin/uvicorn app.main:app --port 8000"*. `proxy_unreachable` said *"pnpm dev neu
 *     starten"*. `unexpected_response_shape` said *"python scripts/export_openapi.py, dann pnpm
 *     generate:contracts"*. A customer has no checkout, no terminal on our machine and no business
 *     being told to restart our services; what the instruction actually communicates is that they
 *     are looking at somebody's development build.
 *   - **An `error_code` badge**, in monospace, beside the message. `solver_timeout` is a token for
 *     a bug tracker, not a sentence.
 *   - **The raw JSON `details`**, pretty-printed under the message — the engine's internal payload,
 *     verbatim, in the customer's face.
 *
 * All three were right for the audience the screen was built for. None of them survives the
 * product being shown to somebody who is evaluating whether to buy it.
 *
 * ## What replaced them
 *
 * A German sentence per failure, saying what happened in terms of *their* work, and what to do
 * next when there is something to do. Where there is nothing useful to say, the generic sentence
 * is used rather than a specific-sounding one that says nothing: *"Ein technischer Fehler ist
 * aufgetreten. Bitte versuchen Sie es erneut oder kontaktieren Sie den Support."*
 *
 * **The diagnostic detail is not deleted, it is moved.** Every render logs the code, the HTTP
 * status and the whole `details` payload through `console.error`, so the browser console still has
 * exactly what the panel used to print — which is where a developer looks anyway, and where a
 * customer does not. A support call still starts with "open the console and send me what is red".
 *
 * `onRetry` is optional and should only be passed for a failure that can plausibly succeed on a
 * second attempt — see `isRetryable` in `lib/deep-link.ts`. A retry button on a 404 is a lie: it
 * asks the identical question and gets the identical answer, and the reader spends a click finding
 * that out. `pending` disables it while the retry is in flight, so a slow engine does not collect a
 * queue of clicks.
 */

export function ErrorPanel({
  error,
  onRetry,
  pending = false,
}: {
  error: ReviewError
  onRetry?: () => void
  pending?: boolean
}) {
  /**
   * Everything the panel no longer prints, kept where a developer can still reach it.
   *
   * In an effect rather than in render, so React's double-invocation in development does not log
   * each failure twice, and keyed on the fields that identify the failure so a re-render for an
   * unrelated reason does not log it again either.
   */
  React.useEffect(() => {
    console.error("[azmoth] request failed", {
      error_code: error.error,
      status: error.status,
      message: error.message,
      details: error.details,
    })
    // `details` is deliberately not a dependency: it is a fresh object on every render, so
    // including it would log the same failure again on every unrelated re-render. The three
    // scalars below identify a failure; the payload logged is whatever is current when they change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error.error, error.status, error.message])

  return (
    <Alert variant="destructive">
      <AlertTriangleIcon />
      {/*
        `min-w-0` on both cells is what keeps this panel inside the content column. `Alert` lays
        itself out as `grid-cols-[auto_1fr]`, and a grid item's automatic minimum is its content's
        intrinsic width — so a long German compound widens the `1fr` column past the page and puts
        a scrollbar on the viewport. `break-words` is the same guard for the sentence itself.
      */}
      <AlertTitle className="min-w-0">
        <span className="break-words">Die Aktion konnte nicht ausgeführt werden</span>
      </AlertTitle>
      <AlertDescription className="min-w-0 space-y-3">
        <p className="break-words text-foreground/80">
          {MESSAGES[error.error] ?? GENERIC_MESSAGE}
        </p>
        {onRetry ? (
          <Button
            variant="outline"
            size="sm"
            onClick={onRetry}
            disabled={pending}
          >
            <RotateCwIcon
              className={pending ? "animate-spin" : undefined}
              aria-hidden
            />
            {pending ? "Wird erneut geladen…" : "Erneut versuchen"}
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
  )
}
