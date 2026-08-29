"use client";

import { openChat } from "@/lib/openChat";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import LandingServices from "@/components/LandingServices";
import CaptureForm from "@/components/CaptureForm";



export default function ServicesPage() {
  const t = useTranslations("services");
  const common = useTranslations("common");

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)]">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        {/* Header */}
        <div className="max-w-3xl mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-6">
            <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
              {common("badgeServices")}
            </span>
          </div>
          <h1 className="text-[36px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            {t("heroTitle")}
          </h1>
          <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em]">
            {t("heroSubtitle")}
          </p>
        </div>

        {/* Service cards */}
        <LandingServices />

        {/* One-field lead capture */}
        <div className="mt-20 max-w-3xl">
          <CaptureForm />
        </div>
      </div>
    </div>
  );
}
