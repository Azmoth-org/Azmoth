"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { TransitionLink } from "@/components/TransitionLink";
import { openChat } from "@/lib/openChat";

/**
 * Services showcase built on the dusk-landing-10 composition:
 * scrollspy service explorer (dusk-features-5) + how-we-work split
 * (content-2) + client logo row (integrations-1) + stats (stats-2)
 * + final CTA (call-to-action-2).
 *
 * The explorer shows ALL services stacked on the right; the left tab
 * rail is sticky and the active tab follows the section currently
 * crossing the center of the viewport (IntersectionObserver).
 */

const SLUGS = [
  "web-development",
  "ai-support-agents",
  "custom-ai-features",
  "knowledge-ai",
  "automation",
  "fractional-cto",
] as const;

const CLIENTS = [
  { name: "IPS", icon: "/images/ips-logo.svg" },
  { name: "Luca Pacioli", icon: "/images/lucapacioli.svg" },
  { name: "Wolves Gym", icon: "/images/wolves-gym.svg" },
  { name: "Creacom", icon: "/images/creacom-logo.png" },
  { name: "Trueveda", icon: "/images/trueveda-logo.png" },
  { name: "Podomus", icon: "/images/podomus.png" },
];

export default function LandingServices() {
  const t = useTranslations("services");
  const homeT = useTranslations("home");
  const [activeId, setActiveId] = useState<(typeof SLUGS)[number]>("web-development");
  const sectionRefs = useRef<Partial<Record<(typeof SLUGS)[number], HTMLDivElement | null>>>({});

  const offerings = t.raw("offerings") as Record<
    string,
    { title: string; tagline: string; outcome: string; items: string[] }
  >;

  // Scrollspy: the active tab follows the section crossing the viewport center
  useEffect(() => {
    const sections = SLUGS.map((slug) => sectionRefs.current[slug]).filter(
      (el): el is HTMLDivElement => el != null,
    );

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        const nextId = visible[0]?.target.getAttribute("data-slug") as
          | (typeof SLUGS)[number]
          | undefined;
        if (nextId) setActiveId(nextId);
      },
      // The band around the viewport center: a section is "active" while it
      // crosses the middle ~30% of the screen.
      { rootMargin: "-25% 0px -55% 0px", threshold: [0.15, 0.35, 0.55, 0.75] },
    );

    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  const scrollToSection = (slug: (typeof SLUGS)[number]) => {
    sectionRefs.current[slug]?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveId(slug);
  };

  return (
    <>
      {/* ─── Service explorer (dusk-features-5 scrollspy) ─── */}
      <section className="dusk py-16 md:py-20">
        <div className="mx-auto max-w-7xl">
          <h2 className="text-muted-foreground max-w-4xl text-balance text-4xl font-medium tracking-tight">
            <span className="text-foreground">{t("explorerTitle")}</span>
          </h2>

          <div className="mt-16 grid gap-6 md:mt-24 lg:grid-cols-[auto_1fr] lg:gap-12">
            {/* Sticky tab rail — active follows the centered section */}
            <div className="lg:sticky lg:top-24 lg:h-fit lg:w-56">
              <ul className="flex gap-2 overflow-x-auto pb-2 max-lg:flex-wrap lg:flex-col lg:gap-1 lg:overflow-visible lg:pb-0">
                {SLUGS.map((slug) => {
                  const o = offerings[slug];
                  const isActive = slug === activeId;
                  return (
                    <li key={slug} className="shrink-0">
                      <button
                        type="button"
                        onClick={() => scrollToSection(slug)}
                        aria-current={isActive ? "true" : undefined}
                        className={`flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-3.5 py-2.5 text-left text-sm duration-150 ${
                          isActive
                            ? "bg-foreground/10 font-medium text-foreground"
                            : "text-muted-foreground hover:bg-foreground/5 hover:text-accent-foreground"
                        }`}
                      >
                        <span
                          className={`h-1.5 w-1.5 shrink-0 rounded-full transition-colors ${
                            isActive ? "bg-[var(--accent)]" : "bg-foreground/25"
                          }`}
                        />
                        <span className="whitespace-nowrap">{o?.title ?? slug}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>

            {/* All services stacked */}
            <div className="min-w-0 space-y-8">
              {SLUGS.map((slug) => {
                const s = offerings[slug];
                if (!s) return null;
                return (
                  <div
                    key={slug}
                    ref={(el) => {
                      sectionRefs.current[slug] = el;
                    }}
                    data-slug={slug}
                    className="scroll-mt-28 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-8 md:p-10"
                  >
                    <p className="text-muted-foreground max-w-xl text-balance text-lg font-medium">
                      <span className="text-foreground">{s.title}.</span> {s.tagline}
                    </p>
                    <p className="text-muted-foreground mt-4 max-w-2xl text-balance text-[15px] leading-relaxed">
                      {s.outcome}
                    </p>

                    <ul className="text-muted-foreground mt-7 grid gap-x-10 gap-y-2 sm:grid-cols-2">
                      {(s.items ?? []).slice(0, 6).map((item) => (
                        <li key={item} className="flex items-center gap-2.5 py-1.5">
                          <Check className="size-4 shrink-0 text-[var(--accent)]" />
                          <span className="text-sm">{item}</span>
                        </li>
                      ))}
                    </ul>

                    <div className="mt-7 flex flex-wrap items-center gap-3">
                      <TransitionLink
                        href={`/services/${slug}`}
                        className="inline-flex items-center gap-2 rounded-full bg-[var(--accent)] px-5 py-2.5 text-sm font-medium text-white duration-150 hover:opacity-90"
                      >
                        {t("learnMore")}
                        <ArrowRight className="size-4" />
                      </TransitionLink>
                      <button
                        type="button"
                        onClick={openChat}
                        className="inline-flex cursor-pointer items-center gap-2 rounded-full bg-foreground/5 px-5 py-2.5 text-sm font-medium text-foreground ring-1 ring-foreground/10 duration-150 hover:bg-foreground/10"
                      >
                        {t("startService")}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ─── How we work (dusk-content-2) ─── */}
      <section className="dusk py-16 md:py-20">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-4 md:grid-cols-2 md:gap-6 lg:gap-12">
            <h2 className="text-balance text-4xl font-medium tracking-tight text-foreground lg:text-5xl">
              {t("howTitle")}.
            </h2>
            <div className="grid gap-4 pt-6 sm:grid-cols-2">
              <p className="text-muted-foreground text-balance text-lg">
                <span className="font-medium text-foreground">{t("howFast")}</span> {t("howFastBody")}
              </p>
              <p className="text-muted-foreground text-balance text-lg">
                <span className="font-medium text-foreground">{t("howProven")}</span> {t("howProvenBody")}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Client logos (dusk-integrations-1, real clients) ─── */}
      <section className="dusk py-16 md:py-20">
        <div className="mx-auto max-w-7xl">
          <p className="text-muted-foreground text-center text-sm tracking-[0.15em] uppercase">
            {t("clientsTitle")}
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-x-12 gap-y-8">
            {CLIENTS.map((c) => (
              <img
                key={c.name}
                src={c.icon}
                alt={c.name}
                className="h-9 w-auto max-w-40 object-contain opacity-60 grayscale"
              />
            ))}
          </div>
        </div>
      </section>

      {/* ─── Stats (dusk-stats-2, real numbers) ─── */}
      <section className="dusk py-16 md:py-20">
        <div className="mx-auto max-w-7xl">
          <p className="text-muted-foreground max-w-4xl text-balance text-4xl font-medium tracking-tight lg:text-5xl">
            <span className="text-foreground">{homeT("statsHead1")}</span> {homeT("statsHead2")}
          </p>
          <div className="mt-16 grid gap-12 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-3 border-t pt-6">
              <div className="text-5xl font-semibold tracking-tight text-foreground">4+</div>
              <p className="text-muted-foreground">{homeT("metric1")}</p>
            </div>
            <div className="space-y-3 border-t pt-6">
              <div className="text-5xl font-semibold tracking-tight text-foreground">4</div>
              <p className="text-muted-foreground">{homeT("metric3")}</p>
            </div>
            <div className="space-y-3 border-t pt-6">
              <div className="text-5xl font-semibold tracking-tight text-foreground">6+</div>
              <p className="text-muted-foreground">{homeT("metric2")}</p>
            </div>
            <div className="space-y-3 border-t pt-6">
              <div className="text-5xl font-semibold tracking-tight text-foreground">5.0</div>
              <p className="text-muted-foreground">{homeT("ratedGoogle")}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Final CTA (dusk-call-to-action-2) ─── */}
      <section className="dusk py-16 md:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="flex items-center justify-center gap-6 max-lg:flex-col max-lg:text-center lg:items-end lg:justify-between">
            <h2 className="max-w-4xl text-balance text-5xl font-semibold tracking-tight text-foreground xl:text-6xl">
              {t("cta2Title")}
            </h2>
            <button
              type="button"
              onClick={openChat}
              className="inline-flex shrink-0 cursor-pointer items-center gap-2 rounded-full bg-[var(--accent)] px-8 py-4 text-[15px] font-medium text-white duration-150 hover:opacity-90 btn-press"
            >
              {t("startService")}
              <ArrowRight className="size-4" />
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
