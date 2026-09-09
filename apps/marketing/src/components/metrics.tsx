import { useTranslations } from "next-intl";
import { CountUp } from "@/components/count-up";
import { Reveal, RevealGroup, RevealItem } from "@/components/reveal";
import {
  ENFORCED_RULE_COUNT,
  LATENCY_MS_PER_INVOICE,
  ZIFFERN_UNDER_RULE_COUNT,
  engineFacts,
} from "@/lib/engine-facts";

/**
 * The numbers, counting up — and the section that stands where a testimonial would normally go.
 *
 * ## Why there is no testimonial here
 *
 * The brief asked for "Pilot-Ergebnisse (letzte 90 Tage)": 47 errors found, €12,340 saved per
 * month, 15 hours saved per week, under a quote attributed to "Dr. med. [Name], Praxis für
 * Orthopädie". There is no pilot in this repository, no customer, and no measurement behind any of
 * those four figures. Writing them would not be optimistic copy; it would be a fabricated
 * reference for a medical billing product, which is a §5 UWG problem before it is a taste problem,
 * and it would be the first thing a Datenschutzbeauftragte asks to see evidence for.
 *
 * The interesting question is what to put there instead, because "social proof" is doing real work
 * in a landing page and deleting it leaves a hole.
 *
 * The answer this section takes is that Azmoth's substitute for a reference customer is a
 * *checkable claim*. A billing centre cannot verify that Dr. med. Somebody saved €12,340 — they
 * can verify, in the demo, in under a minute, that the same delivery produces the same verdict
 * twice with a paragraph of the GOÄ printed beside it. Numbers that are pinned by a test suite are
 * a weaker emotional appeal and a much stronger argument, and on a page whose headline is
 * "deterministisch, nachvollziehbar" they are the only kind that does not undercut the headline.
 *
 * ## The third tile is the point
 *
 * Two of these numbers flatter the product. The third — 358 of 2,192 catalog positions have any
 * enforced rule speaking to them, sixteen percent — does not, and it is rendered at exactly the
 * same size as the other two rather than tucked into a footnote.
 *
 * That is a deliberate conversion decision, not a fit of conscience. The audience is billing
 * centres and PVS vendors who have been sold "KI-gestützte Abrechnungsoptimierung" before and know
 * that a product claiming to check everything is either lying or a language model guessing. Naming
 * the gap in the same typeface as the strengths is the single most credible thing this page can
 * do.
 *
 * This section shows that number and stops there. The *argument* around it — why an unaudited
 * position gets the "unbestätigt" category rather than a guess — already exists one section down,
 * on `startseite.buckets.ehrlichkeit`, and says it better because it says it where the three
 * categories are on screen. An earlier draft of this file repeated it in a panel of its own, which
 * put the same two sentences and the same three figures on the page twice, roughly a screen
 * apart. A number stated once and explained once reads as candour; stated twice it reads as a
 * disclaimer somebody was told to add.
 *
 * `lib/engine-facts.ts` computes all three from the same constants the engine's own
 * `test_published_numbers.py` pins, so none of them can drift without turning that suite red.
 */

/**
 * One tile. `value` is the number the tween runs to, `display` the server-formatted string it
 * lands on — see `components/count-up.tsx` for why those are two props rather than one.
 */
type Metric = {
  value: number;
  display: string;
  format?: "integer" | "percent";
  /** Rendered after the figure, at body size: "ms", "%", "von 894". */
  unit?: string;
};

export function Metrics() {
  const t = useTranslations("startseite.zahlen");

  const metrics: Metric[] = [
    {
      value: ENFORCED_RULE_COUNT,
      display: engineFacts.regelnDurchgesetzt,
      unit: t("regeln.einheit", { gesamt: engineFacts.regelnGesamt }),
    },
    {
      value: ZIFFERN_UNDER_RULE_COUNT,
      display: engineFacts.katalogGeprueft,
      unit: t("katalog.einheit", { gesamt: engineFacts.katalogZiffern }),
    },
    {
      value: LATENCY_MS_PER_INVOICE,
      display: engineFacts.laufzeitMs,
      unit: t("laufzeit.einheit"),
    },
  ];

  const labels = t.raw("kacheln") as { titel: string; text: string }[];

  return (
    <>
      <RevealGroup as="ul" className="mt-14 grid gap-4 sm:gap-6 md:grid-cols-3">
        {metrics.map((metric, index) => {
          const label = labels[index];
          return (
            <RevealItem key={label?.titel ?? index}>
              <div className="azm-lift flex h-full flex-col gap-3 rounded-2xl bg-white p-6 ring-1 ring-azm-hairline sm:p-8">
                {/*
                  `items-baseline`, so the unit sits on the figure's baseline rather than centred
                  against a 60px number — the difference between a designed stat and two spans that
                  happen to be adjacent.

                  The figure is `azm-display` at display-xl scale: `DESIGN.md` puts the display tier
                  at weight 300 with negative tracking, and a large thin numeral with tabular
                  figures is the house's whole numeric voice. Bolding it here, as the brief's
                  "72–96px, font-bold" asked, would make these three tiles the only place on the
                  site where a number is heavy.
                */}
                <p className="flex items-baseline gap-2">
                  <span className="azm-display text-[3rem] leading-none sm:text-[3.5rem]">
                    <CountUp
                      to={metric.value}
                      display={metric.display}
                      format={metric.format}
                    />
                  </span>
                  {metric.unit ? (
                    <span className="azm-tnum text-sm text-azm-ink-mute">{metric.unit}</span>
                  ) : null}
                </p>
                <p className="text-lg font-medium text-azm-ink">{label?.titel}</p>
                <p className="leading-relaxed text-muted-foreground">{label?.text}</p>
              </div>
            </RevealItem>
          );
        })}
      </RevealGroup>

      {/*
        The one share figure worth stating on its own line under the tiles.

        Only the catalog share — "358 von 2.192" said as a percentage — belongs here. The rules
        share (858 von 894, as a percentage) is a share of Azmoth's own rule table, not of the
        GOÄ, and printing it beside the catalog figure invited a reader to conflate the two; the
        honest coverage claim this page can make is `katalogAnteil` alone.
      */}
      <Reveal delay={0.1} className="mt-8">
        <p className="azm-tnum mx-auto max-w-2xl text-center text-sm leading-relaxed text-azm-ink-mute">
          {t("anteile", {
            katalogAnteil: engineFacts.katalogAnteil,
          })}
        </p>
      </Reveal>

    </>
  );
}
