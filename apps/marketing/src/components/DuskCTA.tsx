"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { TransitionLink } from "@/components/TransitionLink";
import { openChat } from "@/lib/openChat";

/** Tailark dusk-call-to-action-1 adapted: the final conversion CTA. */
export default function DuskCTA() {
  const t = useTranslations("home");

  return (
    <section className="dusk py-16 md:py-20">
      <div className="mx-auto max-w-7xl">
        <div className="mx-auto max-w-4xl text-center">
          <h2 className="text-balance text-4xl font-semibold tracking-tight text-foreground lg:text-5xl xl:text-6xl">
            {t("ctaTitle")}
          </h2>
          <p className="text-muted-foreground mt-4 text-balance text-lg">{t("ctaBody")}</p>

          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <button
              type="button"
              onClick={openChat}
              className="inline-flex items-center gap-2 px-8 py-3.5 bg-[var(--accent)] text-white rounded-full font-medium text-[15px] hover:opacity-90 transition-all duration-150 btn-press tracking-[-0.01em] cursor-pointer"
            >
              {t("ctaAction")}
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </button>
            <TransitionLink
              href="/services"
              className="inline-flex items-center gap-2 px-8 py-3.5 border border-[var(--border)] text-white rounded-full font-medium text-[15px] hover:bg-white/5 transition-colors duration-150 btn-press tracking-[-0.01em]"
            >
              {t("servicesViewAll")}
            </TransitionLink>
          </div>
        </div>
      </div>
    </section>
  );
}
