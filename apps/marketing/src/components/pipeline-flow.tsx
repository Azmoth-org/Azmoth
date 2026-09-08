import { useTranslations } from "next-intl";
import {
  ChevronRightIcon,
  CircleAlertIcon,
  CircleCheckIcon,
  CircleHelpIcon,
  CpuIcon,
  FileCheckIcon,
  FileCodeIcon,
} from "lucide-react";

import { cn } from "@workspace/ui/lib/utils";

import { engineFacts } from "@/lib/engine-facts";

/**
 * The hero's answer to "what does this thing do", as a diagram: delivery in, rules applied,
 * report out.
 *
 * ## Why this is a server component
 *
 * It looks like the most animation-heavy element on the site and it ships zero JavaScript. The
 * whole sequence — three stages arriving, two connectors drawing, four verdicts landing, a pulse
 * travelling — is `animation-delay` on server-rendered markup. See the pipeline block in
 * `app/globals.css` for the measurements behind that; the short version is that this element sits
 * directly under the `<h1>` that is this page's Largest Contentful Paint, and every client
 * component placed there has historically cost the metric several hundred milliseconds while
 * buying an effect CSS could already express.
 *
 * The practical consequence is that the timings live in two places — the keyframes in the
 * stylesheet, the per-element offsets in `DELAYS` below — and they have to be read together. That
 * is the price of keeping the hero free of hydration, and it is worth it here specifically because
 * the sequence is fixed: nothing about it responds to input, so there is no state for JavaScript
 * to own.
 *
 * ## Why the verdicts are the mockup's rows
 *
 * The chips are not written here. They are `startseite.mockup.zeilen` — the same four rows the
 * `<HeroMockup>` report renders further down the page, read from the same catalogue key.
 *
 * That is deliberate and it is the only interesting decision in this file. A visitor reads the
 * pipeline, scrolls, and reads the report; if the pipeline says Ziffer 5 was rejected and the
 * report shows a different set of positions, the two elements describe two different products.
 * Sharing the source means the hero cannot drift from the artefact it is promising, and it means
 * the "Beispieldarstellung, synthetische Lieferung" disclaimer the mockup already carries covers
 * both — these are the same four synthetic positions, shown twice.
 */

/**
 * The three verdict categories, keyed to the same tokens the engine's own report uses.
 *
 * Duplicated in shape from `components/hero-mockup.tsx` rather than shared, because the two render
 * different things from it: the mockup needs table-row surfaces, this needs pill chips. Extracting
 * a common module would export a map of Tailwind class strings that neither file could read
 * without jumping to it. What must not drift is the *colour semantics*, and that is already
 * guaranteed one level down — both files name `--azm-confirmed` and its neighbours.
 */
const CATEGORIES = {
  bestaetigt: {
    icon: CircleCheckIcon,
    chip: "bg-azm-confirmed-bg text-azm-confirmed ring-azm-confirmed/25",
  },
  falsch: {
    icon: CircleAlertIcon,
    chip: "bg-azm-wrong-bg text-azm-wrong ring-azm-wrong/25",
  },
  unbestaetigt: {
    icon: CircleHelpIcon,
    chip: "bg-azm-unconfirmed-bg text-azm-unconfirmed ring-azm-unconfirmed/30",
  },
} as const;

type Row = {
  ziffer: string;
  kategorie: keyof typeof CATEGORIES;
  grundlage?: string;
  befund: string;
};

/**
 * The sequence, in milliseconds, as one table rather than scattered inline.
 *
 * Read top to bottom it *is* the storyboard: the file arrives, the connector draws, the engine
 * appears, four verdicts land 120ms apart, the second connector draws, the report appears. Keeping
 * them adjacent is what makes the sequence adjustable — spread across six JSX attributes, changing
 * the pace means finding and re-deriving every number.
 */
const DELAYS = {
  input: 0,
  connectorA: 180,
  engine: 320,
  /** The first verdict. Each subsequent chip adds `CHIP_STAGGER`. */
  firstChip: 520,
  connectorB: 1040,
  output: 1180,
} as const;

const CHIP_STAGGER = 120;

/** An inline `--azm-stage-delay`, since Tailwind cannot express a per-element custom property. */
function delay(ms: number): React.CSSProperties {
  return { "--azm-stage-delay": `${ms}ms` } as React.CSSProperties;
}

/**
 * One box in the flow.
 *
 * `tone="engine"` inverts to navy because the middle stage is the product and the two either side
 * are the customer's file formats. Three identical cards would draw a diagram of a conveyor belt;
 * the polarity flip is what makes it read as "your data goes through *our* thing".
 */
function Stage({
  icon: Icon,
  label,
  detail,
  tone = "plain",
  delayMs,
}: {
  icon: typeof CpuIcon;
  label: string;
  detail: string;
  tone?: "plain" | "engine";
  delayMs: number;
}) {
  const isEngine = tone === "engine";

  return (
    <div
      className={cn(
        "azm-stage flex min-w-0 flex-col items-center gap-2 rounded-2xl px-4 py-5 text-center ring-1",
        isEngine
          ? "bg-azm-navy text-white ring-azm-navy/20 shadow-[0_8px_24px_rgba(0,55,112,0.14)]"
          : "bg-white/90 text-azm-ink ring-azm-hairline backdrop-blur-sm"
      )}
      style={delay(delayMs)}
    >
      <span
        className={cn(
          "flex size-10 items-center justify-center rounded-xl",
          isEngine ? "bg-white/12 text-white" : "bg-primary/10 text-primary"
        )}
      >
        <Icon aria-hidden="true" className="size-5" />
      </span>
      <span className="text-sm font-medium">{label}</span>
      {/*
        `break-words` and not `truncate`. The detail line carries a filename and a rule count, and
        at 360px the German label above it is already close to the cell width — truncating would
        hide the half of "lieferung-beispiel.padx" that identifies it as a PADnext file at all.
      */}
      <span
        className={cn(
          "azm-tnum text-[0.6875rem] leading-snug break-words",
          isEngine ? "text-white/65" : "text-azm-ink-mute"
        )}
      >
        {detail}
      </span>
    </div>
  );
}

/**
 * The line between two stages, with a pulse travelling down it.
 *
 * It is horizontal on desktop and vertical on mobile, and both orientations come out of one
 * element by rotating the *track* rather than by rendering two. The alternative — a `hidden
 * md:block` pair — ships the pulse twice and gives the reduced-motion rule two things to find.
 *
 * `aria-hidden`, because a connector is punctuation. The reading order a screen reader gets is
 * "PADnext-Lieferung, Azmoth Engine, Prüfbericht", which is the sentence this diagram is drawing;
 * announcing the arrows between them adds nothing a list does not already imply.
 */
function Connector({ delayMs }: { delayMs: number }) {
  return (
    <div aria-hidden="true" className="flex items-center justify-center py-1 md:py-0">
      {/*
        Column while stacked, row from `md` — the same flip the grid itself makes, so the line and
        its arrowhead stay in reading order at both widths.
      */}
      <div className="flex flex-col items-center md:w-full md:flex-row">
        {/*
          Two pixels, not one.

          The first version was a 1px hairline with a `primary/40` midpoint, and at 1440px it was
          effectively invisible — the two stage cards read as sitting next to each other rather
          than as being connected, which loses the one thing the diagram exists to say. A hairline
          is right for a border, where the eye only needs to find an edge; a connector is a
          *figure* and has to survive beside two filled cards and a navy panel.
        */}
        <div className="relative h-8 w-0.5 overflow-hidden rounded-full md:h-0.5 md:w-full md:min-w-6">
          <div
            className="azm-connector absolute inset-0 bg-linear-to-b from-primary/15 via-primary/50 to-primary/15 md:bg-linear-to-r"
            style={delay(delayMs)}
          />
          {/*
            The pulse: a full-size element whose own extent the `-100% → 100%` sweep is measured
            against, so it crosses the connector exactly once whatever the track resolves to. The
            parent's `overflow-hidden` clips the half of the travel that happens outside.

            The gradient axis follows the connector's orientation — `to bottom` while stacked, `to
            right` from `md` up — for the same reason the track itself does.
          */}
          <div
            className="azm-pulse absolute inset-0 bg-linear-to-b from-transparent via-white to-transparent md:bg-linear-to-r"
            style={delay(delayMs)}
          />
        </div>

        {/*
          The arrowhead, which is what actually makes this directional.

          A plain line between two boxes is ambiguous — it could be a connection, a divider or a
          relationship. The chevron is the difference between "these two things are related" and
          "the thing on the left becomes the thing on the right", and the second reading is the
          whole point of the hero.

          One icon rotated rather than two swapped at the breakpoint: `rotate-90` points it down
          the stacked column, `md:rotate-0` restores the horizontal flow. Rotation is a transform,
          so nothing reflows when the breakpoint crosses.

          The negative margin pulls it over the line's rounded end so the two read as one arrow
          rather than as a line with a chevron parked near it.
        */}
        <ChevronRightIcon
          className="azm-stage -mt-1 size-3.5 rotate-90 text-primary/60 md:mt-0 md:-ml-1 md:rotate-0"
          style={delay(delayMs)}
        />
      </div>
    </div>
  );
}

export function PipelineFlow() {
  const t = useTranslations("startseite.pipeline");
  const tMockup = useTranslations("startseite.mockup");
  const rows = tMockup.raw("zeilen") as Row[];

  return (
    <figure
      className="mx-auto w-full max-w-3xl"
      aria-label={t("ariaLabel")}
    >
      {/*
        A grid, not a flex row, and the column template is what makes the connectors work: the
        stages take equal fractions and the connectors take what is left, so the three boxes stay
        the same width whatever their content. On mobile it collapses to one column and the same
        connectors become the vertical joins between stacked stages.
      */}
      <div className="grid grid-cols-1 items-stretch gap-0 md:grid-cols-[1fr_auto_1.15fr_auto_1fr] md:gap-2">
        <Stage
          icon={FileCodeIcon}
          label={t("eingabe.titel")}
          detail={t("eingabe.detail")}
          delayMs={DELAYS.input}
        />
        <Connector delayMs={DELAYS.connectorA} />
        <Stage
          icon={CpuIcon}
          tone="engine"
          label={t("engine.titel")}
          detail={t("engine.detail", {
            regeln: engineFacts.regelnDurchgesetzt,
            laufzeit: engineFacts.laufzeitMs,
          })}
          delayMs={DELAYS.engine}
        />
        <Connector delayMs={DELAYS.connectorB} />
        <Stage
          icon={FileCheckIcon}
          label={t("ausgabe.titel")}
          detail={t("ausgabe.detail")}
          delayMs={DELAYS.output}
        />
      </div>

      {/*
        The verdicts landing.

        They sit *under* the row rather than floating over the engine box, which is a deliberate
        retreat from the brief's sketch. Absolutely positioned chips around a centre stage look
        right at 1280px and become an overlap-and-overflow problem at 390px, where this site's
        largest audience segment reads it — and horizontal overflow on the hero is a bug this
        codebase has already fixed twice (see the `min-w-0` note on the API section). A wrapping
        row keeps the same "results arriving" reading at every width, because the sequencing does
        the work rather than the placement.
      */}
      <ul className="mt-5 flex flex-wrap items-center justify-center gap-2">
        {rows.map((row, index) => {
          const category = CATEGORIES[row.kategorie] ?? CATEGORIES.unbestaetigt;
          const Icon = category.icon;
          return (
            <li
              key={row.ziffer}
              className={cn(
                "azm-chip flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.6875rem] font-medium ring-1",
                category.chip
              )}
              style={delay(DELAYS.firstChip + index * CHIP_STAGGER)}
            >
              <Icon aria-hidden="true" className="size-3" />
              <span className="azm-tnum">
                {t("ziffer", { ziffer: row.ziffer })}
              </span>
              {/*
                The legal citation when there is one, and nothing when there is not.

                This is the detail that makes the chips worth rendering at all. "Ziffer 4 ✗" is a
                claim; "Ziffer 4 · GOÄ Anmerkung zu Nummer 4 · excl_auto_34_4" is the claim plus the
                thing a billing centre would have to quote back to an Erstattungsstelle. The site's
                whole argument is that the second one is what it produces, so the hero should show
                it rather than describe it.
              */}
              {row.grundlage ? (
                <span className="border-l border-current/25 pl-1.5 opacity-80">
                  {row.grundlage}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>

      <figcaption className="mt-4 text-center text-[0.6875rem] leading-relaxed text-azm-ink-mute">
        {t("hinweis")}
      </figcaption>
    </figure>
  );
}
