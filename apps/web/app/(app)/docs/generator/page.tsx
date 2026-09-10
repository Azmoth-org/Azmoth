import { ArrowRightIcon } from "lucide-react"
import type { Metadata } from "next"
import Link from "next/link"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"

export const metadata: Metadata = {
  title: "Testlieferung erzeugen",
  description:
    "Ein Kommandozeilenskript, das eine synthetische PADnext-Testlieferung ohne echte Daten erzeugt.",
}

/**
 * `/docs/generator` — how to produce a delivery to try the pilot on, with no PVS export at hand.
 *
 * Linked from the first-run dashboard card and nowhere else — this is documentation for one
 * command, not a workspace, so it carries no entry in `WORKSPACE_ITEMS`.
 *
 * The script itself, `scripts/generate_synthetic_delivery.py`, lives at the repository root next to
 * `scripts/anonymize_padnext.py` rather than under `apps/engine` or `apps/web`: it depends on
 * neither, reads nothing from either service, and a reader trying the pilot should not need either
 * app's dependencies installed to run one Python file.
 */
export default function GeneratorDocsPage() {
  return (
    <>
      <header className="space-y-1.5">
        <h1 className="text-display-md">Synthetische Testlieferung erzeugen</h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          Ein einzelnes Kommandozeilenskript, ohne Abhängigkeiten, das eine
          PADnext-Testlieferung mit frei erfundenen GOÄ-Positionen schreibt —
          für den Fall, dass keine eigene Lieferung zur Hand ist, um den Pilot
          auszuprobieren.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ausführen</CardTitle>
          <CardDescription>
            Python 3.9 oder neuer, sonst nichts. Kein Netzwerkzugriff, keine
            weiteren Pakete.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <pre className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs">
            python3 scripts/generate_synthetic_delivery.py
          </pre>
          <p className="text-sm text-muted-foreground">
            Schreibt eine Datei wie{" "}
            <span className="font-mono">
              00000000_20260910_ADL_123456_padx.xml
            </span>{" "}
            im aktuellen Verzeichnis, mit drei erfundenen GOÄ-Positionen und{" "}
            <span className="font-mono">echtdaten=&quot;false&quot;</span>{" "}
            von Anfang an. Kein Patient, keine Adresse, keine Versichertennummer
            — nur ein Platzhaltername, weil das Feld selbst zur Struktur einer
            PADnext-Lieferung gehört.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Optionen</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <pre className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs">
            {`python3 scripts/generate_synthetic_delivery.py \\
  --positions 5 \\
  --seed 7 \\
  -o meine-testlieferung.xml`}
          </pre>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            <li>
              <span className="font-mono">--positions</span> — wie viele
              GOÄ-Zeilen erzeugt werden (Standard: 3).
            </li>
            <li>
              <span className="font-mono">--seed</span> — macht den Lauf
              wiederholbar: derselbe Seed erzeugt dieselbe Lieferung.
            </li>
            <li>
              <span className="font-mono">-o</span> — der Ausgabepfad.
            </li>
          </ul>
        </CardContent>
      </Card>

      <section className="rounded-xl border border-dashed p-4">
        <h2 className="text-sm font-semibold">Und dann?</h2>
        <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">
          Die erzeugte Datei lässt sich direkt hochladen —{" "}
          <Link
            href="/padnext"
            className="inline-flex items-center gap-1 font-medium underline underline-offset-4"
          >
            /padnext
            <ArrowRightIcon className="size-3" aria-hidden />
          </Link>{" "}
          für eine einzelne Lieferung.
        </p>
      </section>
    </>
  )
}
