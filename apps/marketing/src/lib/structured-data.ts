import { absoluteUrl } from "@/lib/seo";
import { siteConfig } from "@/lib/site";

/**
 * JSON-LD, restricted to things that are actually true.
 *
 * Structured data is read by machines that cannot tell an aspiration from a fact,
 * and a fabricated `aggregateRating` or a review count nobody can produce is worth
 * a manual action. Everything below is either the product's own description or a
 * question genuinely answered on the FAQ page.
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
    name: siteConfig.name,
    url: absoluteUrl("/"),
    logo: absoluteUrl("/favicon.svg"),
    description: siteConfig.description,
    areaServed: { "@type": "Country", name: "Deutschland" },
    knowsAbout: [
      "GOÄ",
      "Gebührenordnung für Ärzte",
      "Privatliquidation",
      "Rechnungsprüfung",
      "PADnext",
      "Abrechnungssoftware",
    ],
  };
}

export function getWebsiteSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: siteConfig.name,
    url: absoluteUrl("/"),
    description: siteConfig.description,
    publisher: { "@type": "Organization", name: siteConfig.name },
    inLanguage: "de",
  };
}

export function getFaqPageSchema(items: ReadonlyArray<{ q: string; a: string }>) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.q,
      acceptedAnswer: { "@type": "Answer", text: stripHtml(item.a) },
    })),
  };
}
