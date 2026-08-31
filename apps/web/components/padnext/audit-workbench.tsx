"use client"

import { FileUpIcon, Loader2Icon } from "lucide-react"
import { useRef, useState } from "react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"

import { AnonymisationGate } from "@/components/padnext/anonymisation-gate"
import { BucketSummary } from "@/components/padnext/bucket-summary"
import { FindingsPanel } from "@/components/padnext/findings-panel"
import { PositionsTable } from "@/components/padnext/positions-table"
import { SinglePruefberichtButton } from "@/components/padnext/pruefbericht-button"
import { ReportProvenance } from "@/components/padnext/report-provenance"
import { ErrorPanel } from "@/components/review/error-panel"
import { auditPadnextFile } from "@/lib/padnext/client"
import type { PadnextResult } from "@/lib/padnext/types"

/** What the engine's reader accepts: a `.padx` container, or a bare payload/order file. */
const ACCEPTED = ".padx,.xml,.auf"

/**
 * Upload a PADnext delivery and render the audit.
 *
 * The file's *bytes* never touch component state — they are read straight into the request body.
 * What is kept, for exactly as long as a report is on screen, is the `File` handle itself, and only
 * so `SinglePruefberichtButton` can produce the printable Prüfbericht from the same delivery. A
 * `File` is a reference to bytes the browser already holds on behalf of the file input, not a
 * second copy in JavaScript memory, and the next upload replaces it — so the window in which this
 * page can name a billing document is the window in which it is displaying one.
 *
 * The alternative was to have the PDF button re-open the file picker, which asks a user to find the
 * same file twice to get two views of one audit. The one it was weighed against — caching the
 * rendered report on the server — is the option that would actually change what this endpoint is:
 * the single audit stores nothing, and that is what keeps it outside tenancy.
 *
 * ## The gate in front of the picker
 *
 * The file input cannot be opened until `AnonymisationGate` has been confirmed, and the confirmation
 * is cleared again after every upload. That is a deliberate act placed between "I have a file" and
 * "the picker is open", for the failure that actually happens in a pilot: not somebody defeating a
 * control, but somebody exporting from their PVS, forgetting the anonymisation step, and uploading
 * out of habit. See that component for why it resets per file rather than per session.
 *
 * **It is not what enforces the rule.** The engine refuses a delivery flagged `echtdaten="true"`
 * with `REAL_DATA_REFUSED` before it reads a position, and that refusal is not reachable from this
 * browser. If both were somehow bypassed the engine would still say no; if this checkbox were
 * removed the engine would still say no. What the checkbox adds is the moment of deliberation and
 * a written record of whose obligation the pseudonymisation is.
 *
 * A refusal arrives here as a normal error panel carrying the engine's own German message, which
 * names the anonymisation script — so the reader is told what to do rather than only what failed.
 */
export function AuditWorkbench() {
  const [result, setResult] = useState<PadnextResult | null>(null)
  const [pending, setPending] = useState(false)
  const [filename, setFilename] = useState<string | null>(null)
  // The delivery the report on screen describes, kept so it can be rendered as a PDF. Cleared
  // whenever the report it belongs to is — see the note above.
  const [audited, setAudited] = useState<File | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function onPick(file: File | undefined) {
    if (!file) return
    setFilename(file.name)
    setPending(true)
    setResult(null)
    setAudited(null)
    try {
      const outcome = await auditPadnextFile(file)
      setResult(outcome)
      // Only alongside a report. A refusal has no document to export, and holding the file after
      // one would keep a delivery around for a screen that is showing an error.
      setAudited(outcome.kind === "report" ? file : null)
    } finally {
      setPending(false)
      // Per file, not per session — see `AnonymisationGate`. The next upload is a new statement.
      setConfirmed(false)
      // Without this, picking the same file twice in a row fires no `change` event and the second
      // attempt looks like a dead button.
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  return (
    <div className="space-y-6">
      <AnonymisationGate checked={confirmed} onCheckedChange={setConfirmed} />

      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 pt-6">
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            onChange={(event) => void onPick(event.target.files?.[0])}
          />
          <Button
            onClick={() => inputRef.current?.click()}
            disabled={pending || !confirmed}
          >
            {pending ? (
              <>
                <Loader2Icon className="animate-spin" aria-hidden />
                Prüfung läuft…
              </>
            ) : (
              <>
                <FileUpIcon aria-hidden />
                PADnext-Datei prüfen
              </>
            )}
          </Button>
          <div className="min-w-0 text-xs text-muted-foreground">
            {!confirmed && !pending ? (
              <span>
                Bitte bestätigen Sie zuerst die Anonymisierung — erst dann lässt
                sich eine Datei auswählen.
              </span>
            ) : filename ? (
              <span className="font-mono break-all">{filename}</span>
            ) : (
              <span>
                <span className="font-mono">.padx</span>-Container oder{" "}
                <span className="font-mono">*_padx.xml</span>-Nutzdaten. Nur
                pseudonymisierte Testdaten.
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {result?.kind === "error" ? <ErrorPanel error={result.error} /> : null}

      {result?.kind === "report" ? (
        <>
          {audited ? (
            <div className="flex justify-end print:hidden">
              <SinglePruefberichtButton file={audited} />
            </div>
          ) : null}
          <BucketSummary report={result.report} />
          <ReportProvenance report={result.report} />
          <PositionsTable report={result.report} />
          <FindingsPanel report={result.report} />
        </>
      ) : null}

      {result === null && !pending ? (
        <Alert>
          <AlertTitle>Noch keine Prüfung</AlertTitle>
          <AlertDescription>
            Eine PADnext-Lieferung enthält bereits kodierte Positionen. Diese
            Prüfung rechnet sie gegen den eigenen Katalog nach und trennt das
            Ergebnis in drei Gruppen: nachweislich falsch, bestätigt korrekt,
            und unbestätigt. Die dritte Gruppe ist kein Befund gegen die Praxis,
            sondern die Grenze unserer Regelabdeckung.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
