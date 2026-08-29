"use client";

import { Suspense, useMemo } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useSearchParams } from "next/navigation";

const STEPS = ["confirmStep1", "confirmStep2", "confirmStep3", "confirmStep4", "confirmStep5"] as const;
const COMPLETED = 1; // First step is always done after submission

export default function IntakeConfirmationPage() {
  return (
    <Suspense fallback={null}>
      <ConfirmationContent />
    </Suspense>
  );
}

function ConfirmationContent() {
  const t = useTranslations("intake");
  const common = useTranslations("common");
  const searchParams = useSearchParams();
  const ref = searchParams.get("ref") || "SKD-????";

  const submittedData = useMemo(() => {
    if (typeof window === "undefined") return null;
    const stored = JSON.parse(localStorage.getItem("silkdev_intakes") || "[]");
    return stored.find((s: { ref: string }) => s.ref === ref) || null;
  }, [ref]);

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)] min-h-screen">
      <div className="max-w-3xl mx-auto px-6 md:px-[40px]">
        {/* Header */}
        <div className="mb-12 text-center">
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6"
            style={{ background: "rgba(108,99,255,0.15)" }}
          >
            <svg className="w-8 h-8 text-[var(--accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-[32px] md:text-[38px] font-bold tracking-[-0.03em] text-white mb-3 font-['Manrope',system-ui,sans-serif]">
            {t("confirmTitle")}
          </h1>
          <p className="text-[16px] text-[var(--muted)] max-w-md mx-auto tracking-[-0.01em]">
            {t("confirmBody")}
          </p>
        </div>

        {/* Reference code */}
        <div className="glass rounded-2xl p-6 text-center mb-8">
          <p className="text-[12px] text-[var(--muted)] uppercase tracking-[0.05em] mb-2 font-medium">
            {t("confirmRef")}
          </p>
          <p className="text-[24px] font-bold text-white tracking-[-0.02em] font-['Manrope',system-ui,sans-serif]">
            {ref}
          </p>
        </div>

        {/* Email confirmation */}
        {submittedData?.email && (
          <p className="text-[14px] text-[var(--muted)] text-center mb-10 tracking-[-0.01em]">
            {t("confirmEmail")}{" "}
            <span className="text-white font-medium">{submittedData.email}</span>
          </p>
        )}

        {/* Progress dashboard */}
        <div className="glass rounded-3xl p-8 mb-10">
          <h2 className="text-[18px] font-bold text-white mb-6 tracking-[-0.02em] font-['Manrope',system-ui,sans-serif]">
            {t("confirmProgress")}
          </h2>

          <div className="space-y-4">
            {STEPS.map((key, i) => {
              const isDone = i < COMPLETED;
              const isCurrent = i === COMPLETED;
              return (
                <div key={key} className="flex items-center gap-4">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300 ${
                      isDone
                        ? "bg-[var(--accent)] text-white"
                        : isCurrent
                        ? "bg-[var(--accent)]/20 text-[var(--accent)] border border-[var(--accent)]/40"
                        : "bg-[var(--surface)] text-[var(--muted)] border border-[var(--border)]"
                    }`}
                  >
                    {isDone ? (
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      <span className="text-[12px] font-bold">{i + 1}</span>
                    )}
                  </div>
                  <span
                    className={`text-[15px] tracking-[-0.01em] ${
                      isDone ? "text-white font-medium" : "text-[var(--muted)]"
                    }`}
                  >
                    {t(key)}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Progress bar */}
          <div className="mt-8">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[12px] text-[var(--muted)] tracking-[-0.01em]">
                {Math.round((COMPLETED / STEPS.length) * 100)}%
              </span>
              <span className="text-[12px] text-[var(--muted)] tracking-[-0.01em]">
                {COMPLETED}/{STEPS.length}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-[var(--surface)] overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${(COMPLETED / STEPS.length) * 100}%`,
                  background: "linear-gradient(90deg, var(--accent), var(--accent-hover))",
                }}
              />
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link
            href="/"
            className="px-6 py-3 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[14px] hover:opacity-90 transition-all duration-150 btn-press tracking-[-0.01em]"
          >
            {common("home")}
          </Link>
          <Link
            href="/services"
            className="px-6 py-3 border border-[var(--border)] text-[var(--muted)] rounded-[10px] font-medium text-[14px] hover:text-white hover:border-white/20 transition-all duration-150 btn-press tracking-[-0.01em]"
          >
            {common("badgeServices")}
          </Link>
        </div>
      </div>
    </div>
  );
}
