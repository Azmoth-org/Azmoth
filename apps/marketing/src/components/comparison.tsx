import { useTranslations } from "next-intl";
import { CheckIcon, MinusIcon } from "lucide-react";

import { cn } from "@workspace/ui/lib/utils";

import { Reveal } from "@/components/reveal";
import { engineFacts } from "@/lib/engine-facts";

/**
 * Manual review beside automated review, one row per thing that actually differs.
 *
 * ## What this section is allowed to claim
 *
 * The brief this was built from asked for "4 Stunden/Woche → 5 Minuten", "5–15 % Fehlerquote →
 * 99,3 % geprüft" and "€12k Regress-Risiko → €0 Risiko". None of those six numbers exists
 * anywhere in this repository, and three of them are not the kind of thing that could: nobody here
 * has measured how long a billing centre spends reviewing, what their error rate is, or what a
 * Regress costs them.
 *
 * `lib/engine-facts.ts` exists because this product already shipped wrong numbers once, in a
 * customer-facing PDF and a partner contract, and the engine's test suite now fails if the
 * marketing figures drift from what the pipeline computes. A comparison table that invents a
 * "5–15 % Fehlerquote" walks straight past that mechanism — and does it on the page whose headline
 * is that Azmoth does not assert what it cannot prove.
 *
 * So the left column describes *properties* of manual review rather than measurements of it. "Two
 * reviewers can reach two verdicts" is a true statement about human judgement that needs no study
 * behind it; "5–15 % Fehlerquote" is a citation, and there is nothing to cite. Only the right
 * column carries digits, and every one of them comes from `engineFacts`.
 *
 * That turns out to be the stronger pitch anyway. The claim "we are faster than you" invites a
 * billing centre to dispute the baseline; the claim "the same delivery produces the same verdict
 * twice, with the paragraph printed next to it" is one they can check in the demo in a minute.
 *
 * ## Why not a `<table>`
 *
 * The rows pair semantically but they are not tabular data — there is no cell here you would want
 * to read down a column and compare. It is two lists in visual parallel, and it collapses to two
 * stacked lists on a phone, which a real `<table>` cannot do without `display: block` overrides
 * that strip its semantics anyway. Two `<ul>`s in a grid degrade honestly at every width.
 */

type Row = { manuell: string; azmoth: string };

export function Comparison() {
  const t = useTranslations("startseite.vergleich");
  /*
   * ICU placeholders are resolved here rather than in the catalogue, so the German copy holds
   * `{regeln}` and never a digit — the same discipline `Workflow` already applies to step two.
   * `t.raw()` bypasses interpolation, so the values are substituted after the fact.
   */
  const rows = (t.raw("zeilen") as Row[]).map((row) => ({
    manuell: row.manuell,
    azmoth: row.azmoth
      .replace("{regeln}", engineFacts.regelnDurchgesetzt)
      .replace("{laufzeit}", engineFacts.laufzeitMs),
  }));

  return (
    <div className="mt-14 grid gap-4 md:grid-cols-2 md:gap-6">
      {/*
        The muted column first in source order, because that is also the reading order: a visitor
        recognises their current situation, then sees what replaces it. Reversing them would put
        the answer before the question.
      */}
      <Reveal>
        <div className="h-full rounded-2xl bg-azm-canvas-soft p-6 ring-1 ring-azm-hairline sm:p-8">
          <p className="text-[0.6875rem] font-medium tracking-[0.12em] text-azm-ink-mute uppercase">
            {t("manuellTitel")}
          </p>
          <ul className="mt-6 flex flex-col gap-5">
            {rows.map((row) => (
              <li key={row.manuell} className="flex items-start gap-3">
                {/*
                  A minus rather than a cross. The left column is not a list of failures — manual
                  GOÄ review is done by competent people and mostly works. What it lacks is
                  *guarantees*, and a red ✗ against "zwei Prüfer, zwei Ergebnisse" would read as an
                  accusation aimed at the person being asked to buy this.
                */}
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-azm-ink/8 text-azm-ink-mute">
                  <MinusIcon aria-hidden="true" className="size-3" />
                </span>
                <span className="leading-relaxed text-azm-ink-secondary">{row.manuell}</span>
              </li>
            ))}
          </ul>
        </div>
      </Reveal>

      <Reveal delay={0.1}>
        {/*
          The solution column carries the brand rather than a green wash. `DESIGN.md`'s indigo is
          the product's colour; emerald here would collide with `--azm-confirmed`, which this site
          reserves for one specific meaning — a position the engine accepted. Using it decoratively
          on a marketing card would spend the one colour whose meaning the report depends on.
        */}
        <div className="azm-lift relative h-full overflow-hidden rounded-2xl bg-azm-navy p-6 text-white ring-1 ring-azm-navy/20 sm:p-8">
          <div aria-hidden="true" className="azm-mesh opacity-40" />
          <div className="relative">
            <p className="text-[0.6875rem] font-medium tracking-[0.12em] text-white/55 uppercase">
              {t("azmothTitel")}
            </p>
            <ul className="mt-6 flex flex-col gap-5">
              {rows.map((row) => (
                <li key={row.azmoth} className="flex items-start gap-3">
                  <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-white/15 text-white">
                    <CheckIcon aria-hidden="true" className="size-3" />
                  </span>
                  {/*
                    `azm-tnum` on a line that may carry "858" or "80 ms". Tabular figures are the
                    house rule wherever a number appears in prose on this site; it costs nothing on
                    the lines that have none.
                  */}
                  <span className={cn("azm-tnum leading-relaxed text-white/90")}>
                    {row.azmoth}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Reveal>
    </div>
  );
}
