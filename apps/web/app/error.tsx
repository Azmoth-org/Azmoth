"use client"

import { AlertOctagonIcon } from "lucide-react"
import * as React from "react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"

/**
 * The outer boundary. Without it an unhandled render error showed the Next.js default error page —
 * an English stack trace on a German compliance tool, with no way back.
 *
 * It is deliberately **not** where engine failures land. Those are values, not exceptions:
 * `lib/engine.ts` resolves every transport failure into a described error and each screen renders it
 * as a panel with the engine's own reason. So anything arriving here is a genuine defect in this
 * app, and the copy says so rather than blaming the network.
 *
 * `digest` is included because it is the only handle that ties what the reader saw to the line in
 * the server log — the message itself is redacted in production builds.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  React.useEffect(() => {
    // Server-side render errors are already logged by Next; a client-side one is not, and a defect
    // nobody can see is one nobody fixes.
    console.error("Unbehandelter Fehler in der Oberfläche:", error)
  }, [error])

  return (
    <Alert variant="destructive">
      <AlertOctagonIcon />
      <AlertTitle>Diese Ansicht konnte nicht dargestellt werden</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>
          Das ist ein Fehler in der Oberfläche, nicht ein Befund zu einer Rechnung. Es wurde nichts
          freigegeben, abgelehnt oder exportiert — Statuswechsel finden ausschließlich in der Engine
          statt und werden dort protokolliert.
        </p>
        {error.digest ? (
          <p className="text-xs">
            Kennung für das Server-Log: <span className="font-mono">{error.digest}</span>
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={reset}>
            Erneut versuchen
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  )
}
