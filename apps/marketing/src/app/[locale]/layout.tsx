import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { SiteShell } from "@/components/site-shell";
import { routing } from "@/i18n/routing";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

/**
 * The only namespace a client component reads: the header (`navigation`).
 *
 * `NextIntlClientProvider` serialises whatever it is given into the RSC payload, and left
 * to itself it takes the whole catalogue — every FAQ answer, the Impressum and the whole
 * privacy notice — into the browser on a page that renders none of it. Every other
 * component on this site is a server component and reads its strings during render.
 *
 * `cookies` used to be here too, for the consent banner. The banner is gone: reach
 * measurement is now cookieless and stores nothing on the device, so there is nothing to
 * ask permission for. See `lib/analytics.ts`.
 */
const CLIENT_NAMESPACES = ["navigation"] as const;

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();

  // Opts every page under this segment into static rendering.
  setRequestLocale(locale);

  const messages = await getMessages();
  const clientMessages = Object.fromEntries(
    CLIENT_NAMESPACES.map((namespace) => [namespace, messages[namespace]])
  );

  return (
    <NextIntlClientProvider messages={clientMessages}>
      <SiteShell>{children}</SiteShell>
    </NextIntlClientProvider>
  );
}
