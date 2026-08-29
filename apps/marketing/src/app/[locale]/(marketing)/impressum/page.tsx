import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { LegalDocumentView } from "@/components/legal-document";
import { impressum } from "@/data/legal";
import { buildPageMetadata } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });

  return buildPageMetadata({
    path: "/impressum",
    title: t("impressumTitel"),
    description: t("impressumBeschreibung"),
  });
}

export default async function ImpressumPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <LegalDocumentView document={impressum} />;
}
