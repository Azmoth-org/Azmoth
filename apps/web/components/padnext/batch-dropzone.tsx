"use client"

import { FileUpIcon, Loader2Icon, XIcon } from "lucide-react"
import { useCallback, useId, useRef, useState } from "react"

import { Button } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"

/** What the engine's reader accepts: a `.padx` container, or a bare payload/order file. */
const ACCEPTED = ".padx,.xml,.auf"

/** Same ceilings the proxy route and the engine enforce, shown before an upload is attempted. */
const MAX_FILES = 500
const MAX_TOTAL_BYTES = 64 * 1024 * 1024

/**
 * A drag-and-drop area for many PADnext deliveries.
 *
 * The files are held in component state, unlike the single-file screen, and it is worth being
 * explicit about why the difference is acceptable: a batch has to be reviewed and corrected before
 * it is sent — dropping the wrong folder in is the normal case — so the list has to exist between
 * the drop and the submit. Nothing is read here; the `File` handles are references to the user's
 * own disk, and only `uploadBatch` ever reads their bytes. The list is cleared on submit.
 */
export function BatchDropzone({
  onSubmit,
  pending,
}: {
  onSubmit: (files: File[]) => void
  pending: boolean
}) {
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const inputId = useId()

  const add = useCallback((incoming: FileList | null) => {
    if (!incoming) return
    setFiles((current) => {
      // Deduplicated by name and size, because dropping the same folder twice is a common slip and
      // a batch with a file in it twice would double that invoice's weight in the roll-up.
      const seen = new Set(current.map((file) => `${file.name}:${file.size}`))
      const added = Array.from(incoming).filter(
        (file) => !seen.has(`${file.name}:${file.size}`),
      )
      return [...current, ...added].slice(0, MAX_FILES)
    })
  }, [])

  const totalBytes = files.reduce((sum, file) => sum + file.size, 0)
  const tooLarge = totalBytes > MAX_TOTAL_BYTES
  const atFileLimit = files.length >= MAX_FILES

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div
          // A label, not a button: it wraps the file input, so the keyboard and the screen reader
          // get the browser's own picker semantics rather than a div pretending to be a control.
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            add(event.dataTransfer.files)
          }}
          className={[
            "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
            dragging ? "border-primary bg-primary/5" : "border-muted-foreground/25",
          ].join(" ")}
        >
          <FileUpIcon className="text-muted-foreground size-8" aria-hidden />
          <label htmlFor={inputId} className="cursor-pointer text-sm font-medium underline">
            Dateien auswählen
          </label>
          <input
            id={inputId}
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED}
            className="sr-only"
            onChange={(event) => {
              add(event.target.files)
              // Cleared so re-picking the same file fires `change` again.
              event.target.value = ""
            }}
          />
          <p className="text-muted-foreground text-xs">
            oder mehrere <span className="font-mono">.padx</span>- /{" "}
            <span className="font-mono">*_padx.xml</span>-Dateien hierher ziehen. Höchstens{" "}
            {MAX_FILES} Dateien, {MAX_TOTAL_BYTES / 1024 / 1024} MB gesamt. Nur synthetische
            Testdaten.
          </p>
        </div>

        {files.length > 0 ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm font-medium">
                {files.length} {files.length === 1 ? "Datei" : "Dateien"} ausgewählt
              </span>
              <span className="text-muted-foreground text-xs tabular-nums">
                {(totalBytes / 1024).toFixed(0)} kB
              </span>
            </div>

            <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
              {files.map((file) => (
                <li
                  key={`${file.name}:${file.size}:${file.lastModified}`}
                  className="flex items-center justify-between gap-2"
                >
                  <span className="truncate font-mono">{file.name}</span>
                  <button
                    type="button"
                    aria-label={`${file.name} entfernen`}
                    className="text-muted-foreground hover:text-foreground shrink-0"
                    onClick={() => setFiles((current) => current.filter((f) => f !== file))}
                  >
                    <XIcon className="size-3.5" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>

            {tooLarge ? (
              <p className="text-destructive text-xs">
                Der Stapel ist größer als {MAX_TOTAL_BYTES / 1024 / 1024} MB. Bitte aufteilen.
              </p>
            ) : null}
            {atFileLimit ? (
              <p className="text-muted-foreground text-xs">
                Das Limit von {MAX_FILES} Dateien ist erreicht; weitere wurden nicht übernommen.
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            onClick={() => {
              onSubmit(files)
              setFiles([])
            }}
            disabled={pending || files.length === 0 || tooLarge}
          >
            {pending ? (
              <>
                <Loader2Icon className="animate-spin" aria-hidden />
                Stapel wird übertragen…
              </>
            ) : (
              <>
                <FileUpIcon aria-hidden />
                {files.length > 0 ? `${files.length} Dateien prüfen` : "Stapel prüfen"}
              </>
            )}
          </Button>
          {files.length > 0 && !pending ? (
            <Button variant="ghost" onClick={() => setFiles([])}>
              Auswahl leeren
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}
