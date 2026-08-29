"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { TransitionLink } from "@/components/TransitionLink";
import { openChat } from "@/lib/openChat";

export type DuskService = {
  slug: string;
  accent: string;
  icon: React.ReactNode;
  labelKey: string;
};

/**
 * Tailark dusk-features-1 adapted: the real service offerings in the
 * block's card layout (big card + wide card + icon rows), each linking
 * to its service page.
 */
export default function DuskFeatures({ services }: { services: DuskService[] }) {
  const t = useTranslations("home");
  const st = useTranslations("services");
  const offerings = st.raw("offerings") as Record<string, { title: string; tagline: string }>;

  const [primary, wide, ...rest] = services;
  const data = (slug: string) => offerings[slug];

  return (
    <section className="dusk py-16 md:py-20" id="services-grid">
      <div className="mx-auto max-w-7xl">
        <h2 className="text-muted-foreground max-w-4xl text-balance text-4xl font-medium tracking-tight lg:text-5xl">
          <span className="text-foreground">{t("servicesTitle")}.</span> <br /> {t("servicesSub")}
        </h2>

        <div className="*:bg-background mt-8 grid gap-3 md:mt-16 md:grid-cols-2 lg:grid-cols-3">
          {/* Big card — flagship service */}
          {primary && (
            <TransitionLink href={`/services/${primary.slug}`} className="bg-card group p-8 block">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ background: `${primary.accent}15`, color: primary.accent }}>
                {primary.icon}
              </div>
              <p className="text-muted-foreground max-w-xs text-lg font-medium mt-6">
                <span className="text-foreground">{data(primary.slug)?.title ?? primary.labelKey}.</span>{" "}
                {data(primary.slug)?.tagline}
              </p>

              <div className="my-16">
                <div className="relative mx-auto aspect-[16/10] w-11/12 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--background)] shadow-lg shadow-black/20">
                  <img
                    src="/images/hero-silkloom.webp"
                    alt="SILKLOOM — AI workflow agents that weave themselves"
                    className="h-full w-full object-cover object-top"
                    loading="lazy"
                  />
                </div>
              </div>
            </TransitionLink>
          )}

          {/* Wide card */}
          {wide && (
            <TransitionLink href={`/services/${wide.slug}`} className="bg-card group lg:col-span-2 block">
              <div className="p-8">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ background: `${wide.accent}15`, color: wide.accent }}>
                  {wide.icon}
                </div>
                <p className="text-muted-foreground max-w-xs text-lg font-medium mt-6">
                  <span className="text-foreground">{data(wide.slug)?.title ?? wide.labelKey}.</span>{" "}
                  {data(wide.slug)?.tagline}
                </p>
              </div>

              <div className="mask-x-from-65% mt-6 pt-2">
                <div className="relative h-56 overflow-hidden rounded-xl border border-[var(--border)] shadow-md">
                  <img
                    src="/images/hero-silkguild.webp"
                    alt="SILKGUILD — gamified learning, RPG-style concept art"
                    className="h-full w-full object-cover object-top"
                    loading="lazy"
                  />
                </div>
              </div>
            </TransitionLink>
          )}
        </div>

        {/* Icon rows — all offerings */}
        <div className="max-sm:*:not-last:border-b max-sm:*:not-last:pb-3 mt-12 grid gap-3 *:max-w-xs sm:grid-cols-2 md:mt-16 md:gap-y-6 lg:mt-24 lg:grid-cols-4 lg:gap-6">
          {services.map((svc) => (
            <TransitionLink key={svc.slug} href={`/services/${svc.slug}`} className="text-muted-foreground text-balance group block">
              <span className="text-foreground font-medium flex items-center gap-2">
                <span className="text-[var(--accent)]">{svc.icon}</span>
                {data(svc.slug)?.title ?? svc.labelKey}.
              </span>{" "}
              {data(svc.slug)?.tagline}
            </TransitionLink>
          ))}
        </div>

        <div className="mt-12 flex flex-col sm:flex-row items-center justify-center gap-3">
          <button
            type="button"
            onClick={openChat}
            className="inline-flex items-center gap-2 px-6 py-3 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[14px] hover:opacity-90 transition-all duration-150 btn-press tracking-[-0.01em] cursor-pointer"
          >
            {t("servicesCta")}
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
            </svg>
          </button>
          <TransitionLink
            href="/services"
            className="inline-flex items-center gap-2 px-6 py-3 border border-[var(--border)] text-[var(--muted)] rounded-[10px] font-medium text-[14px] hover:text-white hover:border-white/20 transition-all duration-150 btn-press tracking-[-0.01em]"
          >
            {t("servicesViewAll")}
          </TransitionLink>
        </div>
      </div>
    </section>
  );
}
