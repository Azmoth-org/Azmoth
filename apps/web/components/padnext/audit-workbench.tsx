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
import { ReportProvenance } from "@/components/padnext/report-provenance"
import { ErrorPanel } from "@/components/review/error-panel"
import { auditPadnextFile } from "@/lib/padnext/client"
import type { PadnextResult } from "@/lib/padnext/types"

/** What the engine's reader accepts: a `.padx` container, or a bare payload/order file. */
const ACCEPTED = ".padx,.xml,.auf"

/**
 * Upload a PADnext delivery and render the audit.
 *
 * The file never touches component state — it is read straight into the request body and dropped, so
 * the browser holds no copy of a billing document longer than the request takes.
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
  const [confirmed, setConfirmed] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function onPick(file: File | undefined) {
    if (!file) return
    setFilename(file.name)
    setPending(true)
    setResult(null)
    try {
      setResult(await auditPadnextFile(file))
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
