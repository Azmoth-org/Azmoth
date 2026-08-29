import type { MetadataRoute } from "next";
import blogs from "@/data/blogs.json";
import { absoluteUrl, siteMetadata } from "@/lib/seo";

const staticRoutes = [
  "",
  "/about",
  "/blog",
  "/contact",
  "/faq",
  "/intake",
  "/privacy",
  "/products",
  "/services",
  "/terms",
];

const serviceSlugs = [
  "web-development",
  "ai-support-agents",
  "custom-ai-features",
  "knowledge-ai",
  "automation",
  "fractional-cto",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const today = new Date().toISOString().split("T")[0];
  const entries: MetadataRoute.Sitemap = [];

  for (const locale of siteMetadata.LOCALES) {
    for (const route of staticRoutes) {
      entries.push({
        url: absoluteUrl(`/${locale}${route}`),
        lastModified: today,
        changeFrequency: "monthly",
        priority: route === "" ? 1.0 : 0.8,
      });
    }

    for (const slug of serviceSlugs) {
      entries.push({
        url: absoluteUrl(`/${locale}/services/${slug}`),
        lastModified: today,
        changeFrequency: "monthly",
        priority: 0.7,
      });
    }

    for (const post of blogs) {
      entries.push({
        url: absoluteUrl(`/${locale}/blog/${post.slug}`),
        lastModified: post.Date
          ? new Date(post.Date).toISOString().split("T")[0]
          : today,
        changeFrequency: "weekly",
        priority: 0.6,
      });
    }
  }

  return entries;
}
