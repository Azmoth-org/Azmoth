"use client";

import { openChat } from "@/lib/openChat";
import { notFound, useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { BookOpen, MessageSquare, Sparkles, Workflow } from "lucide-react";
import { Link } from "@/i18n/navigation";

const VALID_SLUGS = [
  "web-development",
  "ai-support-agents",
  "custom-ai-features",
  "knowledge-ai",
  "automation",
  "fractional-cto",
] as const;

type ServiceSlug = (typeof VALID_SLUGS)[number];

interface ServiceData {
  title: string;
  tagline: string;
  outcome: string;
  items: string[];
  processTitle: string;
  processSteps: Array<{ title: string; description: string }>;
  trustMetrics: Array<{ value: string; label: string }>;
  caseStudies: Array<{ company: string; before: string; after: string; metric: string }>;
  comparison: Array<{ feature: string; us: string; them: string }>;
  quote: { note: string };
  faq: Array<{ q: string; a: string }>;
}

const META: Record<
  ServiceSlug,
  {
    accent: string;
    gradient: string;
    icon: React.ReactNode;
    reviews: Array<{ name: string; text: string; rating: number }>;
    ctaLabelKey: string;
  }
> = {
  "web-development": {
    accent: "#6c63ff",
    gradient: "linear-gradient(135deg, #6c63ff, #5a52e0)",
    ctaLabelKey: "ctaWeb",
    icon: (
      <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
      </svg>
    ),
    reviews: [
      { name: "Ahmed B.", text: "reviewWeb1", rating: 5 },
      { name: "Sarra M.", text: "reviewWeb2", rating: 5 },
      { name: "Karim J.", text: "reviewWeb3", rating: 5 },
    ],
  },
  "fractional-cto": {
    accent: "#66e3ff",
    gradient: "linear-gradient(135deg, #00d9ff, #00a8cc)",
    ctaLabelKey: "ctaCto",
    icon: (
      <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
      </svg>
    ),
    reviews: [
      { name: "Mohamed A.", text: "reviewCto1", rating: 5 },
      { name: "Yassine K.", text: "reviewCto2", rating: 5 },
    ],
  },
  "ai-support-agents": {
    accent: "#66e3ff",
    gradient: "linear-gradient(135deg, #00d9ff, #00a8cc)",
    ctaLabelKey: "ctaSupport",
    icon: <MessageSquare className="w-8 h-8" />,
    reviews: [],
  },
  "custom-ai-features": {
    accent: "#f59e0b",
    gradient: "linear-gradient(135deg, #f59e0b, #d97706)",
    ctaLabelKey: "ctaFeatures",
    icon: <Sparkles className="w-8 h-8" />,
    reviews: [],
  },
  "knowledge-ai": {
    accent: "#ec4899",
    gradient: "linear-gradient(135deg, #ec4899, #db2777)",
    ctaLabelKey: "ctaKnowledge",
    icon: <BookOpen className="w-8 h-8" />,
    reviews: [],
  },
  "automation": {
    accent: "#22c55e",
    gradient: "linear-gradient(135deg, #22c55e, #16a34a)",
    ctaLabelKey: "ctaAutomation",
    icon: <Workflow className="w-8 h-8" />,
    reviews: [],
  },
};

export default function ServiceDetailPage() {
  const params = useParams();
  const slug = params.slug as string;

  if (!VALID_SLUGS.includes(slug as ServiceSlug)) {
    notFound();
  }

  const t = useTranslations("services");
  const common = useTranslations("common");
  const offerings = t.raw("offerings") as Record<string, ServiceData>;
  const s = offerings[slug] as ServiceData;
  const reviewsContent = t.raw("reviewsContent") as Record<string, string>;
  const meta = META[slug as ServiceSlug];

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)]">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-[var(--muted)] mb-8 tracking-[-0.01em]">
          <Link href="/services" className="hover:text-white transition-colors duration-150">
            {common("badgeServices")}
          </Link>
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span>{s.title}</span>
        </div>

        {/* Hero section */}
        <div
          className="rounded-3xl p-8 md:p-12 mb-16 relative overflow-hidden"
          style={{
            background: `linear-gradient(135deg, ${meta.accent}15, transparent)`,
            border: `1px solid ${meta.accent}22`,
          }}
        >
          <div
            className="absolute -top-40 -right-40 w-80 h-80 rounded-full opacity-10 pointer-events-none"
            style={{ background: meta.gradient }}
          />
          <div className="relative z-10">
            <div
              className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border mb-6"
              style={{ borderColor: `${meta.accent}33`, background: `${meta.accent}10` }}
            >
              <div style={{ color: meta.accent }}>{meta.icon}</div>
              <span className="text-[13px] font-medium tracking-[0.05em] uppercase" style={{ color: meta.accent }}>
                {s.tagline}
              </span>
            </div>
            <h1 className="text-[36px] md:text-[44px] font-bold tracking-[-0.03em] leading-[1.1] text-white mb-6 font-['Manrope',system-ui,sans-serif]">
              {s.title}
            </h1>
            <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em] max-w-2xl leading-[1.7]">
              {s.outcome}
            </p>
          </div>
        </div>

        {/* Trust metrics strip */}
        {s.trustMetrics && s.trustMetrics.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-16">
            {s.trustMetrics.map((m, i) => (
              <div key={i} className="glass rounded-xl p-6 text-center">
                <div className="text-[28px] md:text-[32px] font-bold tracking-[-0.02em] font-['Manrope',system-ui,sans-serif]" style={{ color: meta.accent }}>
                  {m.value}
                </div>
                <div className="text-[13px] text-[var(--muted)] mt-1 tracking-[-0.01em]">{m.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* What's included section */}
        <div className="mb-16">
          <h2 className="text-[28px] font-bold tracking-[-0.03em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            {t("whatsIncluded")}
          </h2>
          <p className="text-[15px] text-[var(--muted)] mb-8 max-w-xl tracking-[-0.01em]">
            {t("whatsIncludedSub")}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {s.items.map((item, i) => (
              <div key={i} className="flex items-start gap-3 glass rounded-xl p-5">
                <div className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5" style={{ background: `${meta.accent}20` }}>
                  <svg className="w-3.5 h-3.5" style={{ color: meta.accent }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <span className="text-[15px] text-[var(--muted)] leading-[1.6] tracking-[-0.01em]">{item}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Process section */}
        <div className="mb-16">
          <h2 className="text-[28px] font-bold tracking-[-0.03em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            {s.processTitle}
          </h2>
          <p className="text-[15px] text-[var(--muted)] mb-8 max-w-xl tracking-[-0.01em]">
            {t("processSub")}
          </p>
          <div className="space-y-6">
            {s.processSteps.map((step, i) => (
              <div key={i} className="glass rounded-xl p-6 relative pl-14">
                <div className="absolute left-4 top-6 w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold" style={{ background: `${meta.accent}20`, color: meta.accent }}>
                  {i + 1}
                </div>
                <h3 className="text-[18px] font-bold tracking-[-0.02em] text-white mb-2 font-['Manrope',system-ui,sans-serif]">
                  {step.title}
                </h3>
                <p className="text-[14px] text-[var(--muted)] leading-[1.7] tracking-[-0.01em]">{step.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Case studies section */}
        {s.caseStudies && s.caseStudies.length > 0 && (
          <div className="mb-16">
            <h2 className="text-[28px] font-bold tracking-[-0.03em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
              {t("caseStudiesTitle")}
            </h2>
            <p className="text-[15px] text-[var(--muted)] mb-8 max-w-xl tracking-[-0.01em]">
              {t("caseStudiesSub")}
            </p>
            <div className="space-y-6">
              {s.caseStudies.map((cs, i) => (
                <div key={i} className="glass rounded-xl p-6 md:p-8">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold" style={{ background: `${meta.accent}20`, color: meta.accent }}>
                      {i + 1}
                    </div>
                    <h3 className="text-[18px] font-bold tracking-[-0.02em] text-white font-['Manrope',system-ui,sans-serif]">{cs.company}</h3>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="glass rounded-lg p-4">
                      <div className="text-[11px] uppercase tracking-[0.1em] text-[var(--muted)] mb-1">{t("beforeLabel")}</div>
                      <div className="text-[14px] text-white/70 leading-[1.5]">{cs.before}</div>
                    </div>
                    <div className="flex items-center justify-center">
                      <svg className="w-6 h-6" style={{ color: meta.accent }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                      </svg>
                    </div>
                    <div className="glass rounded-lg p-4" style={{ borderColor: `${meta.accent}33` }}>
                      <div className="text-[11px] uppercase tracking-[0.1em]" style={{ color: meta.accent }}>{t("afterLabel")}</div>
                      <div className="text-[14px] text-white leading-[1.5]">{cs.after}</div>
                    </div>
                  </div>
                  <div className="mt-4 text-center">
                    <span className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-medium" style={{ background: `${meta.accent}15`, color: meta.accent }}>
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                      </svg>
                      {cs.metric}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Comparison table */}
        {s.comparison && s.comparison.length > 0 && (
          <div className="mb-16">
            <h2 className="text-[28px] font-bold tracking-[-0.03em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
              {t("comparisonTitle")}
            </h2>
            <p className="text-[15px] text-[var(--muted)] mb-8 max-w-xl tracking-[-0.01em]">
              {t("comparisonSub")}
            </p>
            <div className="glass rounded-2xl overflow-x-auto">
              <table className="w-full text-sm min-w-[560px]">
                <thead>
                  <tr style={{ background: `${meta.accent}08` }}>
                    <th className="text-left p-4 font-medium text-white tracking-[-0.01em]">{t("comparisonFeature")}</th>
                    <th className="text-left p-4 font-medium tracking-[-0.01em]" style={{ color: meta.accent }}>{t("comparisonUs")}</th>
                    <th className="text-left p-4 font-medium text-[var(--muted)] tracking-[-0.01em]">{t("comparisonThem")}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.comparison.map((row, i) => (
                    <tr key={i} className="border-t border-[var(--border)]">
                      <td className="p-4 text-white/80 tracking-[-0.01em] font-medium">{row.feature}</td>
                      <td className="p-4 tracking-[-0.01em]" style={{ color: meta.accent }}>{row.us}</td>
                      <td className="p-4 text-[var(--muted)] tracking-[-0.01em]">{row.them}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Quote section — no published prices; every project is scoped individually */}
        {s.quote && (
          <div className="mb-16">
            <h2 className="text-[28px] font-bold tracking-[-0.03em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
              {t("quoteTitle")}
            </h2>
            <p className="text-[15px] text-[var(--muted)] mb-8 max-w-xl tracking-[-0.01em]">
              {s.quote.note}
            </p>
            <div className="glass rounded-2xl p-8 md:p-10 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-40 h-40 rounded-bl-full opacity-5 pointer-events-none" style={{ background: meta.gradient }} />
              <div className="relative z-10 flex flex-col md:flex-row md:items-center gap-6 md:gap-12">
                <div className="flex-1">
                  <p className="text-[16px] text-white leading-[1.6] tracking-[-0.01em]">
                    {t("quoteBody")}
                  </p>
                </div>
                <Link
                  href="/contact"
                  onClick={(e: React.MouseEvent) => { e.preventDefault(); openChat(); }}
                  className="inline-flex items-center gap-2 px-6 py-3 text-white rounded-[10px] font-medium text-[15px] hover:opacity-90 transition-all duration-150 btn-press whitespace-nowrap"
                  style={{ background: meta.gradient }}
                >
                  {t("getQuote")}
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                  </svg>
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* FAQ section — expanded */}
        {s.faq && s.faq.length > 0 && (
          <div className="mb-16">
            <h2 className="text-[28px] font-bold tracking-[-0.03em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
              {t("faqTitle")}
            </h2>
            <p className="text-[15px] text-[var(--muted)] mb-8 max-w-xl tracking-[-0.01em]">
              {t("faqSub")}
            </p>
            <div className="space-y-4">
              {s.faq.map((item, i) => (
                <details key={i} className="glass rounded-xl group">
                  <summary className="flex items-center justify-between p-5 cursor-pointer text-[16px] font-medium tracking-[-0.01em] text-white hover:text-[var(--accent)] transition-colors duration-150 font-['Manrope',system-ui,sans-serif]">
                    {item.q}
                    <svg className="w-4 h-4 text-[var(--muted)] group-open:rotate-180 transition-transform duration-200 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </summary>
                  <div className="px-5 pb-5 text-[14px] text-[var(--muted)] leading-[1.7] tracking-[-0.01em]" dangerouslySetInnerHTML={{ __html: item.a }} />
                </details>
              ))}
            </div>
          </div>
        )}

        {/* Reviews section */}
        {meta.reviews.length > 0 && (
        <div className="mb-16">
          <h2 className="text-[28px] font-bold tracking-[-0.03em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            {t("reviewsTitle")}
          </h2>
          <p className="text-[15px] text-[var(--muted)] mb-8 max-w-xl tracking-[-0.01em]">
            {t("reviewsSub")}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {meta.reviews.map((review, i) => (
              <div key={i} className="glass rounded-xl p-6">
                <div className="flex items-center gap-1 mb-3">
                  {Array.from({ length: 5 }).map((_, j) => (
                    <svg key={j} className="w-4 h-4" fill={j < review.rating ? meta.accent : "none"} stroke={meta.accent} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
                    </svg>
                  ))}
                </div>
                <p className="text-[14px] text-[var(--muted)] leading-[1.7] tracking-[-0.01em] mb-3 italic">
                  &ldquo;{reviewsContent[review.text]}&rdquo;
                </p>
                <p className="text-[13px] font-medium tracking-[-0.01em]" style={{ color: meta.accent }}>
                  — {review.name}
                </p>
              </div>
            ))}
          </div>
        </div>
        )}

        {/* CTA */}
        <div
          className="rounded-2xl p-10 md:p-14 text-center relative overflow-hidden"
          style={{
            background: `linear-gradient(135deg, ${meta.accent}12, transparent)`,
            border: `1px solid ${meta.accent}22`,
          }}
        >
          <div className="absolute -bottom-20 -left-20 w-60 h-60 rounded-full opacity-5 pointer-events-none" style={{ background: meta.gradient }} />
          <div className="relative z-10">
            <h2 className="text-[28px] md:text-[32px] font-bold tracking-[-0.02em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
              {t(`ctaService.${meta.ctaLabelKey}.title`)}
            </h2>
            <p className="text-[var(--muted)] text-[16px] mb-8 max-w-lg mx-auto tracking-[-0.01em]">
              {t(`ctaService.${meta.ctaLabelKey}.body`)}
            </p>
            <Link
              href="/contact"
              onClick={(e: React.MouseEvent) => { e.preventDefault(); openChat(); }}
              className="inline-flex items-center px-8 py-3 text-white rounded-[10px] font-medium text-[15px] hover:opacity-90 transition-all duration-150 btn-press"
              style={{ background: meta.gradient }}
            >
              {t(`ctaService.${meta.ctaLabelKey}.button`)}
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
