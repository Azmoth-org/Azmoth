"use client";

import { openChat } from "@/lib/openChat";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

export default function AboutPage() {
  const t = useTranslations("about");
  const common = useTranslations("common");

  const sections = t.raw("sections") as Array<{ title: string; body: string }>;

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)]">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        <div className="max-w-3xl">
        {/* Header */}
        <div className="mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-6">
            <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
              {common("badgeAbout")}
            </span>
          </div>
          <h1 className="text-[36px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            {t("pageTitle")}
          </h1>
          <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em]">
            {t("subtitle")}
          </p>
        </div>

        {/* Sections */}
        <div className="space-y-12">
          {sections.map((section, i) => (
            <div key={i} className={i > 0 ? "pt-12 border-t border-[var(--border)]" : ""}>
              <h2 className="text-[22px] font-bold tracking-[-0.02em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
                {section.title}
              </h2>
              <p className="text-[var(--muted)] text-[15px] leading-[1.8] tracking-[-0.01em]">
                {section.body}
              </p>
            </div>
          ))}
        </div>

        {/* CTA */}
        <div className="mt-16">
          <Link
            href="/contact" onClick={(e: React.MouseEvent) => { e.preventDefault(); openChat(); }}
            className="inline-flex items-center px-6 py-3 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[15px] hover:bg-[var(--accent-hover)] transition-colors duration-150 btn-press"
          >
            {t("ctaButton")}
          </Link>
        </div>
        </div>
      </div>
    </div>
  );
}
