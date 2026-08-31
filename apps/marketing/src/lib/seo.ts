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
   * The real set, generated from the Azmoth mark. It replaces a single 367-byte
   * placeholder SVG — a blue rounded square with a tick — that stood in while the
   * brand did not exist.
   *
   * **Raster only, and that is deliberate.** The generator also produced a
   * `favicon.svg`, and it was 2.0 MB: the same 2676x1492 monogram raster wrapped in
   * an `<svg>`. Browsers *prefer* an SVG icon when one is offered, so listing it
   * would have made every cold visit download two megabytes before the page — for a
   * 16-pixel tab icon. It is not shipped and not linked. `brand/` keeps it.
   *
   * `/favicon.ico` carries 48, 32 and 16 in one file, which is what a browser that
   * reads no `<link>` at all fetches from the origin root. The 96px PNG is what a
   * modern browser picks for a high-DPI tab; `apple-touch-icon` is iOS's home
   * screen. All five live at the root of `public/` rather than in a subdirectory,
   * because the automatic requests for the first two only work from there.
   */
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "48x48 32x32 16x16" },
      { url: "/favicon-96x96.png", type: "image/png", sizes: "96x96" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
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
