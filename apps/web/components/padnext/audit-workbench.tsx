"use client"

import { FileUpIcon, Loader2Icon } from "lucide-react"
import { useRef, useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"

import { CopyableHash } from "@/components/common/copyable-hash"
import { BucketSummary } from "@/components/padnext/bucket-summary"
import { FindingsPanel } from "@/components/padnext/findings-panel"
import { PositionsTable } from "@/components/padnext/positions-table"
import { ErrorPanel } from "@/components/review/error-panel"
import { auditPadnextFile } from "@/lib/padnext/client"
import { eur } from "@/lib/padnext/format"
import type { PadnextResult } from "@/lib/padnext/types"

/** What the engine's reader accepts: a `.padx` container, or a bare payload/order file. */
const ACCEPTED = ".padx,.xml,.auf"

function Provenance({ result }: { result: Extract<PadnextResult, { kind: "report" }> }) {
  const { report } = result
  return (
    <Card>
      <CardContent className="grid grid-cols-2 gap-x-6 gap-y-2 pt-6 text-xs sm:grid-cols-4">
        <div>
          <div className="text-muted-foreground">Datei</div>
          <div className="font-mono break-all">{report.source_name || "—"}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Nachrichtentyp</div>
          <div className="font-mono">{report.nachrichtentyp || "—"}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Setting (§ 6a)</div>
          <div className="font-mono">{report.setting}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Katalog</div>
          <div className="font-mono break-all">{report.catalog_version || "—"}</div>
        </div>
        <div>
          <div className="text-muted-foreground">nachgerechnet</div>
          <div className="font-mono tabular-nums">{eur(report.recomputed_total_eur)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Rechendifferenz</div>
          <div className="font-mono tabular-nums">{eur(report.arithmetic_delta_eur)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">nicht nachrechenbar</div>
          <div className="font-mono tabular-nums">{eur(report.unpriceable_claimed_eur)}</div>
        </div>
        <div className="min-w-0">
          <div className="text-muted-foreground">Receipt</div>
          <CopyableHash value={report.receipt_hash} label="Receipt-Hash" />
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Upload a PADnext delivery and render the audit.
 *
 * The file never touches component state — it is read straight into the request body and dropped, so
 * the browser holds no copy of a billing document longer than the request takes. The engine refuses
 * a delivery flagged as production data with a `422`, which arrives here as a normal error panel.
 */
export function AuditWorkbench() {
  const [result, setResult] = useState<PadnextResult | null>(null)
  const [pending, setPending] = useState(false)
  const [filename, setFilename] = useState<string | null>(null)
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
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 pt-6">
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            onChange={(event) => void onPick(event.target.files?.[0])}
          />
          <Button onClick={() => inputRef.current?.click()} disabled={pending}>
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
          <div className="text-muted-foreground min-w-0 text-xs">
            {filename ? (
              <span className="font-mono break-all">{filename}</span>
            ) : (
              <span>
                <span className="font-mono">.padx</span>-Container oder{" "}
                <span className="font-mono">*_padx.xml</span>-Nutzdaten. Nur synthetische Testdaten.
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {result?.kind === "error" ? <ErrorPanel error={result.error} /> : null}

      {result?.kind === "report" ? (
        <>
          <BucketSummary report={result.report} />
          <Provenance result={result} />
          <PositionsTable report={result.report} />
          <FindingsPanel report={result.report} />
        </>
      ) : null}

      {result === null && !pending ? (
        <Alert>
          <AlertTitle>Noch keine Prüfung</AlertTitle>
          <AlertDescription>
            Eine PADnext-Lieferung enthält bereits kodierte Positionen. Diese Prüfung rechnet sie
            gegen den eigenen Katalog nach und trennt das Ergebnis in drei Gruppen: nachweislich
            falsch, bestätigt korrekt, und unbestätigt. Die dritte Gruppe ist kein Befund gegen die
            Praxis, sondern die Grenze unserer Regelabdeckung.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
