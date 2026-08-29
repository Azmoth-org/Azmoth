import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { buildLocaleMetadata, isLocale, type Locale } from "@/lib/seo";
import { getFaqPageSchema } from "@/lib/structured-data";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const l: Locale = isLocale(locale) ? locale : "en";
  const t = await getTranslations({ locale: l, namespace: "faq" });
  return buildLocaleMetadata({
    locale: l,
    path: "/faq",
    title: t("pageTitle"),
    description: t("subtitle"),
  });
}

export default async function FaqLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const l: Locale = isLocale(locale) ? locale : "en";
  const t = await getTranslations({ locale: l, namespace: "faq" });
  const items = t.raw("items") as Array<{ q: string; a: string }>;

  return (
    <>
      {children}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(getFaqPageSchema(items)) }}
      />
    </>
  );
}
