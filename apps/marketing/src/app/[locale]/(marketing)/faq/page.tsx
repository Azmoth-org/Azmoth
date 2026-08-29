import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@workspace/ui/components/accordion";

import { Section, SectionHeading } from "@/components/section";
import { buildPageMetadata } from "@/lib/seo";
import { getFaqPageSchema } from "@/lib/structured-data";

type Frage = { q: string; a: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });

  return buildPageMetadata({
    path: "/faq",
    title: t("faqTitel"),
    description: t("faqBeschreibung"),
  });
}

export default async function FaqPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  // FAQPage JSON-LD is built from the same catalogue entries the page renders, so
  // the two cannot describe different answers.
  const t = await getTranslations({ locale, namespace: "faq" });
  const schema = getFaqPageSchema(t.raw("fragen") as Frage[]);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
      />
      <FaqContent />
    </>
  );
}

function FaqContent() {
  const t = useTranslations("faq");
  const fragen = t.raw("fragen") as Frage[];

  return (
    <Section className="pt-16 lg:pt-24">
      <SectionHeading title={t("titel")} subtitle={t("untertitel")} as="h1" />
      <Accordion className="mx-auto mt-14 max-w-3xl">
        {fragen.map((frage) => (
          <AccordionItem key={frage.q} value={frage.q}>
            <AccordionTrigger className="text-base">{frage.q}</AccordionTrigger>
            <AccordionContent className="text-muted-foreground">
              {frage.a}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </Section>
  );
}
