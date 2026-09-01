import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  DocsBody,
  DocsDescription,
  DocsPage,
  DocsTitle,
} from "fumadocs-ui/page";
import { createRelativeLink } from "fumadocs-ui/mdx";

import { getMDXComponents } from "@/mdx-components";
import { absoluteUrl, siteConfig } from "@/lib/site";
import { source } from "@/lib/source";

/**
 * Every documentation page, as one optional catch-all.
 *
 * Optional (`[[...slug]]`) rather than required, because `baseUrl` is `/`: the landing page's
 * slug array is empty, and a required catch-all would not match it, leaving `content/docs/index.mdx`
 * with no route at all.
 */

export function generateStaticParams() {
  return source.generateParams();
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const page = source.getPage(slug);
  if (!page) notFound();

  const url = page.url;

  return {
    title: page.data.title,
    description: page.data.description,
    alternates: { canonical: url },
    openGraph: {
      type: "article",
      url: absoluteUrl(url),
      title: page.data.title,
      description: page.data.description,
      siteName: siteConfig.name,
      locale: "de_DE",
    },
  };
}

export default async function Page({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}) {
  const { slug } = await params;
  const page = source.getPage(slug);
  if (!page) notFound();

  const MDX = page.data.body;

  return (
    <DocsPage toc={page.data.toc} full={page.data.full}>
      <DocsTitle>{page.data.title}</DocsTitle>
      <DocsDescription>{page.data.description}</DocsDescription>
      <DocsBody>
        {/*
          `createRelativeLink` is what makes `[Partner-API](./api/partner-api.mdx)` work in MDX.
          Without it a relative link is emitted verbatim and 404s in the browser, because the
          file path and the published URL are not the same string — the extension is dropped and
          `index` collapses to the directory. Authors get to link the file they can see in the
          editor, and the mapping happens here rather than in every page's frontmatter.
        */}
        <MDX components={getMDXComponents({ a: createRelativeLink(source, page) })} />
      </DocsBody>
    </DocsPage>
  );
}
