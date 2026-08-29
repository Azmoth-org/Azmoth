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

/*
 * The card is served by src/app/opengraph-image.tsx (and twitter-image.tsx), which
 * render it with `next/og` at request time.
 *
 * It has to be named explicitly here rather than left to Next's file convention.
 * The convention attaches the image to the segment the file sits in — the root —
 * and `openGraph` is *replaced* by a child's metadata rather than deep-merged, so
 * every page that returns its own `openGraph` block dropped the inherited image and
 * emitted no og:image at all. `metadataBase` makes this relative path absolute.
 */
const OG_IMAGE = {
  url: "/opengraph-image",
  width: 1200,
  height: 630,
} as const;

type PageMetadataInput = {
  /** Path of the page, e.g. "/funktionen" or "/". */
  path: string;
  /** A plain string joins the root's "%s · Azmoth" template; `{ absolute }` replaces it. */
  title: string | { absolute: string };
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
  // og:title takes no template, so it needs the plain string either way.
  const ogTitle = typeof title === "string" ? title : title.absolute;

  return {
    title,
    description,
    keywords,
    alternates: { canonical: path },
    openGraph: {
      type,
      url: absoluteUrl(path),
      title: ogTitle,
      description,
      siteName: siteConfig.name,
      locale: "de_DE",
      images: [{ ...OG_IMAGE, alt: ogTitle }],
    },
    twitter: {
      card: "summary_large_image",
      title: ogTitle,
      description,
      images: [OG_IMAGE.url],
    },
  };
}

const defaultTitle = siteConfig.title;

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
    images: [{ ...OG_IMAGE, alt: siteConfig.name }],
  },
  twitter: {
    card: "summary_large_image",
    title: defaultTitle,
    description: siteConfig.description,
    images: [OG_IMAGE.url],
  },
};
