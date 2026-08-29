"use client";

import { useLocale } from "next-intl";
import { legalContent, type LegalPage as LegalPageData } from "@/data/legal";

export default function LegalPage({ page }: { page: "terms" | "privacy" }) {
  const locale = useLocale() as "en" | "fr";
  const content: LegalPageData = legalContent[locale][page];

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)]">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        <div className="max-w-3xl mx-auto">
          {/* Header */}
          <div className="mb-12">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-6">
              <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
                SILKDEV · Legal
              </span>
            </div>
            <h1 className="text-[36px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
              {content.title}
            </h1>
            <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em] leading-[1.6]">
              {content.intro}
            </p>
            <p className="mt-4 text-[12px] text-[var(--muted)]/60 tracking-[-0.01em]">
              {content.updated}
            </p>
          </div>

          {/* Sections */}
          <div className="space-y-8">
            {content.sections.map((section) => (
              <section key={section.title}>
                <h2 className="text-[20px] md:text-[22px] font-bold tracking-[-0.02em] text-white mb-3 font-['Manrope',system-ui,sans-serif]">
                  {section.title}
                </h2>
                {section.body.map((paragraph, i) => (
                  <p
                    key={i}
                    className="text-[15px] text-[var(--muted)] leading-[1.7] tracking-[-0.01em] mb-3"
                  >
                    {paragraph}
                  </p>
                ))}
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
