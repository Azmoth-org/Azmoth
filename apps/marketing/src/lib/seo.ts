import type { Metadata } from "next";

import { siteConfig } from "@/lib/site";

/**
 * Canonical URLs and per-page metadata.
 *
 * The site is single-locale, so there are no hreflang alternates to emit — a
 * `languages` map naming only `de` is noise that tells a crawler nothing. When a
 * second locale arrives, this is where it comes back.
 */

export function getSiteUrl(): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL;
  if (configured) return configured;

  const production = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  if (production) return `https://${production}`;

  const preview = process.env.VERCEL_URL;
  if (preview) return `https://${preview}`;

  return "http://localhost:3001";
}

export function absoluteUrl(path = "/"): string {
  return new URL(path, getSiteUrl()).toString();
}

type PageMetadataInput = {
  /** Path of the page, e.g. "/funktionen" or "/". */
  path: string;
  title: string;
  description: string;
  type?: "website" | "article";
  keywords?: string[];
};

/** Metadata for one page: self-referencing canonical, Open Graph, Twitter card. */
export function buildPageMetadata({
  path,
  title,
  description,
  type = "website",
  keywords,
}: PageMetadataInput): Metadata {
  return {
    title,
    description,
    keywords,
    alternates: { canonical: path },
    openGraph: {
      type,
      url: absoluteUrl(path),
      title,
      description,
      siteName: siteConfig.name,
      locale: "de_DE",
    },
    twitter: {
      card: "summary",
      title,
      description,
    },
  };
}

const defaultTitle = `${siteConfig.name} — ${siteConfig.tagline}`;

export const defaultMetadata: Metadata = {
  metadataBase: new URL(getSiteUrl()),
  title: {
    default: defaultTitle,
    template: `%s · ${siteConfig.name}`,
  },
  description: siteConfig.description,
  /*
   * SVG only. The .ico / .png / apple-touch set that used to be here was the
   * original template author's artwork and was removed with the rest of their
   * branding; pointing at files that no longer exist would serve 404s to every
   * browser that asks. Phase 2 generates the raster set from the real Azmoth mark.
   */
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
  },
  manifest: "/site.webmanifest",
  openGraph: {
    type: "website",
    url: absoluteUrl("/"),
    title: defaultTitle,
    description: siteConfig.description,
    siteName: siteConfig.name,
    locale: "de_DE",
  },
  twitter: {
    card: "summary",
    title: defaultTitle,
    description: siteConfig.description,
  },
};
