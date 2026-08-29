"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { TransitionLink } from "@/components/TransitionLink";
import { openChat } from "@/lib/openChat";
import { InfiniteSlider } from "@/components/ui/motion-primitives/infinite-slider";

/**
 * Dusk-style hero (Tailark dusk-hero-section-10) adapted to SILKDEV:
 * two-column headline + stacked-card visual, product slider instead of
 * third-party logos, CTAs open the chat modal. Uses the site's tokens.
 */
export default function Hero10() {
  const t = useTranslations("home");

  // Client brands — the agency's work, not our own products (those live
  // in the products section with their icons).
  const clients = [
    { name: t("clientIps"), icon: "/images/ips-logo.svg" },
    { name: t("clientLuca"), icon: "/images/lucapacioli.svg" },
    { name: t("clientWolves"), icon: "/images/wolves-gym.svg" },
    { name: t("clientCreacom"), icon: "/images/creacom-logo.png" },
    { name: t("clientTrueveda"), icon: "/images/trueveda-logo.png" },
    { name: t("clientPodomus"), icon: "/images/podomus.png" },
  ];

  return (
    <>
      <div className="mx-auto max-w-7xl px-6 pt-24 md:pt-32">
        <div className="grid items-center gap-10 md:grid-cols-2 md:gap-12">
          {/* Left — messaging */}
          <div className="text-left">
            <div className="mb-6 inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/60 backdrop-blur-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse" />
              <span className="text-[11px] md:text-[12px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
                {t("heroBadge")}
              </span>
            </div>

            <h1 className="text-balance text-4xl font-medium tracking-tight text-white md:text-5xl xl:text-6xl">
              {t("hero10Title")}
            </h1>

            <div className="mt-6 flex max-w-md flex-col gap-6">
              <p className="text-balance text-lg leading-relaxed text-[var(--muted)]">
                {t("hero10Sub")}
              </p>

              <div className="flex flex-col sm:flex-row items-start gap-3">
                <button
                  type="button"
                  onClick={openChat}
                  className="inline-flex items-center gap-2 px-7 py-3 bg-[var(--accent)] text-white rounded-full font-medium text-[14px] hover:opacity-90 transition-all duration-150 btn-press tracking-[-0.01em]"
                >
                  {t("servicesCta")}
                </button>
                <TransitionLink
                  href="/services"
                  className="inline-flex items-center gap-2 px-7 py-3 border border-[var(--border)] text-white rounded-full font-medium text-[14px] hover:bg-white/5 transition-colors duration-150 btn-press tracking-[-0.01em]"
                >
                  {t("ctaServices")}
                </TransitionLink>
              </div>
            </div>
          </div>

          {/* Right — stacked product cards: SILKLEARN · SILKLABS · Meridian */}
          <div className="relative mt-16 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 pt-6 md:px-6 lg:px-8 lg:pt-16">
            <div className="relative z-10 mx-auto flex max-w-5xl -space-x-14 sm:aspect-video lg:-space-x-24">
              {/* Back left — SILKLABS */}
              <div className="w-1/2 pt-10 lg:pt-16">
                <div className="h-full overflow-hidden rounded-t-2xl border border-[var(--border)] bg-[var(--background)] shadow-lg shadow-black/20">
                  <img
                    src="/images/hero-silklabs.webp"
                    alt="SILKLABS — find your team and build something great"
                    className="h-full w-full object-cover object-top"
                    loading="lazy"
                  />
                </div>
              </div>
              {/* Front center — SILKLEARN */}
              <div className="relative z-10 w-2/3 -mt-6 lg:-mt-10">
                <div className="h-full overflow-hidden rounded-t-2xl border border-[var(--border)] bg-[var(--background)] shadow-xl shadow-black/30">
                  <img
                    src="/images/hero-silklearn.webp"
                    alt="SILKLEARN — your documents become a knowledge graph"
                    className="h-full w-full object-cover object-top"
                  />
                </div>
              </div>
              {/* Back right — Meridian */}
              <div className="w-1/2 pt-10 lg:pt-16">
                <div className="h-full overflow-hidden rounded-t-2xl border border-[var(--border)] bg-[var(--background)] shadow-lg shadow-black/20">
                  <img
                    src="/images/hero-meridian.webp"
                    alt="Meridian — the client portal that runs the engagement"
                    className="h-full w-full object-cover object-top"
                    loading="lazy"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Client brands carousel */}
      <div className="relative mt-14">
        <InfiniteSlider gap={40} className="mask-x-from-85% mask-x-to-99% py-6">
          {[...clients, ...clients].map((c, i) => (
            <div
              key={`${c.name}-${i}`}
              className="flex h-12 w-36 items-center justify-center"
            >
              <img
                src={c.icon}
                alt={c.name}
                className="max-h-full max-w-full object-contain opacity-70 grayscale"
              />
            </div>
          ))}
        </InfiniteSlider>
      </div>
    </>
  );
}
