/**
 * `POST /api/engine/padnext/audit` → `POST {ENGINE_BASE_URL}/api/v1/padnext/audit`
 *
 * The request body is the PADnext file itself, forwarded byte for byte. Nothing is parsed here: the
 * engine owns reading the container, and it refuses a delivery flagged as production data with a
 * `422` that this route passes straight through — see `docs/compliance/PRIVATE_DATA_WARNING.md`.
 */

import { callEngineBytes, proxyResponse } from "@/lib/engine"

/** Same ceiling the engine's own reader enforces. Rejected here so a large upload is not streamed
 * across the proxy only to be refused at the far end. */
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024

export async function POST(request: Request): Promise<Response> {
  const body = await request.arrayBuffer()

  if (body.byteLength === 0) {
    return Response.json(
      {
        error: "empty_request_body",
        message:
          "Kein Inhalt empfangen. Bitte eine PADnext-Datei senden — einen .padx-Container oder " +
          "eine *_padx.xml-Nutzdatei.",
      },
      { status: 400 },
    )
  }

  if (body.byteLength > MAX_UPLOAD_BYTES) {
    return Response.json(
      {
        error: "upload_too_large",
        message: `Die Datei ist größer als ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.`,
      },
      { status: 413 },
    )
  }

  return proxyResponse(
    await callEngineBytes("/api/v1/padnext/audit", {
      body,
      filename: request.headers.get("x-padnext-filename") ?? undefined,
      contentType: request.headers.get("content-type") ?? undefined,
    }),
  )
}
