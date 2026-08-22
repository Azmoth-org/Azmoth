/**
 * `POST /api/engine/padnext/batch` → `POST {ENGINE_BASE_URL}/api/v1/padnext/batch`
 *
 * A multipart body carrying many PADnext deliveries, forwarded part for part. Nothing is parsed
 * here beyond counting and sizing: the engine owns reading each container, and it refuses a
 * delivery flagged as production data — per file, marking that file FAILED and continuing with the
 * rest. See `docs/compliance/PRIVATE_DATA_WARNING.md`.
 *
 * The engine enforces the same three limits again on its own side. Checking them here as well is
 * not redundancy for its own sake: it means an over-large upload is refused before it is streamed
 * across the proxy, and it means the browser gets a German message instead of an engine payload.
 */

import { callEngineFormData, proxyResponse } from "@/lib/engine"

/** Mirrors `MAX_BATCH_FILES` / `MAX_BATCH_FILE_BYTES` / `MAX_BATCH_TOTAL_BYTES` in the engine. */
const MAX_FILES = 500
const MAX_FILE_BYTES = 8 * 1024 * 1024
const MAX_TOTAL_BYTES = 64 * 1024 * 1024

export async function POST(request: Request): Promise<Response> {
  let form: FormData
  try {
    form = await request.formData()
  } catch (cause) {
    return Response.json(
      {
        error: "unreadable_upload",
        message: "Der Upload konnte nicht als multipart/form-data gelesen werden.",
        details: cause instanceof Error ? cause.message : String(cause),
      },
      { status: 400 },
    )
  }

  const files = form.getAll("files").filter((part): part is File => part instanceof File)

  if (files.length === 0) {
    return Response.json(
      {
        error: "empty_batch",
        message:
          "Keine Dateien empfangen. Bitte mindestens eine PADnext-Datei auswählen — " +
          ".padx-Container oder *_padx.xml-Nutzdaten.",
      },
      { status: 400 },
    )
  }

  if (files.length > MAX_FILES) {
    return Response.json(
      {
        error: "too_many_files",
        message: `${files.length} Dateien; höchstens ${MAX_FILES} pro Stapel. Bitte aufteilen.`,
      },
      { status: 413 },
    )
  }

  let total = 0
  for (const file of files) {
    if (file.size > MAX_FILE_BYTES) {
      return Response.json(
        {
          error: "file_too_large",
          message: `${file.name} ist größer als ${MAX_FILE_BYTES / 1024 / 1024} MB.`,
        },
        { status: 413 },
      )
    }
    total += file.size
  }

  if (total > MAX_TOTAL_BYTES) {
    return Response.json(
      {
        error: "batch_too_large",
        message: `Der Stapel ist größer als ${MAX_TOTAL_BYTES / 1024 / 1024} MB. Bitte aufteilen.`,
      },
      { status: 413 },
    )
  }

  return proxyResponse(await callEngineFormData("/api/v1/padnext/batch", form))
}
