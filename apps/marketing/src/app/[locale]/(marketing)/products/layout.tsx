import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { buildLocaleMetadata, isLocale, type Locale } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const l: Locale = isLocale(locale) ? locale : "en";
  const t = await getTranslations({ locale: l, namespace: "metadata" });
  return buildLocaleMetadata({
    locale: l,
    path: "/products",
    title: t("title"),
    description: t("description"),
    keywords: [
      "SILKLEARN",
      "knowledge graph platform",
      "AI products",
      "LucaP accounting software",
      "AI-native software",
      "SILKLABS",
      "SILKGUILD",
    ],
  });
}

export default function ProductsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
