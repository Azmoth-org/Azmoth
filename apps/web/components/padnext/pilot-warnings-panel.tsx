import { InfoIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"

import type { PadnextAuditReport } from "@/lib/padnext/types"

/**
 * What the audit found out about *itself* — today, that this invoice is older than the catalog
 * edition it was priced against.
 *
 * ## Why it is not in `FindingsPanel`
 *
 * `findings` is the list of things wrong with the invoice. This is a thing missing from the
 * engine, and the two must not be counted together: a reviewer who reads "9 Befunde" and acts on
 * nine defects must not find that one of them was our own coverage gap. The engine keeps the same
 * separation — `pilot_warnings` is a top-level array and deliberately never merged into `findings`
 * or into `schema_warnings`, each of which already means something specific.
 *
 * ## Where it sits and how loud it is
 *
 * Above `BucketSummary`, because it changes how every number below it should be read, and a
 * caveat printed after the figures it qualifies is a caveat that arrives too late. Informational
 * rather than destructive for the reason `CatalogScopeNotice` gives: this is a limit of the
 * product, not a defect in the practice's billing, and rendering it in the same red as a
 * `confirmed_wrong` position would make a coverage gap look like an accusation.
 *
 * Renders nothing when the array is empty — which, note, includes deliveries where no position
 * carried a readable `<datum>`. That case is `pilot_scope_checked: false` on the report; the
 * screen does not distinguish it, because "we could not read a date" is a statement for the
 * findings list (where the reader already reports it) rather than a second banner here.
 */
export function PilotWarningsPanel({ report }: { report: PadnextAuditReport }) {
  const warnings = report.pilot_warnings ?? []

  if (warnings.length === 0) {
    return null
  }

  return (
    <Alert>
      <InfoIcon className="size-4 shrink-0" aria-hidden />
      <AlertTitle>Hinweis zum Prüfumfang</AlertTitle>
      <AlertDescription className="space-y-2">
        {warnings.map((warning) => (
          <p key={warning}>{warning}</p>
        ))}
        <p className="text-muted-foreground">
          Die Prüfung wurde vollständig durchgeführt. Dieser Hinweis betrifft
          nicht die Rechnung, sondern die Reichweite dieser Engine
          {report.catalog_version ? (
            <>
              {" "}
              — geprüft gegen den Katalogstand{" "}
              <span className="font-mono">{report.catalog_version}</span>
            </>
          ) : null}
          .
        </p>
      </AlertDescription>
    </Alert>
  )
}
