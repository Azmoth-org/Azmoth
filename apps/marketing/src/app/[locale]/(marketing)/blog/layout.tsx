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
    path: "/blog",
    title: t("title"),
    description: t("description"),
    keywords: [
      "AI development blog",
      "web development insights",
      "AI agency blog",
      "software development Tunisia",
      "AI agents for business",
    ],
  });
}

export default function BlogLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
