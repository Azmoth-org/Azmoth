"use client";

import { openChat } from "@/lib/openChat";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

export default function FaqPage() {
  const t = useTranslations("faq");
  const common = useTranslations("common");

  const items = t.raw("items") as Array<{ q: string; a: string }>;

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)]">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        {/* Header */}
        <div className="max-w-3xl mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-6">
            <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
              {common("badgeFaq")}
            </span>
          </div>
          <h1 className="text-[36px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            {t("pageTitle")}
          </h1>
          <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em]">
            {t("subtitle")}
          </p>
        </div>

        {/* FAQ items — dusk-faqs-1 split layout with shadcn accordion */}
        <div className="dusk grid gap-12 md:grid-cols-2 md:gap-6">
          <h2 className="text-foreground max-w-sm text-balance text-4xl font-medium tracking-tight">
            {t("duskTitle")}
          </h2>
          <div>
            <Accordion type="single" collapsible className="w-full">
              {items.map((item, i) => (
                <AccordionItem key={i} value={`item-${i}`} className="border-dashed">
                  <AccordionTrigger className="cursor-pointer text-base hover:no-underline">
                    {item.q}
                  </AccordionTrigger>
                  <AccordionContent>
                    <div
                      className="prose-custom text-muted-foreground text-base"
                      dangerouslySetInnerHTML={{ __html: item.a }}
                    />
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>

            <p className="text-muted-foreground mt-6">
              {t("ctaBody")}{" "}
              <button
                type="button"
                onClick={openChat}
                className="text-[var(--accent)] font-medium hover:underline cursor-pointer"
              >
                {t("ctaButton")}
              </button>
            </p>
          </div>
        </div>

        {/* CTA */}
        <div className="mt-16 text-center">
          <h2 className="text-[24px] font-bold tracking-[-0.02em] text-white mb-3 font-['Manrope',system-ui,sans-serif]">
            {t("ctaTitle")}
          </h2>
          <p className="text-[var(--muted)] mb-6 text-[15px] tracking-[-0.01em]">
            {t("ctaBody")}
          </p>
          <Link
            href="/contact" onClick={(e: React.MouseEvent) => { e.preventDefault(); openChat(); }}
            className="inline-flex items-center px-6 py-3 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[15px] hover:bg-[var(--accent-hover)] transition-colors duration-150 btn-press"
          >
            {t("ctaButton")}
          </Link>
        </div>
      </div>
    </div>
  );
}
