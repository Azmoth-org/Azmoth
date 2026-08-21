import { AlertTriangleIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"

/**
 * The three statements a reviewer must see on every load, not once in an onboarding flow.
 *
 * This is not decoration. The engine has no access control, no audit logging and no PHI handling,
 * and its output is a draft that a physician remains responsible for. See
 * `docs/compliance/PRIVATE_DATA_WARNING.md`.
 */
export function SyntheticDataBanner() {
  return (
    <Alert variant="destructive" className="border-destructive/40">
      <AlertTriangleIcon />
      <AlertTitle>Nur synthetische Demodaten — kein Echtbetrieb</AlertTitle>
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-4">
          <li>
            Es dürfen <strong>ausschließlich synthetische Testdaten</strong> verarbeitet werden. Keine
            Patientendaten, keine echten Rechnungen. Das System implementiert keine
            Zugriffskontrolle, keine Protokollierung und keinen § 203 StGB-Workflow.
          </li>
          <li>
            Das Ergebnis ist ein <strong>Abrechnungsvorschlag (Entwurf)</strong> und{" "}
            <strong>keine Rechnung</strong>.
          </li>
          <li>
            Die <strong>ärztliche Prüfung ist zwingend erforderlich</strong>. Die Regelabdeckung ist
            unvollständig; die Engine ersetzt keine fachliche Entscheidung.
          </li>
        </ul>
      </AlertDescription>
    </Alert>
  )
}
