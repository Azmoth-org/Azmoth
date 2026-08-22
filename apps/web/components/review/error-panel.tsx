import { AlertTriangleIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Badge } from "@workspace/ui/components/badge"

import { RawJson } from "@/components/review/raw-json"
import type { ReviewError } from "@/lib/review/types"

/** Human-readable guidance per failure the screen can hit. Anything unlisted falls back to none. */
const HINTS: Record<string, string> = {
  engine_unreachable:
    "Engine starten: cd apps/engine && .venv/bin/uvicorn app.main:app --port 8000 — oder ENGINE_BASE_URL prüfen.",
  engine_unreachable_timeout:
    "Die Engine läuft, antwortet aber nicht. Prüfen, ob der Soufflé-Prozess hängt (GET /api/v1/health).",
  proxy_unreachable: "Der Next.js-Server ist nicht erreichbar. pnpm dev neu starten.",
  solver_timeout:
    "Der Optimierer hat innerhalb von SOLVER_TIMEOUT_SECONDS kein Modell gefunden. Es wird bewusst KEIN Entwurf ausgegeben: ein leeres Ergebnis wäre nicht von „nichts ist berechnungsfähig“ zu unterscheiden.",
  rules_engine_failed:
    "Die Regel-Engine (Soufflé) ist ausgefallen. Ist das souffle-Binary installiert? GET /api/v1/health zeigt souffle_available.",
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
  unexpected_response_shape:
    "Engine und UI verwenden möglicherweise verschiedene Contract-Versionen. In apps/engine: python scripts/export_openapi.py, dann pnpm generate:contracts.",
  batch_not_completed:
    "Nur ein abgeschlossener Stapel kann exportiert werden. Eine Zwischensumme wäre ein Stand, den später niemand mehr identifizieren kann.",
  batch_not_found:
    "Unter dieser ID ist kein Stapel gespeichert. ID prüfen, oder die Dateien neu hochladen.",
  unreadable_request_body: "Der Export benötigt einen Namen im Feld exported_by.",
  empty_response: "Die Engine hat einen leeren Body geliefert. Engine-Logs prüfen.",
  unparsable_response: "Die Antwort war kein JSON. Steht ein Proxy zwischen UI und Engine?",
}

export function ErrorPanel({ error }: { error: ReviewError }) {
  const hint = HINTS[error.error]

  return (
    <Alert variant="destructive">
      <AlertTriangleIcon />
      <AlertTitle className="flex flex-wrap items-center gap-2">
        <span>{error.message}</span>
        <Badge variant="destructive" className="font-mono">
          {error.error}
        </Badge>
        {error.status ? <Badge variant="outline">HTTP {error.status}</Badge> : null}
      </AlertTitle>
      <AlertDescription className="space-y-3">
        {hint ? <p className="text-foreground/80">{hint}</p> : null}
        {error.details === undefined || error.details === null ? null : (
          <RawJson value={error.details} label="Details (unverändert)" />
        )}
      </AlertDescription>
    </Alert>
  )
}
