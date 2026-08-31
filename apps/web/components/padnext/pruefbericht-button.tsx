"use client"

import { FileTextIcon, Loader2Icon } from "lucide-react"
import { useState } from "react"

import { Button } from "@workspace/ui/components/button"

/**
 * Download the Prüfbericht — the printable report — for one delivery or for a whole batch.
 *
 * ## Why this is a `POST` and a blob rather than an `<a href>`
 *
 * The engine renders the document on demand; there is no stored file to link to. And on the
 * single-delivery path the request carries the PADnext file itself, which a link cannot do at all.
 * So both variants go through `fetch`, and the object URL is revoked in a `finally` — a user who
 * clicks four times must not leave four copies of a billing document pinned in the tab's memory.
 *
 * ## Why the engine's filename is used and not one built here
 *
 * The `Content-Disposition` the engine sends is the name a Rechnungsprüfer will find the file
 * under, and the engine already sanitises it — a PADnext filename is client-supplied and reaches a
 * response header. Rebuilding it in the browser would be a second implementation of that
 * sanitisation, which is exactly how the two come to disagree.
 */

/** `attachment; filename="x.pdf"` → `x.pdf`. The engine restricts it to `[A-Za-z0-9._-]`. */
function filenameFrom(disposition: string | null, fallback: string): string {
  const match = disposition?.match(/filename="([A-Za-z0-9._-]+)"/)
  return match?.[1] ?? fallback
}

async function save(response: Response, fallback: string): Promise<void> {
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = filenameFrom(
      response.headers.get("content-disposition"),
      fallback
    )
    document.body.append(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** The engine answers a refusal as JSON with its own German message. Show that, not "failed". */
async function reasonFrom(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { message?: string }
    if (body.message) return body.message
  } catch {
    // A non-JSON refusal is possible in principle; fall through to the generic sentence.
  }
  return "Der Bericht konnte nicht erstellt werden. Bitte erneut versuchen."
}

function useDownload() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(request: () => Promise<Response>, fallback: string) {
    setPending(true)
    setError(null)
    try {
      const response = await request()
      if (!response.ok) {
        setError(await reasonFrom(response))
        return
      }
      await save(response, fallback)
    } catch {
      setError("Die Engine ist nicht erreichbar. Bitte erneut versuchen.")
    } finally {
      setPending(false)
    }
  }

  return { pending, error, run }
}

function DownloadButton({
  pending,
  error,
  onClick,
  disabled,
}: {
  pending: boolean
  error: string | null
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        variant="outline"
        size="sm"
        onClick={onClick}
        disabled={pending || disabled}
      >
        {pending ? (
          <>
            <Loader2Icon className="animate-spin" aria-hidden />
            Bericht wird erstellt…
          </>
        ) : (
          <>
            <FileTextIcon aria-hidden />
            Prüfbericht exportieren
          </>
        )}
      </Button>
      {error ? (
        <span className="text-xs text-destructive" role="status">
          {error}
        </span>
      ) : null}
    </div>
  )
}

/**
 * The Prüfbericht for one audited delivery.
 *
 * Takes the `File` the user picked rather than the report on screen, because the audit stores
 * nothing: there is no server-side report to render, so the document is produced by auditing the
 * delivery again. That is deterministic — the PDF carries the same verdicts and the same
 * `receipt_hash` as the report beside this button, and the hash is printed on the document so a
 * reader can check that for themselves.
 *
 * Holding the `File` is holding a handle to bytes the browser already has from the file input, not
 * a second copy in JavaScript memory. `AuditWorkbench` drops the handle when the next upload
 * starts, so it lives exactly as long as the report it belongs to is on screen.
 */
export function SinglePruefberichtButton({ file }: { file: File }) {
  const { pending, error, run } = useDownload()
  return (
    <DownloadButton
      pending={pending}
      error={error}
      onClick={() =>
        void run(
          () =>
            fetch("/api/engine/padnext/audit/pdf", {
              method: "POST",
              headers: {
                "Content-Type": "application/octet-stream",
                // Latin-1 is what a header may carry; the engine sanitises it again before it
                // reaches a `Content-Disposition`.
                "x-padnext-filename": file.name.replace(/[^\x20-\x7E]/g, "_"),
              },
              body: file,
            }),
          "pruefbericht.pdf"
        )
      }
    />
  )
}

/**
 * The aggregated Prüfbericht for a completed batch.
 *
 * `disabled` for anything but `COMPLETED`: the engine refuses with a `409` and this says so before
 * the click rather than after it. The reason is the one the CSV export gives — a running batch
 * would produce totals that are a snapshot of an unidentifiable moment.
 */
export function BatchPruefberichtButton({
  batchId,
  completed,
}: {
  batchId: string
  completed: boolean
}) {
  const { pending, error, run } = useDownload()
  return (
    <DownloadButton
      pending={pending}
      error={error}
      disabled={!completed}
      onClick={() =>
        void run(
          () =>
            fetch(
              `/api/engine/padnext/batch/${encodeURIComponent(batchId)}/pdf`,
              { method: "POST" }
            ),
          `${batchId}_pruefbericht.pdf`
        )
      }
    />
  )
}
