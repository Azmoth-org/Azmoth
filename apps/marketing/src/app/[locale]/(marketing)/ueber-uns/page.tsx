import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Section, SectionHeading } from "@/components/section";
import { buildPageMetadata } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });

  return buildPageMetadata({
    path: "/ueber-uns",
    title: t("ueberUnsTitel"),
    description: t("ueberUnsBeschreibung"),
  });
}

export default async function UeberUnsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <UeberUnsContent />;
}

function UeberUnsContent() {
  const t = useTranslations("ueberUns");
  const paragraphs = t.raw("absaetze") as string[];

  return (
    <Section className="pt-16 lg:pt-24">
      <SectionHeading
        title={t("titel")}
        subtitle={t("untertitel")}
        align="start"
        as="h1"
      />
      <div className="mt-10 flex max-w-2xl flex-col gap-6">
        {paragraphs.map((paragraph) => (
          <p key={paragraph} className="text-pretty text-muted-foreground">
            {paragraph}
          </p>
        ))}
      </div>
    </Section>
  );
}
