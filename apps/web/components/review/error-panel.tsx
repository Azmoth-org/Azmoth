import { AlertTriangleIcon, RotateCwIcon } from "lucide-react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"

import { RawJson } from "@/components/review/raw-json"
import type { ReviewError } from "@/lib/review/types"

/** Human-readable guidance per failure the screen can hit. Anything unlisted falls back to none. */
const HINTS: Record<string, string> = {
  engine_unreachable:
    "Engine starten: cd apps/engine && .venv/bin/uvicorn app.main:app --port 8000 — oder ENGINE_BASE_URL prüfen.",
  engine_unreachable_timeout:
    "Die Engine läuft, antwortet aber nicht. Prüfen, ob der Prozess der Regel-Engine hängt (GET /api/v1/health).",
  proxy_unreachable:
    "Der Next.js-Server ist nicht erreichbar. pnpm dev neu starten.",
  solver_timeout:
    "Der Optimierer hat innerhalb von SOLVER_TIMEOUT_SECONDS kein Modell gefunden. Es wird bewusst KEIN Entwurf ausgegeben: ein leeres Ergebnis wäre nicht von „nichts ist berechnungsfähig“ zu unterscheiden.",
  rules_engine_failed:
    "Die deterministische Regel-Engine ist ausgefallen. GET /api/v1/health zeigt unter „Regel-Engine“, ob sie auf diesem Host verfügbar ist.",
  validation_failed:
    "Die unabhängige Validierung hat dem Solver widersprochen. Das ist ein Defekt in der Engine, nicht in der Eingabe — es wird absichtlich kein Entwurf zurückgegeben.",
  validation_error:
    "Die Eingabe entspricht nicht dem Extraktionsschema. Das betroffene Feld steht in den Details.",
  illegal_transition:
    "Dieser Statuswechsel ist nicht erlaubt. Ein abgelehnter oder exportierter Vorschlag wird nicht erneut entschieden — und ein Export ist nur einmal möglich.",
  // Was: "Vorschläge liegen nur im Speicher der Engine und überleben keinen Neustart." That was the
  // right explanation while the store was in-memory and is now simply false — and it pointed the
  // reviewer at the wrong fix, since re-running the case does not help with a mistyped id.
  proposal_not_found:
    "Unter dieser ID ist kein Vorschlag gespeichert. Vorschläge werden dauerhaft gespeichert — ID prüfen, oder den Fall neu ausführen.",
  // The two below are refused before a request is sent: the id in the link cannot be one this
  // engine issued. Worth separating from `*_not_found`, because "the link is damaged" and "the
  // record is gone" send a reader to look in two different places.
  malformed_proposal_id:
    "Die ID in der Adresszeile hat nicht die Form prop_<hex>. Vermutlich ist der Link unvollständig kopiert — der Vorschlag lässt sich über „Alle Prüfungen“ suchen.",
  malformed_batch_id:
    "Die ID in der Adresszeile hat nicht die Form batch_<hex>. Vermutlich ist der Link unvollständig kopiert — der Stapel lässt sich über die Stapel-Historie suchen.",
  unexpected_response_shape:
    "Engine und UI verwenden möglicherweise verschiedene Contract-Versionen. In apps/engine: python scripts/export_openapi.py, dann pnpm generate:contracts.",
  batch_not_completed:
    "Nur ein abgeschlossener Stapel kann exportiert werden. Eine Zwischensumme wäre ein Stand, den später niemand mehr identifizieren kann.",
  batch_not_found:
    "Unter dieser ID ist kein Stapel gespeichert. ID prüfen, oder die Dateien neu hochladen.",
  unreadable_request_body:
    "Der Export benötigt einen Namen im Feld exported_by.",
  empty_response:
    "Die Engine hat einen leeren Body geliefert. Engine-Logs prüfen.",
  unparsable_response:
    "Die Antwort war kein JSON. Steht ein Proxy zwischen UI und Engine?",
}

/**
 * One failure, in the same shape everywhere the app can fail.
 *
 * `onRetry` is optional and should only be passed for a failure that can plausibly succeed on a
 * second attempt — see `isRetryable` in `lib/deep-link.ts`. A retry button on a 404 is a lie: it
 * asks the identical question and gets the identical answer, and the reader spends a click finding
 * that out. `pending` disables it while the retry is in flight, so a slow engine does not collect a
 * queue of clicks.
 */
export function ErrorPanel({
  error,
  onRetry,
  pending = false,
}: {
  error: ReviewError
  onRetry?: () => void
  pending?: boolean
}) {
  const hint = HINTS[error.error]

  return (
    <Alert variant="destructive">
      <AlertTriangleIcon />
      <AlertTitle className="flex flex-wrap items-center gap-2">
        <span>{error.message}</span>
        <Badge variant="destructive" className="font-mono">
          {error.error}
        </Badge>
        {error.status ? (
          <Badge variant="outline">HTTP {error.status}</Badge>
        ) : null}
      </AlertTitle>
      <AlertDescription className="space-y-3">
        {hint ? <p className="text-foreground/80">{hint}</p> : null}
        {onRetry ? (
          <Button
            variant="outline"
            size="sm"
            onClick={onRetry}
            disabled={pending}
          >
            <RotateCwIcon
              className={pending ? "animate-spin" : undefined}
              aria-hidden
            />
            {pending ? "Wird erneut geladen…" : "Erneut versuchen"}
          </Button>
        ) : null}
        {error.details === undefined || error.details === null ? null : (
          <RawJson value={error.details} label="Details (unverändert)" />
        )}
      </AlertDescription>
    </Alert>
  )
}
