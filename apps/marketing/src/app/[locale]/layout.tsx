import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";
import { buildLocaleMetadata, isLocale, type Locale } from "@/lib/seo";
import { DirectionProvider } from "@radix-ui/react-direction";
import LocaleHtmlAttrs from "@/components/LocaleHtmlAttrs";
import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { PageTransitionOverlay } from "@/components/PageTransitionOverlay";
import { AppShell } from "@/components/AppShell";
import LenisProvider from "@/components/LenisProvider";
import CookieBanner from "@/components/CookieBanner";
import ChatWidget from "@/components/ChatWidget";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

/**
 * Default per-locale metadata (applies to every page under [locale]):
 * localized title/description + canonical + hreflang for the locale root.
 * Pages with their own nested layout or generateMetadata override the path
 * (and thus canonical/hreflang), keeping title/description for the page.
 */
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
    path: "/",
    title: t("title"),
    description: t("description"),
    keywords: [
      "AI development agency",
      "web development agency Tunisia",
      "AI software development",
      "custom AI solutions",
      "AI agents",
      "SILKDEV",
    ],
  });
}

export default async function LocaleLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}>) {
  const { locale } = await params;
  setRequestLocale(locale);
  const messages = await getMessages();

  return (
    <>
      {/* Set <html dir/lang> before paint — both supported locales are LTR */}
      <script
        dangerouslySetInnerHTML={{
          __html: `document.documentElement.setAttribute('dir','ltr');document.documentElement.setAttribute('lang','${locale}');`,
        }}
      />
      {/* Keep dir/lang in sync on client-side locale switches (language switcher) */}
      <LocaleHtmlAttrs locale={locale} isRtl={false} />
      <DirectionProvider dir="ltr">
        <NextIntlClientProvider messages={messages}>
          <NuqsAdapter>
            <PageTransitionOverlay />
            <AppShell>{children}</AppShell>
          </NuqsAdapter>
        </NextIntlClientProvider>
      </DirectionProvider>
    </>
  );
}
