/**
 * Browser-side call to the PADnext audit proxy.
 *
 * Mirrors `lib/review/client.ts`: never throws, never returns a half-parsed body. The screen renders
 * either a report whose fields it can trust to exist, or a named error with the raw details attached.
 */

import { isAuditReportShape, toReviewError, type PadnextResult } from "@/lib/padnext/types"

export async function auditPadnextFile(file: File): Promise<PadnextResult> {
  let response: Response
  try {
    response = await fetch("/api/engine/padnext/audit", {
      method: "POST",
      headers: {
        // The engine sniffs the container by magic bytes, so this is a hint, not a contract.
        "Content-Type": file.name.endsWith(".xml") ? "application/xml" : "application/octet-stream",
        "x-padnext-filename": file.name,
      },
      body: file,
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

  const raw = await response.text()

  if (raw.length === 0) {
    return {
      kind: "error",
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
      kind: "error",
      error: {
        error: "unparsable_response",
        message: "Die Antwort ist kein gültiges JSON.",
        status: response.status,
        details: raw.slice(0, 4000),
      },
    }
  }

  if (!response.ok) {
    return { kind: "error", error: toReviewError(response.status, body) }
  }

  if (!isAuditReportShape(body)) {
    return {
      kind: "error",
      error: {
        error: "unexpected_response_shape",
        message:
          "Die Engine hat mit HTTP 200 geantwortet, aber der Body enthält nicht die drei " +
          "Bewertungsgruppen (confirmed_fine / confirmed_wrong / unconfirmed). Möglicherweise läuft " +
          "die Engine noch auf einer Contract-Version mit dem alten Feld at_risk_eur — " +
          "packages/contracts neu generieren.",
        status: response.status,
        details: body,
      },
    }
  }

  return { kind: "report", report: body }
}
