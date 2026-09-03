import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { cn } from "@workspace/ui/lib/utils";

import { AnalyticsScript } from "@/components/analytics-script";

import { defaultMetadata } from "@/lib/seo";
import { getOrganizationSchema, getWebsiteSchema } from "@/lib/structured-data";
import "./globals.css";

/**
 * `next/font` rather than an `@import url(fonts.googleapis.com)` in the stylesheet.
 * The CSS import is render-blocking against a third-party origin on every cold
 * visit; this self-hosts the file, emits the `@font-face` inline, and sets
 * `--font-sans`, which is the variable `@workspace/ui` already reads.
 */
const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = defaultMetadata;

const structuredData = JSON.stringify([getOrganizationSchema(), getWebsiteSchema()]);

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    /*
     * Light, with no toggle and no `system` check — the same decision apps/web
     * makes, for the same reason. This product carries invoice amounts and a
     * physician's signature, and a public page that arrives dark because a laptop
     * switched at sunset reads as the developer-tool version of the product. The
     * palette is defined on bare `:root` in @workspace/ui, so simply not setting
     * the class is the light theme.
     */
    <html
      lang="de"
      className={cn("antialiased font-sans", inter.variable)}
      suppressHydrationWarning
    >
      <head>
        {/*
         * The scroll reveals' failure mode, closed.
         *
         * `components/reveal.tsx` server-renders `opacity:0` inline on everything that fades in on
         * scroll — that is how these libraries avoid a flash of unstyled content, and it means a
         * visitor whose JavaScript never runs receives a complete, correct document with every
         * word of it invisible. A chunk blocked by a corporate proxy, a strict CSP, scripting
         * turned off: a blank page that returned HTTP 200.
         *
         * `!important` is not defensive styling here, it is the only thing that works. What is
         * being overridden is an inline `style` attribute, which outranks every ordinary rule
         * regardless of specificity or source order.
         *
         * Inline in `<head>` rather than in `globals.css`, because a stylesheet is itself a
         * subresource: a network condition that stopped the JavaScript may well have stopped the
         * CSS too, and the rule that rescues the page cannot depend on another request succeeding.
         */}
        <noscript
          dangerouslySetInnerHTML={{
            __html:
              "<style>[data-reveal]{opacity:1!important;filter:none!important;transform:none!important}</style>",
          }}
        />
      </head>
      <body className="bg-background text-foreground">
        {/*
         * A plain <script>, not next/script: this has to be in the static HTML a
         * crawler receives, and next/script would defer it into the RSC payload.
         */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: structuredData }}
        />
        {children}
        {/*
          `@vercel/analytics` and `@vercel/speed-insights` were mounted here and have been removed
          again. They were added in two commits immediately before the audit that prompted this
          pass, directly beneath a comment explaining why they had been taken out the last time.

          That comment gave two reasons and one of them was wrong: this site does deploy to Vercel,
          so the beacons resolve. The other one stands and is the one that decides it. Both scripts
          send visitor data to a US service, and `/datenschutz` — three clicks away, on a site whose
          entire argument is that it is the DSGVO-safe option — states that no usage data is
          transferred to a third country. A page cannot make that claim and also ship the beacon.

          Reach measurement is `AnalyticsScript` below: Plausible or Umami, cookieless, off unless
          `NEXT_PUBLIC_ANALYTICS_PROVIDER` is set. See `lib/analytics.ts`.
        */}
        <AnalyticsScript />
      </body>
    </html>
  );
}
