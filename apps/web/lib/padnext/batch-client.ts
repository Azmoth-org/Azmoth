/**
 * Browser-side calls to the batch audit proxy: upload once, then poll.
 *
 * Mirrors `lib/padnext/client.ts` — never throws, never returns a half-parsed body. The screen
 * renders either a job whose fields it can trust to exist, or a named error with the raw details
 * attached.
 */

import {
  isBatchAcceptedShape,
  isBatchJobShape,
  toReviewError,
  type BatchJobResult,
  type BatchUploadResult,
  type ReviewError,
} from "@/lib/padnext/batch-types"

/** How often the screen asks the engine how far it has got. The brief's two seconds. */
export const POLL_INTERVAL_MS = 2_000

/**
 * When to give up on a job that never reaches a terminal state.
 *
 * It has to exist, and the reason is stated rather than hidden: the engine processes a batch with
 * FastAPI `BackgroundTasks`, which do not survive a restart, so a job interrupted mid-run stays
 * `PROCESSING` in the database forever. Without a ceiling the browser would poll that row until
 * the tab was closed. Fifteen minutes is far more than a few hundred files need and short enough
 * that a stuck job is reported as stuck.
 */
export const POLL_TIMEOUT_MS = 15 * 60 * 1000

/** The one failure both calls share, and the only one that happens before a response exists. */
function unreachable(cause: unknown): { kind: "error"; error: ReviewError } {
  return {
    kind: "error",
    error: {
      error: "proxy_unreachable",
      message:
        "Die Anfrage an /api/engine konnte nicht gesendet werden. Läuft der Next.js-Server noch?",
      details: cause instanceof Error ? cause.message : String(cause),
    },
  }
}

async function readJson(
  response: Response
): Promise<{ ok: true; body: unknown } | { ok: false; error: ReviewError }> {
  const raw = await response.text()

  if (raw.length === 0) {
    return {
      ok: false,
      error: {
        error: "empty_response",
        message: `Leere Antwort (HTTP ${response.status}).`,
        status: response.status,
      },
    }
  }

  let body: unknown
  try {
    body = JSON.parse(raw)
  } catch {
    return {
      ok: false,
      error: {
        error: "unparsable_response",
        message: "Die Antwort ist kein gültiges JSON.",
        status: response.status,
        details: raw.slice(0, 4000),
      },
    }
  }

  if (!response.ok) {
    return { ok: false, error: toReviewError(response.status, body) }
  }

  return { ok: true, body }
}

/**
 * Upload the deliveries and get back the handle to poll.
 *
 * The files go straight into a `FormData` and are never held in component state: the browser keeps
 * no copy of a billing document beyond the request. The engine answers `202` before auditing
 * anything, so a fast response here says the batch was *accepted*, not that it is done.
 */
export async function uploadBatch(
  files: readonly File[]
): Promise<BatchUploadResult> {
  const form = new FormData()
  for (const file of files) {
    // The part name the engine's `list[UploadFile]` parameter is called. Repeated once per file.
    form.append("files", file, file.name)
  }

  let response: Response
  try {
    response = await fetch("/api/engine/padnext/batch", {
      method: "POST",
      body: form,
    })
  } catch (cause) {
    return unreachable(cause)
  }

  const parsed = await readJson(response)
  if (!parsed.ok) return { kind: "error", error: parsed.error }

  if (!isBatchAcceptedShape(parsed.body)) {
    return {
      kind: "error",
      error: {
        error: "unexpected_response_shape",
        message:
          "Die Engine hat den Stapel angenommen, aber keine batch_id zurückgegeben. " +
          "Möglicherweise laufen Engine und UI auf verschiedenen Contract-Versionen — " +
          "packages/contracts neu generieren.",
        status: response.status,
        details: parsed.body,
      },
    }
  }

  return { kind: "accepted", accepted: parsed.body }
}

/** One poll. Called on a timer by the workbench until the job reaches a terminal status. */
export async function fetchBatch(batchId: string): Promise<BatchJobResult> {
  let response: Response
  try {
    response = await fetch(
      `/api/engine/padnext/batch/${encodeURIComponent(batchId)}`,
      {
        cache: "no-store",
      }
    )
  } catch (cause) {
    return unreachable(cause)
  }

  const parsed = await readJson(response)
  if (!parsed.ok) return { kind: "error", error: parsed.error }

  if (!isBatchJobShape(parsed.body)) {
    return {
      kind: "error",
      error: {
        error: "unexpected_response_shape",
        message:
          "Die Antwort enthält keinen lesbaren Stapel-Status. Möglicherweise laufen Engine und " +
          "UI auf verschiedenen Contract-Versionen — packages/contracts neu generieren.",
        status: response.status,
        details: parsed.body,
      },
    }
  }

  return { kind: "job", job: parsed.body }
}
