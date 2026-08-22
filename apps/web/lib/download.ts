/**
 * Saving a file the engine produced, from the browser.
 *
 * Both exports are `POST`s — the proposal one carries `exported_by`, and neither is a thing a
 * plain `<a href>` can trigger — so the response has to be fetched and handed to the browser as a
 * blob rather than navigated to. That is the whole reason this file exists.
 *
 * Like every other client helper here it never throws: a caller gets either `{ kind: "saved" }` or
 * a named error it can put in an `ErrorPanel`. A failed export must render as the engine's own
 * reason — "this proposal is not approved", with the status — and not as a silent no-op, which is
 * exactly what a broken download looks like to a user.
 */

import { toReviewError, type ReviewError } from "@/lib/review/types"

export type DownloadResult =
  | { kind: "saved"; filename: string }
  | { kind: "error"; error: ReviewError }

/**
 * The filename the engine chose, out of `Content-Disposition`.
 *
 * Parsed rather than reconstructed on this side: the engine names the file, and a client that
 * guessed would eventually disagree with it. Only the simple quoted `filename="…"` form is handled,
 * because that is the only form these two endpoints emit — anything else falls back rather than
 * pretending to implement RFC 6266.
 */
export function filenameFrom(header: string | null, fallback: string): string {
  if (!header) return fallback
  const match = /filename="([^"]+)"/.exec(header)
  return match?.[1] ?? fallback
}

/**
 * Hand a blob to the browser under a given name.
 *
 * The object URL is revoked on the next tick rather than immediately: Safari has historically
 * needed the URL to still resolve when the synthetic click is processed, and a leaked URL for one
 * frame is cheaper than a download that silently does nothing on one browser.
 */
function save(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.rel = "noopener"
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

/**
 * `POST` to a proxy route and save whatever comes back.
 *
 * The success and failure bodies have different types — a file on the way out, JSON on refusal —
 * so the status decides which it is before anything is read. A `409` body is parsed for the
 * engine's structured detail; a body that is not JSON at all still produces a named error rather
 * than a crash, because a proxy in front of this could return an HTML error page.
 */
export async function downloadPost(
  path: string,
  { body, fallbackFilename }: { body?: unknown; fallbackFilename: string },
): Promise<DownloadResult> {
  let response: Response
  try {
    response = await fetch(path, {
      method: "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    })
  } catch (cause) {
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

  if (!response.ok) {
    const raw = await response.text()
    let parsed: unknown = raw
    try {
      parsed = JSON.parse(raw)
    } catch {
      // Left as the raw text; `toReviewError` renders it in the details block.
    }
    return { kind: "error", error: toReviewError(response.status, parsed) }
  }

  const blob = await response.blob()

  if (blob.size === 0) {
    // A 200 with nothing in it would save an empty file the user would only discover later.
    return {
      kind: "error",
      error: {
        error: "empty_response",
        message: `Die Engine hat mit HTTP ${response.status} und leerem Body geantwortet.`,
        status: response.status,
      },
    }
  }

  const filename = filenameFrom(response.headers.get("content-disposition"), fallbackFilename)
  save(blob, filename)
  return { kind: "saved", filename }
}

/** `POST /api/engine/proposals/{id}/export` — the approved proposal, as JSON. */
export function downloadProposalExport(
  proposalId: string,
  payload: { exported_by: string; note: string },
): Promise<DownloadResult> {
  return downloadPost(`/api/engine/proposals/${encodeURIComponent(proposalId)}/export`, {
    body: payload,
    fallbackFilename: `proposal_${proposalId}.json`,
  })
}

/** `POST /api/engine/padnext/batch/{id}/export` — the completed batch, as a ZIP of CSVs. */
export function downloadBatchExport(batchId: string): Promise<DownloadResult> {
  return downloadPost(`/api/engine/padnext/batch/${encodeURIComponent(batchId)}/export`, {
    fallbackFilename: `batch_${batchId}_export.zip`,
  })
}
