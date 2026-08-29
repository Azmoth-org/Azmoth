import type { Metadata } from "next";

/**
 * SEO helpers — SILKDEV (mirrors the SILKLEARN marketing-site pattern, but
 * locale-aware: silkdev routes every page under /en /fr /ar).
 */

const siteName = "Silkdev";
const defaultTitle = "Web Design & Development Agency | Silkdev";
const defaultDescription =
  "Designing software from Tunisia. An AI development agency in Bizerte.";

export const LOCALES = ["en", "fr"] as const;
export type Locale = (typeof LOCALES)[number];

export function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
}

export const ogLocales: Record<Locale, string> = {
  en: "en_US",
  fr: "fr_FR",
};

export function getSiteUrl() {
  const configuredUrl = process.env.NEXT_PUBLIC_SITE_URL;

  if (configuredUrl) {
    return configuredUrl;
  }

  const productionUrl = process.env.VERCEL_PROJECT_PRODUCTION_URL;

  if (productionUrl) {
    return `https://${productionUrl}`;
  }

  const previewUrl = process.env.VERCEL_URL;

  if (previewUrl) {
    return `https://${previewUrl}`;
  }

  return "https://silkdev.com.tn";
}

export function absoluteUrl(path = "/") {
  return new URL(path, getSiteUrl()).toString();
}

/** Locale-prefixed path, e.g. localePath("/services", "fr") → "/fr/services". */
export function localePath(path: string, locale: Locale): string {
  const normalized = path === "/" ? "" : path;
  return `/${locale}${normalized}`;
}

type BuildLocaleMetadataInput = {
  locale: Locale;
  /** Locale-less path of the page, e.g. "/services" or "/". */
  path: string;
  title: string;
  description: string;
  type?: "website" | "article";
  keywords?: string[];
};

/**
 * Metadata for one locale version of a page: self-referencing canonical,
 * hreflang alternates across en/fr (+ x-default → the English version),
 * and Open Graph/twitter with the absolute URL and the right og:locale.
 */
export function buildLocaleMetadata({
  locale,
  path,
  title,
  description,
  type = "website",
  keywords,
}: BuildLocaleMetadataInput): Metadata {
  const canonicalPath = localePath(path, locale);
  const url = absoluteUrl(canonicalPath);

  const languages: Record<string, string> = {
    en: localePath(path, "en"),
    fr: localePath(path, "fr"),
    "x-default": localePath(path, "en"),
  };

  return {
    title,
    description,
    keywords,
    alternates: {
      canonical: canonicalPath,
      languages,
    },
    openGraph: {
      type,
      url,
      title,
      description,
      siteName,
      locale: ogLocales[locale],
      images: [
        {
          url: "/og-image.png",
          width: 500,
          height: 500,
          alt: title,
        },
      ],
    },
    twitter: {
      card: "summary",
      title,
      description,
      images: ["/og-image.png"],
    },
  };
}

export const defaultMetadata: Metadata = {
  metadataBase: new URL(getSiteUrl()),
  title: defaultTitle,
  description: defaultDescription,
  icons: {
    icon: [
      { url: "/favicon.ico", type: "image/x-icon" },
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-96x96.png", type: "image/png", sizes: "96x96" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
    shortcut: { url: "/favicon.ico" },
  },
  manifest: "/site.webmanifest",
  openGraph: {
    type: "website",
    url: absoluteUrl("/en"),
    title: defaultTitle,
    description: defaultDescription,
    siteName,
    locale: "en_US",
    images: [
      {
        url: "/og-image.png",
        width: 500,
        height: 500,
        alt: "Silkdev",
      },
    ],
  },
  twitter: {
    card: "summary",
    title: defaultTitle,
    description: defaultDescription,
    images: ["/og-image.png"],
  },
};

export const siteMetadata = {
  siteName,
  defaultTitle,
  defaultDescription,
  LOCALES,
};
