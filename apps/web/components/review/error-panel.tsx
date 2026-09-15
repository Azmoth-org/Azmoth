"use client"

import { AlertTriangleIcon, RotateCwIcon } from "lucide-react"
import * as React from "react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"

import { messageFor } from "@/lib/review/error-messages"
import type { ReviewError } from "@/lib/review/types"

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
 * The per-code sentences live in `lib/review/error-messages.ts`, as a plain lookup (`messageFor`)
 * rather than inline here — so the mapping is unit-testable without rendering a component, which
 * is what caught `illegal_transition` describing only two of the three refusals it actually covers.
 * `error.message` itself is never shown, only logged: it is the engine's own text, written for
 * whoever reads a log line or an API response directly, and not vetted for a customer's screen the
 * way each entry in that table is.
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
          {messageFor(error)}
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
