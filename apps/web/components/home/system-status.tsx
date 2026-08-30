import { AlertTriangleIcon, CheckCircle2Icon } from "lucide-react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Badge } from "@workspace/ui/components/badge"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

import { CopyableHash } from "@/components/common/copyable-hash"
import type {
  HealthResponse,
  RuleCoverage,
  SolverHealth,
} from "@workspace/contracts"

/**
 * What the engine currently is, on the screen a reader lands on first.
 *
 * The two figures here are the ones that decide how much any other screen's output is worth, and
 * both were previously invisible until you opened a proposal:
 *
 * * **Verified rules.** Most constraint rules were machine-extracted from the GOÄ's prose
 *   and enforce nothing until a human confirms them. That is the direct cause of the `unbestätigt`
 *   bucket in every audit, so a reader has to be able to see where the number stands before reading
 *   a report that depends on it.
 * * **Catalog version.** Every amount is recomputed from this exact snapshot, and it is part of
 *   every receipt hash. A screen that showed money without naming the catalog it came from would be
 *   showing an unattributable figure.
 *
 * Both are read live rather than baked in — a verified rule takes effect immediately, and a
 * hardcoded count would start lying the first time somebody used the rule queue.
 *
 * ## The two solver figures report a probe, not an inventory
 *
 * `health.solvers` carries what each engine answered when the endpoint handed it a one-line program
 * to solve, and the version beside it is what solved it. That distinction is the reason this card
 * can now explain itself: before, a Soufflé that was installed and broken rendered as a version
 * string next to "Engine bereit", and the first sign of trouble was a coding request failing. Now a
 * solver that did not solve says so on this card, with the engine's own one-line reason — which is
 * the difference between "something is wrong" and "the binary exits 127, its shared library is
 * missing".
 *
 * `solvers` is optional in the rendering rather than required, because this screen can be pointed
 * at an engine older than the field. An engine that does not send it falls back to exactly what
 * this card showed before, which is a version and no probe.
 */
export function SystemStatus({
  coverage,
  health,
}: {
  coverage: RuleCoverage | null
  health: HealthResponse | null
}) {
  // The engine being unreachable is the single most likely thing to be wrong with a fresh checkout,
  // so it is named, with the variable to fix, rather than rendered as zeroes.
  if (!coverage || !health) {
    return (
      <Alert variant="destructive">
        <AlertTriangleIcon />
        <AlertTitle>Engine nicht erreichbar</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>
            Der Systemstatus konnte nicht geladen werden. Die Engine muss unter{" "}
            <span className="font-mono text-xs">ENGINE_BASE_URL</span> laufen
            (Standard{" "}
            <span className="font-mono text-xs">http://localhost:8000</span>).
          </p>
          <p>
            Im Docker-Stack startet sie mit{" "}
            <span className="font-mono text-xs">
              docker compose -f infra/docker/docker-compose.yml up --build
            </span>
            .
          </p>
        </AlertDescription>
      </Alert>
    )
  }

  const verified = coverage.enforced_rule_count ?? 0
  const total = coverage.total_constraint_rule_count ?? 0
  // Guarded rather than tried: a total of zero means the rule tables did not load, and "0 %" is a
  // more honest rendering of that than a division error or a full bar.
  const share = total > 0 ? Math.min(100, (verified / total) * 100) : 0
  const engineReady =
    health.status === "ok" && health.souffle_available === true

  const solvers: Record<string, SolverHealth> = health.solvers ?? {}
  // Only the ones that actually failed, so the alert below is absent on a healthy engine rather
  // than an empty box. `unavailable` is included: a solver that is not installed is as fatal to a
  // coding request as one that is installed and broken, and the two need different fixes.
  const brokenSolvers = Object.entries(solvers).filter(
    ([, solver]) => solver.status !== "ok"
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Systemstatus
          {engineReady ? (
            <Badge variant="secondary" className="gap-1">
              <CheckCircle2Icon className="size-3" aria-hidden />
              Engine bereit
            </Badge>
          ) : (
            <Badge variant="destructive">Engine eingeschränkt</Badge>
          )}
          <Badge variant="outline" className="font-mono text-xs">
            {health.app_env}
          </Badge>
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-6">
        {brokenSolvers.length > 0 && (
          <Alert variant="destructive">
            <AlertTriangleIcon />
            <AlertTitle>
              {brokenSolvers.length === 1
                ? "Ein Solver antwortet nicht"
                : "Solver antworten nicht"}
            </AlertTitle>
            <AlertDescription className="space-y-1">
              {brokenSolvers.map(([name, solver]) => (
                <p key={name}>
                  <span className="font-mono">{name}</span>:{" "}
                  {solver.status === "unavailable"
                    ? "nicht installiert"
                    : "installiert, liefert aber kein Ergebnis"}
                  {/* The engine's own reason, verbatim. It names the exit code or the missing
                      binary, which is the whole difference between a ticket somebody can act on
                      and one that says the system is degraded. */}
                  {solver.detail ? ` — ${solver.detail}` : ""}
                </p>
              ))}
              <p>
                Kodierungsanfragen schlagen fehl, solange das so ist. Details
                unter{" "}
                <span className="font-mono text-xs">/api/v1/health</span>.
              </p>
            </AlertDescription>
          </Alert>
        )}

        <div className="space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-sm font-medium">
              <span className="tabular-nums">{verified}</span> von{" "}
              <span className="tabular-nums">{total}</span> Regeln verifiziert
            </span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {share.toFixed(1)} %
            </span>
          </div>

          {/* A plain div, not a progress component: this is one bar and it needs no library. */}
          <div
            role="progressbar"
            aria-valuenow={verified}
            aria-valuemin={0}
            aria-valuemax={total}
            aria-label="Verifizierte GOÄ-Regeln"
            className="h-2 w-full overflow-hidden rounded-full bg-muted"
          >
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${share}%` }}
            />
          </div>

          <p className="text-xs text-muted-foreground">
            Nicht verifizierte Regeln setzen nichts durch — sie warnen nur.
            Genau das erzeugt die Gruppe <strong>unbestätigt</strong> in jeder
            Rechnungsprüfung, und jede in der Regelprüfung freigegebene Regel
            verkleinert sie.
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-xs sm:grid-cols-4">
          <Figure
            label="Katalogversion"
            value={health.catalog_version || "—"}
            mono
          />
          <Figure
            label="Ziffern im Katalog"
            value={String(health.catalog_ziffern ?? 0)}
            mono
          />
          <Figure
            label="Regelabdeckung"
            value={health.rule_coverage || "—"}
            mono
          />
          <Figure
            label="nur beratend"
            value={String(coverage.advisory_rule_count ?? 0)}
            mono
          />
          <SolverFigure
            label="Soufflé"
            version={health.souffle_version}
            probe={solvers.souffle}
          />
          <SolverFigure
            label="Clingo"
            version={health.clingo_version}
            probe={solvers.clingo}
          />
          <Figure
            label="Regel-Policy"
            value={coverage.policy_for_unverified_rules || "—"}
            mono
          />
          <div className="min-w-0">
            <dt className="text-muted-foreground">Logic-Version</dt>
            <dd className="mt-0.5">
              <CopyableHash
                value={health.logic_version}
                length={12}
                label="Logic-Version"
              />
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}

/**
 * One solver: which version answered, and how long it took to answer.
 *
 * The probe time is shown because it is the number an operator can only ask about if somebody
 * recorded it — "Soufflé takes 400 ms today and took 40 ms last week" is a real signal about the
 * host, and it is invisible without this. It is a diagnostic rather than a benchmark: for Soufflé
 * it is dominated by process creation.
 *
 * `probe` is optional so this renders against an engine that predates the field, in which case it
 * degrades to exactly the version string this card showed before.
 */
function SolverFigure({
  label,
  version,
  probe,
}: {
  label: string
  version: string | undefined
  probe: SolverHealth | undefined
}) {
  const failed = probe !== undefined && probe.status !== "ok"
  const value = failed ? "fehlerhaft" : version || "fehlt"

  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd
        className={
          failed
            ? "mt-0.5 truncate font-mono text-destructive"
            : "mt-0.5 truncate font-mono"
        }
        title={probe?.detail || value}
      >
        {value}
        {probe && !failed ? (
          <span className="ml-1.5 text-muted-foreground tabular-nums">
            {Math.round(probe.probe_time_ms)} ms
          </span>
        ) : null}
      </dd>
    </div>
  )
}

function Figure({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd
        className={mono ? "mt-0.5 truncate font-mono" : "mt-0.5 truncate"}
        title={value}
      >
        {value}
      </dd>
    </div>
  )
}
