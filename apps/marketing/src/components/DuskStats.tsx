"use client";

import { useTranslations } from "next-intl";

/**
 * Tailark dusk-stats-1 adapted: real SILKDEV metrics + the Google rating.
 * Runs under the `.dusk` token scope (shadcn utilities resolve to the
 * site's dark palette).
 */
export default function DuskStats() {
  const t = useTranslations("home");

  const metrics = [
    { value: "4+", label: t("metric1") },
    { value: "4", label: t("metric3") },
    { value: "6+", label: t("metric2") },
  ];

  return (
    <section className="dusk py-16 md:py-20">
      <div className="mx-auto max-w-7xl">
        <div className="grid gap-4 md:grid-cols-2 md:gap-6">
          <h2 className="text-muted-foreground max-w-4xl text-balance text-4xl font-medium tracking-tight lg:text-5xl">
            <span className="text-foreground">{t("statsHead1")}</span> <br /> {t("statsHead2")}
          </h2>
          <div className="flex flex-col gap-12 md:mx-auto xl:gap-16">
            <p className="text-muted-foreground text-balance text-lg">{t("statsSub")}</p>

            <div className="grid gap-8 md:grid-cols-2 md:gap-12">
              {metrics.map((m) => (
                <div key={m.label} className="space-y-3 border-t pt-6">
                  <div className="text-4xl font-semibold tracking-tight text-foreground">{m.value}</div>
                  <p className="text-muted-foreground">{m.label}</p>
                </div>
              ))}
            </div>

            {/* Google Business rating — real verified evidence */}
            <div className="flex flex-wrap items-center gap-2 border-t pt-6">
              <span className="text-muted-foreground">{t("ratedLabel")}</span>
              <span className="flex items-center gap-1 text-white font-medium">
                5.0
                <svg className="w-3.5 h-3.5 text-[var(--accent)]" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2l2.9 6.26 6.86.6-5.2 4.53 1.55 6.71L12 16.9 5.89 20.1l1.55-6.71-5.2-4.53 6.86-.6z" />
                </svg>
              </span>
              <span className="text-muted-foreground">{t("ratedGoogle")}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
