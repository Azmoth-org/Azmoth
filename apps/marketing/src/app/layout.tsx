import type { Metadata } from "next";
import Script from "next/script";
import { SpeedInsights } from "@vercel/speed-insights/next";
import { NextIntlClientProvider } from "next-intl";
import { defaultMetadata } from "@/lib/seo";
import { getOrganizationSchema, getWebsiteSchema } from "@/lib/structured-data";
import "./globals.css";

export const metadata: Metadata = defaultMetadata;

// Google Tag Manager — container GTM-MDTCM7XG.
// Head snippet (as high in <head> as possible) + noscript right after <body>.
const GTM_HEAD = `<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','GTM-MDTCM7XG');</script>
<!-- End Google Tag Manager -->`;

const GTM_NOSCRIPT = `<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-MDTCM7XG"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // lang/dir are set per-locale by a pre-paint script in the [locale]
  // layout — suppressHydrationWarning stops React from flagging the
  // post-server mutation (standard next-intl pattern).
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      {/* GTM head snippet — beforeInteractive injects it into <head> in the
          initial HTML, as high as the app router allows. */}
      <Script
        id="gtm-container"
        strategy="beforeInteractive"
        dangerouslySetInnerHTML={{ __html: GTM_HEAD }}
      />
      <body className="antialiased">
        <noscript dangerouslySetInnerHTML={{ __html: GTM_NOSCRIPT }} />
        {/* Organization + WebSite structured data (JSON-LD) — plain script tag
            so it lands in the static HTML for crawlers (next/script would
            defer it into the RSC payload instead). */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify([
              getOrganizationSchema(),
              getWebsiteSchema(),
            ]),
          }}
        />
        {children}
        {/* Vercel Speed Insights — real-user Core Web Vitals (auto project-id
            on Vercel deployments; no-op off Vercel). */}
        <SpeedInsights />
      </body>
    </html>
  );
}
