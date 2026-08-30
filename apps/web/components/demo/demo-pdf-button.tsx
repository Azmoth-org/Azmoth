"use client"

import { DownloadIcon, Loader2Icon } from "lucide-react"
import { useState } from "react"

import { Button } from "@workspace/ui/components/button"

/**
 * Download the demo Prüfbericht.
 *
 * A `POST` and a blob rather than an `<a href>`, because the engine renders the document on demand
 * and answers `POST /demo/report.pdf` — the same shape the batch report uses, and for the same
 * reason stated there: the endpoint renders rather than reads, even though it is idempotent.
 *
 * The object URL is revoked in a `finally`, so a visitor who clicks four times does not leave four
 * copies of the document pinned in the tab's memory.
 *
 * Distinct from `PrintButton` on the review screen, which calls `window.print()` and deliberately
 * has no second rendering path. Here there is no screen to print that would carry the provenance
 * block — the PDF *is* the artefact a prospect forwards to a colleague, and it has to say inside
 * itself that it describes synthetic data.
 */
export function DemoPdfButton() {
  const [pending, setPending] = useState(false)
  const [failed, setFailed] = useState(false)

  async function download() {
    setPending(true)
    setFailed(false)
    let url: string | null = null
    try {
      const response = await fetch("/api/demo/report.pdf", { method: "POST" })
      if (!response.ok) {
        setFailed(true)
        return
      }
      const blob = await response.blob()
      url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = "azmoth_demo_pruefbericht.pdf"
      document.body.append(anchor)
      anchor.click()
      anchor.remove()
    } catch {
      setFailed(true)
    } finally {
      if (url) URL.revokeObjectURL(url)
      setPending(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        variant="outline"
        onClick={() => void download()}
        disabled={pending}
      >
        {pending ? (
          <>
            <Loader2Icon className="animate-spin" aria-hidden />
            Bericht wird erstellt…
          </>
        ) : (
          <>
            <DownloadIcon aria-hidden />
            Prüfbericht als PDF
          </>
        )}
      </Button>
      {failed ? (
        <span className="text-xs text-destructive">
          Der Bericht konnte nicht erstellt werden. Bitte erneut versuchen.
        </span>
      ) : null}
    </div>
  )
}
