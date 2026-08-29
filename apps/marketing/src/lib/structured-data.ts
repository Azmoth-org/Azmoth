import { absoluteUrl, siteMetadata } from "@/lib/seo";

/**
 * JSON-LD structured data builders — SILKDEV (mirrors the SILKLEARN
 * marketing-site pattern). Only real, verifiable facts: Bizerte office,
 * the six service areas, real blog authors. Nothing fabricated.
 */

function stripHtml(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function getOrganizationSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "SILKDEV",
    url: absoluteUrl("/en"),
    logo: absoluteUrl("/favicon.svg"),
    description: siteMetadata.defaultDescription,
    address: {
      "@type": "PostalAddress",
      addressLocality: "Bizerte",
      addressCountry: "TN",
    },
    areaServed: {
      "@type": "Country",
      name: "Tunisia",
    },
    knowsAbout: [
      "web development",
      "AI development",
      "AI support agents",
      "custom AI features",
      "knowledge AI",
      "workflow automation",
      "fractional CTO",
      "UI/UX design",
      "SEO",
    ],
  };
}

export function getWebsiteSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: siteMetadata.siteName,
    url: absoluteUrl("/en"),
    description: siteMetadata.defaultDescription,
    publisher: {
      "@type": "Organization",
      name: "SILKDEV",
    },
    inLanguage: ["en", "fr"],
  };
}

export function getFaqPageSchema(items: Array<{ q: string; a: string }>) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.q,
      acceptedAnswer: {
        "@type": "Answer",
        text: stripHtml(item.a),
      },
    })),
  };
}

export function getArticleSchema({
  title,
  description,
  url,
  datePublished,
  authorName,
}: {
  title: string;
  description: string;
  url: string;
  datePublished: string;
  authorName: string;
}) {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: title,
    description,
    url,
    datePublished,
    author: {
      "@type": "Person",
      name: authorName,
    },
    publisher: {
      "@type": "Organization",
      name: "SILKDEV",
      logo: {
        "@type": "ImageObject",
        url: absoluteUrl("/favicon.svg"),
      },
    },
    mainEntityOfPage: url,
  };
}
