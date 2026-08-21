import { Badge } from "@workspace/ui/components/badge"

import { RawJson } from "@/components/review/raw-json"
import { timestamp } from "@/lib/review/format"
import type { AuditTrail } from "@/lib/review/types"

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-2 border-b py-1.5 last:border-b-0">
      <dt className="text-muted-foreground w-56 shrink-0 text-xs">{label}</dt>
      <dd className="min-w-0 flex-1 font-mono text-xs break-all">{value || "—"}</dd>
    </div>
  )
}

/**
 * The audit trail: what produced this result, and the proof tree per position.
 *
 * `per_code` covers charged *and* blocked Ziffern, which is why the blocked table can show a proof
 * for a position that never reached the invoice. `stage_timings_ms` is measured, so it is excluded
 * from the receipt hash and from every determinism comparison — it is shown here as diagnostics only.
 */
export function AuditTrailPanel({ auditTrail }: { auditTrail: AuditTrail }) {
  const perCode = auditTrail.per_code ?? []

  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-2 text-sm font-medium">Herkunft und Politik</h3>
        <dl>
          <Row label="Extraktionsmodus" value={auditTrail.extraction_mode} />
          <Row label="Extraktionsmodell" value={auditTrail.extraction_model ?? ""} />
          <Row
            label="LLM sah GOÄ-Katalog"
            value={auditTrail.llm_saw_goae_catalog === true ? "ja" : "nein"}
          />
          <Row label="Katalogversion" value={auditTrail.catalog_version ?? ""} />
          <Row label="Katalogquelle" value={auditTrail.catalog_source ?? ""} />
          <Row label="Katalog-SHA-256" value={auditTrail.catalog_sha256 ?? ""} />
          <Row label="Regelversion" value={auditTrail.rules_version ?? ""} />
          <Row label="Regelabdeckung" value={auditTrail.rule_coverage ?? ""} />
          <Row label="Regel-Engine" value={`${auditTrail.rules_engine ?? ""} ${auditTrail.rules_engine_version ?? ""}`.trim()} />
          <Row label="Optimierer" value={`${auditTrail.optimizer ?? ""} ${auditTrail.optimizer_version ?? ""}`.trim()} />
          <Row label="Logic-Version" value={auditTrail.logic_version ?? ""} />
          <Row label="Solver-Status" value={auditTrail.solver_status ?? ""} />
          <Row label="Policy (unverifiziert)" value={auditTrail.unverified_rule_policy ?? ""} />
          <Row label="Policy (Basisfaktor)" value={auditTrail.base_factor_policy ?? ""} />
          <Row label="Ø Extraktionskonfidenz" value={auditTrail.extraction_confidence_avg ?? ""} />
          <Row label="Zeitstempel" value={timestamp(auditTrail.timestamp)} />
        </dl>
      </section>

      <section>
        <h3 className="mb-2 text-sm font-medium">
          Beweisbaum pro Position{" "}
          <span className="text-muted-foreground font-normal">
            ({perCode.length} Positionen, berechnet und gesperrt)
          </span>
        </h3>
        <div className="space-y-3">
          {perCode.map((entry) => (
            <div key={entry.ziffer} className="rounded-xl border p-3">
              <div className="mb-2 flex items-center gap-2">
                <span className="font-mono text-sm font-medium">GOÄ {entry.ziffer}</span>
                <Badge variant="outline">{(entry.steps ?? []).length} Schritte</Badge>
              </div>
              <ul className="space-y-1">
                {(entry.steps ?? []).map((step, index) => (
                  <li key={`${step.rule}-${index}`} className="text-xs">
                    <span className="font-mono font-medium">{step.rule}</span>
                    {step.detail ? (
                      <span className="text-muted-foreground font-mono"> · {step.detail}</span>
                    ) : null}
                    {step.rule_id ? (
                      <span className="text-muted-foreground font-mono"> · {step.rule_id}</span>
                    ) : null}
                    {step.legal_basis ? (
                      <span className="text-muted-foreground"> · {step.legal_basis}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-medium">Diagnostik</h3>
        <RawJson value={auditTrail.stage_timings_ms ?? {}} label="stage_timings_ms (gemessen)" />
        <RawJson value={auditTrail.rule_summary ?? {}} label="rule_summary" />
      </section>
    </div>
  )
}
