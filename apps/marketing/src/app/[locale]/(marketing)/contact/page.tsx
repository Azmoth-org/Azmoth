"use client";

import ContactChat from "@/components/ContactChat";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

const SILKDEV_LAT = 37.1549076;
const SILKDEV_LNG = 9.7937072;

export default function ContactPage() {
  const t = useTranslations("contact");
  const common = useTranslations("common");

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)]">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        {/* Header */}
        <div className="mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-6">
            <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
              {common("badgeContact")}
            </span>
          </div>
          <h1 className="text-[36px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            {t("pageTitle")}
          </h1>
          <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em]">
            {t("subtitle")}
          </p>
        </div>

        {/* Chat + Info grid */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8 lg:gap-12 mb-12">
          {/* Full assistant-ui chat form */}
          <div className="md:col-span-3">
            <ContactChat />
          </div>

          {/* Info sidebar */}
          <div className="md:col-span-2 flex flex-col gap-6">
            <div className="glass rounded-2xl p-8 space-y-6">
              <div>
                <h3 className="text-xs text-[var(--muted)] uppercase tracking-[0.05em] mb-2">
                  {t("emailLabel")}
                </h3>
                <a
                  href="mailto:contact@silkdev.com.tn"
                  className="text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors text-[15px] tracking-[-0.01em]"
                >
                  contact@silkdev.com.tn
                </a>
              </div>

              <div>
                <h3 className="text-xs text-[var(--muted)] uppercase tracking-[0.05em] mb-2">
                  {t("hours")}
                </h3>
                <p className="text-[var(--muted)] text-[15px] tracking-[-0.01em]">
                  {t("hoursValue")}
                </p>
              </div>

              <div>
                <h3 className="text-xs text-[var(--muted)] uppercase tracking-[0.05em] mb-2">
                  {t("socialMedia")}
                </h3>
                <div className="flex gap-4">
                  {["Fb.", "In.", "Ig."].map((social) => (
                    <a
                      key={social}
                      href="https://www.facebook.com/silkdevcorp"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[var(--muted)] hover:text-[var(--accent)] transition-colors text-[15px] tracking-[-0.01em]"
                    >
                      {social}
                    </a>
                  ))}
                </div>
              </div>
            </div>

            {/* Structured intake CTA */}
            <div
              className="rounded-2xl p-6 text-center"
              style={{
                background: "linear-gradient(135deg, rgba(108,99,255,0.08), transparent)",
                border: "1px solid rgba(108,99,255,0.15)",
              }}
            >
              <p className="text-[13px] text-[var(--muted)] mb-3 tracking-[-0.01em]">
                {t("intakeHint")}
              </p>
              <Link
                href="/intake"
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[13px] hover:opacity-90 transition-all duration-150 btn-press tracking-[-0.01em]"
              >
                {t("intakeCta")} →
              </Link>
            </div>
          </div>
        </div>

        {/* Google Maps */}
        <div className="glass rounded-2xl overflow-hidden">
          <div className="p-6 pb-0">
            <h3 className="text-[13px] text-[var(--muted)] uppercase tracking-[0.05em] font-medium mb-1">
              {t("address")}
            </h3>
            <p className="text-[15px] text-white tracking-[-0.01em] mb-4">
              {t("addressValue")}
            </p>
          </div>
          <div className="w-full h-[300px] md:h-[400px] relative">
            <iframe
              src={`https://maps.google.com/maps?q=${SILKDEV_LAT},${SILKDEV_LNG}&z=15&output=embed`}
              width="100%"
              height="100%"
              style={{ border: 0, filter: "invert(0.9) hue-rotate(180deg)" }}
              allowFullScreen
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              title="Silkdev office location"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
