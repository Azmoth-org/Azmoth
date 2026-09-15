/**
 * `POST /api/engine/padnext/audit/pdf` → `POST {ENGINE_BASE_URL}/api/v1/padnext/audit.pdf`
 *
 * The printable twin of `/api/engine/padnext/audit`, and deliberately the same request: the
 * PADnext file as the body, forwarded byte for byte, with the same size ceiling refused here so a
 * large upload is not streamed across the proxy only to be turned away at the far end.
 *
 * **The file is sent a second time rather than the report being cached.** The audit stores nothing
 * — that is what keeps it outside tenancy — so there is no report on the server to render, and the
 * only way to produce the document is to run the audit again. It is deterministic, so the PDF
 * carries the same verdicts and the same `receipt_hash` as the JSON already on screen; the hash
 * printed on the document is what lets a reader confirm that the two are the same audit.
 *
 * A refusal comes back as the engine's own JSON body with its own status, so a delivery flagged as
 * production data produces the same `422` here as it does on the JSON path.
 *
 * **This route sends one thing the JSON path does not: the practice's name.** The report has a
 * "Praxis / Konto" line and the engine could only fill it from the tenant *id* header, so a
 * signed-in reader downloaded a Prüfbericht headed by a 32-character UUID. The name is resolved
 * from the session's active organisation here — the only tier that can, since the `organization`
 * table belongs to this half of the schema — and forwarded as `X-Organization-Name`. It is display
 * text: nothing is filtered, stored or authorised on it, and when it cannot be resolved the engine
 * prints what it always did.
 */

import {
  ORGANIZATION_NAME_HEADER,
  encodeHeaderValue,
  proxyEngineDownload,
} from "@/lib/engine"
import { activeOrganizationName } from "@/lib/organization-display"

/** The same ceiling `/api/engine/padnext/audit` enforces, and the engine's own reader after it. */
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024

export async function POST(request: Request): Promise<Response> {
  const bytes = await request.arrayBuffer()

  if (bytes.byteLength === 0) {
    return Response.json(
      {
        error: "empty_request_body",
        message:
          "Kein Inhalt empfangen. Bitte eine PADnext-Datei senden — einen .padx-Container oder " +
          "eine *_padx.xml-Nutzdatei.",
      },
      { status: 400 }
    )
  }

  if (bytes.byteLength > MAX_UPLOAD_BYTES) {
    return Response.json(
      {
        error: "upload_too_large",
        message: `Die Datei ist größer als ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.`,
      },
      { status: 413 }
    )
  }

  // The practice's name, for the "Praxis / Konto" line. Resolved here rather than in the engine
  // because the engine cannot: `organization` is Better Auth's table in this tier's half of the
  // schema, and `app/api/tenancy.py` is explicit that querying it from there would couple the
  // engine to a migrator it does not control. So this tier looks up the name of the organisation
  // the session is actually a member of and sends it as display text.
  //
  // `null` is not an error and is not sent: the engine falls back to its id-derived label, which
  // is exactly what it printed before this existed. A download must not fail because a name could
  // not be looked up.
  const organizationName = await activeOrganizationName()

  return proxyEngineDownload("/api/v1/padnext/audit.pdf", {
    method: "POST",
    upload: {
      bytes,
      filename: request.headers.get("x-padnext-filename") ?? undefined,
      contentType: request.headers.get("content-type") ?? undefined,
    },
    extraHeaders: organizationName
      ? { [ORGANIZATION_NAME_HEADER]: encodeHeaderValue(organizationName) }
      : undefined,
  })
}
