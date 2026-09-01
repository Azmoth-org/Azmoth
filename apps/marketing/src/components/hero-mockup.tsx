import { useTranslations } from "next-intl";
import { CircleAlertIcon, CircleCheckIcon, CircleHelpIcon, FileTextIcon } from "lucide-react";

import { cn } from "@workspace/ui/lib/utils";

/**
 * The floating dashboard panel under the hero — a composited product-UI mockup, which `DESIGN.md`
 * names as the brand's most-photographed component and pairs with every feature explanation.
 *
 * ## Why this is drawn in DOM and not shipped as a screenshot
 *
 * A PNG of the real report would be the obvious route and is the wrong one three times over. It
 * would be the Largest Contentful Paint on a critical-path request, at whatever weight a 1200px
 * dashboard screenshot costs; it would need `width`/`height` to avoid a layout shift and would
 * still shift when the intrinsic ratio disagreed with the container; and it would be a picture of
 * a product that changes, taken on a day that recedes. Roughly forty elements of text and border
 * cost nothing to paint, scale to any viewport, stay legible at 320px, and are selectable — which
 * incidentally means the GOÄ paragraph in it is indexable text rather than pixels.
 *
 * ## Why the numbers in it are declared as a mockup
 *
 * Every figure this site prints about the engine comes from `lib/engine-facts.ts`, pinned by the
 * engine's own test suite, because "a number written into prose is a claim with no mechanism to
 * stay true". The rows here are not that: they are an illustration of the *shape* of a report, and
 * inventing a plausible-looking audit result is precisely the behaviour the product exists to
 * argue against. So the strings live in the catalogue under `startseite.mockup`, they describe a
 * synthetic delivery, and the panel says so in a caption under it rather than leaving a reader to
 * assume these are real findings.
 *
 * ## The tilt
 *
 * `perspective` on the wrapper and `rotateX` on the panel, both in CSS — a static transform, not
 * an animation, so it costs one composited layer and no frames. It is dropped below `lg`:
 * foreshortening a data table on a phone makes the bottom rows smaller than the top ones, and this
 * panel has to stay readable more than it has to look expensive.
 */

/** The three verdicts, keyed to the same tokens the engine's own report renders. */
const CATEGORIES = {
  bestaetigt: {
    icon: CircleCheckIcon,
    accent: "text-azm-confirmed",
    surface: "bg-azm-confirmed-bg",
    ring: "ring-azm-confirmed/20",
  },
  falsch: {
    icon: CircleAlertIcon,
    accent: "text-azm-wrong",
    surface: "bg-azm-wrong-bg",
    ring: "ring-azm-wrong/20",
  },
  unbestaetigt: {
    icon: CircleHelpIcon,
    accent: "text-azm-unconfirmed",
    surface: "bg-azm-unconfirmed-bg",
    ring: "ring-azm-unconfirmed/25",
  },
} as const;

type Row = {
  ziffer: string;
  leistung: string;
  kategorie: keyof typeof CATEGORIES;
  befund: string;
  /** The statute the finding rests on. Present only on a `falsch` row — that is the whole point. */
  grundlage?: string;
};

/**
 * The order the three buckets appear in, in both the tiles here and `startseite.buckets.spalten`.
 * The tile labels are read from that array rather than restated, so the summary tile and the
 * section further down the page cannot end up using two different words for one verdict.
 */
const ORDER = ["bestaetigt", "falsch", "unbestaetigt"] as const;

export function HeroMockup() {
  const t = useTranslations("startseite.mockup");
  const tBuckets = useTranslations("startseite.buckets");
  const rows = t.raw("zeilen") as Row[];
  const bucketNames = (tBuckets.raw("spalten") as { titel: string }[]).map(
    (column) => column.titel
  );

  return (
    <figure className="[perspective:1600px]">
      <div
        role="img"
        aria-label={t("ariaLabel")}
        className={cn(
          "overflow-hidden rounded-2xl bg-white ring-1 ring-azm-hairline",
          "shadow-[0_8px_24px_rgba(0,55,112,0.08),0_2px_6px_rgba(0,55,112,0.04)]",
          /*
            Level 2 elevation plus the tilt. `origin-top` so the panel appears to lean away from
            the reader rather than pivot around its middle, which is what keeps the top edge — the
            part carrying the summary tiles — at full scale.
          */
          "lg:[transform:rotateX(14deg)_scale(1.02)] lg:origin-top"
        )}
      >
        {/* Window chrome. The three dots are the convention that says "this is an application". */}
        <div className="flex items-center gap-3 border-b border-azm-hairline bg-azm-canvas-soft px-4 py-3">
          <span aria-hidden="true" className="flex gap-1.5">
            <span className="size-2.5 rounded-full bg-azm-hairline" />
            <span className="size-2.5 rounded-full bg-azm-hairline" />
            <span className="size-2.5 rounded-full bg-azm-hairline" />
          </span>
          <span className="flex items-center gap-2 text-xs font-medium text-azm-ink-secondary">
            <FileTextIcon className="size-3.5 text-primary" aria-hidden="true" />
            {t("titel")}
          </span>
          <span className="azm-tnum ml-auto truncate text-xs text-azm-ink-mute">
            {t("datei")}
          </span>
        </div>

        <div className="p-4 sm:p-6">
          {/*
            The three buckets as tiles, in the order the report uses them. The count is derived
            from the rows below rather than written down, so the tile and the table cannot
            disagree — the same discipline `engine-facts.ts` applies to the real figures.
          */}
          <div className="grid grid-cols-3 gap-2 sm:gap-3">
            {ORDER.map((key, index) => {
              const category = CATEGORIES[key];
              const Icon = category.icon;
              const count = rows.filter((row) => row.kategorie === key).length;
              return (
                <div
                  key={key}
                  className={cn(
                    "rounded-xl p-3 ring-1 sm:p-4",
                    category.surface,
                    category.ring
                  )}
                >
                  <Icon
                    aria-hidden="true"
                    className={cn("size-4 sm:size-5", category.accent)}
                  />
                  <p
                    className={cn(
                      "azm-tnum mt-2 text-xl font-light sm:text-2xl",
                      category.accent
                    )}
                  >
                    {count}
                  </p>
                  <p className="mt-0.5 truncate text-[0.6875rem] text-azm-ink-mute sm:text-xs">
                    {bucketNames[index]}
                  </p>
                </div>
              );
            })}
          </div>

          <div className="mt-4 overflow-hidden rounded-xl ring-1 ring-azm-hairline sm:mt-6">
            <div className="grid grid-cols-[3.5rem_1fr] gap-3 border-b border-azm-hairline bg-azm-canvas-soft px-3 py-2 text-[0.625rem] font-medium tracking-[0.08em] text-azm-ink-mute uppercase sm:px-4">
              <span>{t("spalteZiffer")}</span>
              <span>{t("spalteBefund")}</span>
            </div>
            <ul>
              {rows.map((row) => {
                const category = CATEGORIES[row.kategorie] ?? CATEGORIES.unbestaetigt;
                const Icon = category.icon;
                return (
                  <li
                    key={row.ziffer}
                    className="grid grid-cols-[3.5rem_1fr] items-start gap-3 border-b border-azm-hairline px-3 py-2.5 last:border-b-0 sm:px-4"
                  >
                    <span className="azm-tnum text-xs font-medium text-azm-ink sm:text-sm">
                      {row.ziffer}
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5">
                        <Icon
                          aria-hidden="true"
                          className={cn("size-3.5 shrink-0", category.accent)}
                        />
                        <span className="truncate text-xs text-azm-ink sm:text-sm">
                          {row.leistung}
                        </span>
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-[0.6875rem] text-azm-ink-mute sm:text-xs">
                          {row.befund}
                        </span>
                        {/*
                          The statute, rendered as a code chip. It is the single most important
                          pixel in this mockup: the whole argument of the page is that a rejection
                          arrives with the paragraph it follows from, and this is where a reader
                          sees that rather than reads a claim about it.
                        */}
                        {row.grundlage ? (
                          <code className="azm-tnum rounded bg-azm-wrong/10 px-1.5 py-0.5 text-[0.625rem] font-medium text-azm-wrong sm:text-[0.6875rem]">
                            {row.grundlage}
                          </code>
                        ) : null}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </div>

      <figcaption className="mt-4 text-center text-xs text-azm-ink-mute">
        {t("hinweis")}
      </figcaption>
    </figure>
  );
}
