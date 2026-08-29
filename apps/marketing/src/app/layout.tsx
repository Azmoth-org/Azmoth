import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { SpeedInsights } from "@vercel/speed-insights/next";

import { cn } from "@workspace/ui/lib/utils";

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
    <html lang="de" className={cn(inter.variable, "dark")} suppressHydrationWarning>
      <body className="bg-background text-foreground antialiased">
        {/*
         * A plain <script>, not next/script: this has to be in the static HTML a
         * crawler receives, and next/script would defer it into the RSC payload.
         */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: structuredData }}
        />
        {children}
        <SpeedInsights />
      </body>
    </html>
  );
}
