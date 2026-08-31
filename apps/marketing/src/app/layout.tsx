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
          Vercel Speed Insights used to sit here and has been removed.
          Two reasons, and the second is the one that settles it. It is dead weight —
          this stack deploys behind Caddy on Azure, where its beacon path does not exist —
          and on a Vercel deployment it would send every visitor's performance data to a
          US service, while /datenschutz states that no usage data is transferred to a
          third country. One of those two had to go, and it was not the privacy notice.
        */}
        <AnalyticsScript />
      </body>
    </html>
  );
}
