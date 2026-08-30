import { CheckCircle2Icon, CircleIcon, TriangleAlertIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"

import { Disclosure } from "@/components/review/collapsible-section"
import { RawJson } from "@/components/review/raw-json"
import { timestamp } from "@/lib/review/format"
import type { AuditTrail } from "@/lib/review/types"

/** How a checked statement reads: confirmed, merely recorded, or a caveat the reader must see. */
type Tone = "ok" | "neutral" | "warn"

function ToneIcon({ tone }: { tone: Tone }) {
  if (tone === "ok") {
    return (
      <CheckCircle2Icon className="mt-0.5 size-4 shrink-0 text-emerald-700 dark:text-emerald-400" />
    )
  }
  if (tone === "warn") {
    return (
      <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-destructive" />
    )
  }
  return <CircleIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
}

function Check({
  tone,
  claim,
  evidence,
}: {
  tone: Tone
  claim: string
  evidence: string
}) {
  return (
    <li className="flex gap-2.5">
      <ToneIcon tone={tone} />
      <div className="min-w-0">
        <p className="text-sm">{claim}</p>
        <p className="font-mono text-xs break-all text-muted-foreground">
          {evidence}
        </p>
      </div>
    </li>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-2 border-b py-1.5 last:border-b-0">
      <dt className="w-56 shrink-0 text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 flex-1 font-mono text-xs break-all">
        {value || "—"}
      </dd>
    </div>
  )
}

/**
 * `rule_summary` is an open mapping in the contract, so its keys cannot be known here.
 *
 * The scalar entries are rendered as rows — that is what the engine puts there today and it is the
 * readable half of "which rules ran". Anything structured is left to the raw JSON below rather than
 * flattened into prose it does not mean.
 */
function scalarEntries(summary: Record<string, unknown>): [string, string][] {
  return Object.entries(summary)
    .filter(
      ([, value]) =>
        typeof value === "string" ||
        typeof value === "number" ||
        typeof value === "boolean"
    )
    .map(([key, value]) => [key, String(value)] as [string, string])
}

/**
 * The audit trail: what produced this result, what the run can and cannot claim, and the proof tree
 * per position.
 *
 * ## "Geprüft" is a claim, so it is made carefully
 *
 * Each line in the first section states one thing the run *recorded*, next to the field that records
 * it. The icon is derived from the value and never from the fact that a value exists: `rule_coverage`
 * is a tick only when the engine said `full`, `solver_status` only when the optimum was proven. A
 * green tick beside "the rules were applied" on a run with partial coverage would be the single most
 * dangerous pixel on this screen — it is the reading that turns "we checked the rules we have" into
 * "the invoice is compliant".
 *
 * `llm_saw_goae_catalog: false` earns a tick on its own: it means no language model was in a
 * position to invent a Ziffer, because it never saw the catalog. That is a structural property of
 * the pipeline, not a quality judgement about this run, and it is worth stating on the page a
 * physician signs.
 *
 * `per_code` covers charged *and* blocked Ziffern, which is why the blocked table can show a proof
 * for a position that never reached the invoice. `stage_timings_ms` is measured, so it is excluded
 * from the receipt hash and from every determinism comparison — it is diagnostics only, and it is
 * filed as such.
 */
export function AuditTrailPanel({ auditTrail }: { auditTrail: AuditTrail }) {
  const perCode = auditTrail.per_code ?? []
  const coverage = auditTrail.rule_coverage
  const solverStatus = auditTrail.solver_status
  const sawCatalog = auditTrail.llm_saw_goae_catalog === true
  // In manual mode the engine reports the mode as the model, and "manual · manual" reads as two
  // facts that happen to agree rather than as one fact printed twice.
  const model =
    auditTrail.extraction_model &&
    auditTrail.extraction_model !== auditTrail.extraction_mode
      ? auditTrail.extraction_model
      : null
  const summary = scalarEntries(auditTrail.rule_summary ?? {})

  return (
    <div className="space-y-8">
      <section>
        <h3 className="mb-3 text-sm font-medium">Was geprüft wurde</h3>
        <ul className="space-y-2.5">
          <Check
            tone={sawCatalog ? "warn" : "ok"}
            claim={
              sawCatalog
                ? "Das Extraktionsmodell hatte Zugriff auf den GOÄ-Katalog — eine Ziffer kann aus dem Modell stammen."
                : "Kein Sprachmodell hat den GOÄ-Katalog gesehen. Ziffern stammen ausschließlich aus der Regel-Engine."
            }
            evidence={`llm_saw_goae_catalog = ${sawCatalog ? "true" : "false"} · extraction_mode = ${auditTrail.extraction_mode || "—"}${model ? ` · ${model}` : ""}`}
          />
          <Check
            tone="neutral"
            claim="Der Katalog ist über seinen Hash festgelegt: dieselbe Eingabe ergibt bei gleichem Katalog dasselbe Ergebnis."
            evidence={`${auditTrail.catalog_version || "—"} · ${auditTrail.catalog_source || "—"} · ${auditTrail.catalog_sha256 || "—"}`}
          />
          <Check
            tone={coverage === "full" ? "ok" : "warn"}
            claim={
              coverage === "full"
                ? "Die Regelabdeckung ist vollständig."
                : "Die Regelabdeckung ist unvollständig — eine nicht beanstandete Position ist damit nicht geprüft und bestätigt."
            }
            evidence={`rule_coverage = ${coverage || "—"} · ${auditTrail.rules_engine || "—"} ${auditTrail.rules_engine_version || ""} · Regeln ${auditTrail.rules_version || "—"}`}
          />
          <Check
            tone={solverStatus === "OPTIMUM" ? "ok" : "warn"}
            claim={
              solverStatus === "OPTIMUM"
                ? "Der Optimierer hat die Auswahl unter den zulässigen Alternativen als optimal bewiesen."
                : "Der Optimierer hat kein bewiesenes Optimum geliefert. Jede harte Regel gilt weiterhin; die Auswahl unter gleich zulässigen Alternativen ist möglicherweise nicht die beste."
            }
            evidence={`solver_status = ${solverStatus || "—"} · ${auditTrail.optimizer || "—"} ${auditTrail.optimizer_version || ""}`}
          />
          <Check
            tone="neutral"
            claim="Die Logikprogramme sind über ihre Version festgelegt und gehen in den Receipt-Hash ein."
            evidence={`logic_version = ${auditTrail.logic_version || "—"} · ${timestamp(auditTrail.timestamp)}`}
          />
        </ul>
      </section>

      <section>
        <h3 className="mb-3 text-sm font-medium">
          Angewandte Regeln und Politik
        </h3>
        {summary.length > 0 ? (
          <dl className="mb-4">
            {summary.map(([key, value]) => (
              <Row key={key} label={key} value={value} />
            ))}
          </dl>
        ) : (
          <p className="mb-4 text-sm text-muted-foreground">
            Die Engine hat keine Regelzusammenfassung mitgeliefert.
          </p>
        )}
        <dl>
          <Row
            label="Policy (unverifizierte Regeln)"
            value={auditTrail.unverified_rule_policy ?? ""}
          />
          <Row
            label="Policy (Basisfaktor)"
            value={auditTrail.base_factor_policy ?? ""}
          />
          <Row
            label="Ø Extraktionskonfidenz"
            value={auditTrail.extraction_confidence_avg ?? ""}
          />
        </dl>
      </section>

      <section>
        <h3 className="mb-3 text-sm font-medium">
          Beweisbaum pro Position{" "}
          <span className="font-normal text-muted-foreground">
            ({perCode.length} {perCode.length === 1 ? "Position" : "Positionen"}
            , berechnet und gesperrt)
          </span>
        </h3>
        <div className="space-y-3">
          {perCode.map((entry) => (
            <div key={entry.ziffer} className="rounded-xl border p-3">
              <div className="mb-2 flex items-center gap-2">
                <span className="font-mono text-sm font-medium">
                  GOÄ {entry.ziffer}
                </span>
                <Badge variant="outline">
                  {(entry.steps ?? []).length}{" "}
                  {(entry.steps ?? []).length === 1 ? "Schritt" : "Schritte"}
                </Badge>
              </div>
              {/*
                A timeline rather than a bullet list: the steps are ordered — each one holds because
                the one above it did — and a rail is what says so without a sentence claiming it.
              */}
              <ol className="ml-1.5 space-y-2 border-l border-border pl-4">
                {(entry.steps ?? []).map((step, index) => (
                  <li
                    key={`${step.rule}-${index}`}
                    className="relative text-xs"
                  >
                    <span
                      aria-hidden
                      className="absolute top-1.5 -left-[1.3125rem] size-1.5 rounded-full bg-border"
                    />
                    <span className="font-mono font-medium">{step.rule}</span>
                    {step.detail ? (
                      <span className="font-mono text-muted-foreground">
                        {" "}
                        · {step.detail}
                      </span>
                    ) : null}
                    {step.rule_id ? (
                      <span className="font-mono text-muted-foreground">
                        {" "}
                        · {step.rule_id}
                      </span>
                    ) : null}
                    {step.legal_basis ? (
                      <span className="text-muted-foreground">
                        {" "}
                        · {step.legal_basis}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      </section>

      <section>
        {/*
          Measured, therefore excluded from the receipt hash — and therefore not part of the document
          a physician signs. This is the one disclosure that stays closed when the page is printed.
        */}
        <Disclosure label="Diagnostik und Rohdaten" printOpen={false}>
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Gemessene Laufzeiten. Sie gehen <strong>nicht</strong> in den
              Receipt-Hash ein und werden bei jedem Determinismus-Vergleich
              ausgeschlossen.
            </p>
            <RawJson
              value={auditTrail.stage_timings_ms ?? {}}
              label="stage_timings_ms (gemessen)"
            />
            <RawJson
              value={auditTrail.rule_summary ?? {}}
              label="rule_summary"
            />
          </div>
        </Disclosure>
      </section>
    </div>
  )
}
