import type { Metadata } from "next"
import Link from "next/link"

import { ApiKeyManager } from "@/components/settings/api-key-manager"

export const metadata: Metadata = {
  title: "API-Schlüssel",
  description:
    "API-Schlüssel für die Anbindung eines PVS oder Rechnungszentrums erstellen, einsehen und widerrufen — und den Verbrauch der laufenden Abrechnungsperiode ansehen.",
}

/**
 * `/settings/api-keys` — the self-service credential screen.
 *
 * A server component shell, like every other screen here: the explanation of what a key *is* and
 * what it can reach has to render even if the client bundle fails, because it is the part somebody
 * has to have read before they create one. Only the table and the dialogs below are interactive.
 *
 * Access is decided by the `(app)` layout, which resolves the session against the database on every
 * render — this file adds no check of its own, deliberately, because a per-page check is one
 * somebody forgets on the next page. The organisation a key is minted for is the session's active
 * one and comes from the proxy, so there is no id in this route that could be edited to mint a key
 * into another practice.
 *
 * There is no `SyntheticDataBanner` here and its absence is deliberate: this screen holds no
 * invoice and no patient data. It holds credentials, which is a different kind of sensitive and is
 * warned about where it matters — in the dialog that shows one.
 */
export default function ApiKeysPage() {
  return (
    <>
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">API-Schlüssel</h1>
        <p className="text-sm text-muted-foreground">
          Mit einem API-Schlüssel bindet ein Praxisverwaltungssystem oder ein
          Rechnungszentrum die Prüfung direkt in die eigene Software ein —{" "}
          <span className="font-mono">POST /api/v1/audit/single</span> für eine
          einzelne PADnext-Lieferung,{" "}
          <span className="font-mono">POST /api/v1/audit/bulk</span> für ein
          ganzes Archiv.
        </p>
        <p className="text-sm text-muted-foreground">
          Ein Schlüssel gilt <strong>ausschliesslich für diese Praxis</strong>.
          Er bestimmt selbst, welche Daten eine Anfrage sehen darf — es gibt
          keinen Parameter, mit dem ein Aufrufer eine andere Organisation
          angeben könnte. Die vollständige Schnittstellenbeschreibung steht in{" "}
          <Link
            href="/api/engine/openapi"
            className="underline"
            prefetch={false}
          >
            der OpenAPI-Dokumentation
          </Link>{" "}
          der Engine.
        </p>
      </header>

      <ApiKeyManager />
    </>
  )
}
