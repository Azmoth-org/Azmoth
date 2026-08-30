import type { Metadata } from "next"
import {
  FileTextIcon,
  ScaleIcon,
  ShieldCheckIcon,
  SplitIcon,
} from "lucide-react"

import { Card, CardContent } from "@workspace/ui/components/card"

import { DemoModeBanner } from "@/components/demo/demo-mode-banner"
import { StartDemoButton } from "@/components/demo/start-demo-button"

export const metadata: Metadata = {
  title: "Demo",
  description:
    "GOÄ-Rechnungsprüfung an einer synthetischen Beispiellieferung ausprobieren — " +
    "ohne Anmeldung und ohne Upload.",
}

/**
 * `/demo` — the public track. Explains the product, then runs it on a file we shipped.
 *
 * ## Why this page exists as its own route
 *
 * The two tracks in this application answer two different questions, and conflating them is the
 * legal risk the whole design is arranged around. This one answers *"what does it do"* and can be
 * public precisely because nothing a visitor sends is processed — there is no file input on this
 * page and the endpoint behind the button accepts no body. The other answers *"what does it say
 * about my invoices"* and is gated behind an allowlisted account, because that one involves a
 * document belonging to a practice.
 *
 * A server component. Only the button and the PDF download are interactive; the explanation of the
 * three buckets has to render even if the client bundle never arrives, because it is the part that
 * stops the numbers on the next screen being misread.
 *
 * ## Why the value proposition is stated before the button and not after
 *
 * The report is worth nothing to a first-time reader who has not been told what the amber bucket
 * means. »Nicht beurteilbar« is the largest of the three figures on the demo delivery, and a
 * visitor who meets it cold reads it as "money at risk" — which is the one misreading that would
 * make this product look like the thing it was built not to be. So the three-way split is
 * explained here, in prose, before anyone can see a number.
 */
export default function DemoPage() {
  return (
    <>
      <DemoModeBanner />

      <header className="space-y-4 pt-2">
        <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          GOÄ-Prüfung, die jede Entscheidung belegen kann
        </h1>
        <p className="max-w-2xl text-base leading-relaxed text-muted-foreground">
          Azmoth prüft eine bereits kodierte PADnext-Lieferung gegen die GOÄ und
          rechnet jeden Betrag aus einem versionierten Katalog nach. Kein
          Sprachmodell, keine Schätzung: Jede Beanstandung trägt die Regel und
          die Rechtsgrundlage, auf der sie beruht — und einen Receipt-Hash, mit
          dem sich der Prüfstand später nachweisen lässt.
        </p>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Sehen Sie sich das an einer synthetischen Beispielrechnung an, in die
          neun typische Abrechnungsfehler eingebaut sind. Es wird nichts
          hochgeladen und nichts gespeichert.
        </p>

        <StartDemoButton />
      </header>

      <section aria-labelledby="value" className="space-y-4 pt-4">
        <h2
          id="value"
          className="text-xs font-medium tracking-wide text-muted-foreground uppercase"
        >
          Was diese Prüfung leistet
        </h2>

        <div className="grid gap-4 sm:grid-cols-3">
          <ValueCard
            icon={<ScaleIcon aria-hidden className="size-5 text-primary" />}
            title="Deterministisch, nicht geraten"
            body="Dieselbe Rechnung ergibt immer dasselbe Ergebnis. Ein Datalog-Programm entscheidet, welche Positionen bestehen; ein unabhängiger Prüflauf rechnet das Ergebnis nach. Jede Position trägt ihren Beweisbaum mit Regel-ID und Paragraphenbezug."
          />
          <ValueCard
            icon={<SplitIcon aria-hidden className="size-5 text-primary" />}
            title="Drei Gruppen statt einer Summe"
            body="Belegbar korrekt, belegbar nicht abrechenbar, nicht beurteilbar. Die dritte Gruppe ist die Grenze unserer Regelabdeckung und ausdrücklich kein Vorwurf gegen die Praxis. Die drei Beträge werden nie zu einer Zahl »Risiko« zusammengefasst."
          />
          <ValueCard
            icon={<FileTextIcon aria-hidden className="size-5 text-primary" />}
            title="Prüfbericht als PDF"
            body="Ein druckbarer Bericht mit den drei Beträgen, der Prüfabdeckung und der vollständigen Prüfgrundlage: Katalogfassung, Katalog-Hash, Regel- und Logikstand. Derselbe Auftrag ergibt immer dieselbe Datei."
          />
        </div>
      </section>

      <section aria-labelledby="honesty" className="pt-2">
        <h2 id="honesty" className="sr-only">
          Zur Lesart der dritten Gruppe
        </h2>
        <Card className="border-dashed">
          <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:gap-5">
            <ShieldCheckIcon
              aria-hidden
              className="size-5 shrink-0 text-muted-foreground"
            />
            <div className="space-y-2">
              <p className="text-sm leading-relaxed">
                <strong className="font-semibold">
                  Eine Zahl, die Sie gleich sehen werden, erklären wir lieber
                  vorher.
                </strong>{" "}
                Auf dieser Beispielrechnung ist{" "}
                <em>nicht beurteilbar</em> der grösste der drei Beträge. Das ist
                kein Befund gegen die Rechnung — es bedeutet, dass für diese
                Ziffern noch keine von einer Abrechnungsfachkraft bestätigte
                Regel hinterlegt ist.
              </p>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Wir weisen das getrennt aus, statt es in eine Risikosumme zu
                falten. Eine solche Summe würde aus unserer eigenen
                Abdeckungslücke eine Anschuldigung gegen die Praxis machen — und
                genau das ist der Fehler, den ein Prüfbericht nicht machen darf.
                Die ehrliche Kennzahl ist die <em>Prüfabdeckung</em>: wie viel
                der Rechnung überhaupt beurteilt werden konnte.
              </p>
            </div>
          </CardContent>
        </Card>
      </section>
    </>
  )
}

function ValueCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode
  title: string
  body: string
}) {
  return (
    <Card>
      <CardContent className="space-y-2 pt-6">
        {icon}
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-sm leading-relaxed text-muted-foreground">{body}</p>
      </CardContent>
    </Card>
  )
}
