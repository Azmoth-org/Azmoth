import { notFound } from "next/navigation";
import { Link } from "@/i18n/navigation";
import type { Metadata } from "next";
import blogs from "@/data/blogs.json";
import { absoluteUrl, buildLocaleMetadata, isLocale, ogLocales, type Locale } from "@/lib/seo";
import { getArticleSchema } from "@/lib/structured-data";
import CaptureForm from "@/components/CaptureForm";

export async function generateStaticParams() {
  const locales = ["en", "fr"];
  return locales.flatMap((locale) =>
    blogs.map((post) => ({ locale, slug: post.slug }))
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}): Promise<Metadata> {
  const { locale, slug } = await params;
  const post = blogs.find((b) => b.slug === slug);
  if (!post) return {};

  const l: Locale = isLocale(locale) ? locale : "en";
  const meta = buildLocaleMetadata({
    locale: l,
    path: `/blog/${slug}`,
    title: `${post.title} | Silkdev Blog`,
    description: post["Short Description"],
    type: "article",
  });

  return {
    ...meta,
    openGraph: {
      type: "article",
      url: absoluteUrl(`/${l}/blog/${slug}`),
      title: `${post.title} | Silkdev Blog`,
      description: post["Short Description"],
      siteName: "Silkdev",
      locale: ogLocales[l],
      images: [
        {
          url: "/og-image.png",
          width: 500,
          height: 500,
          alt: post.title,
        },
      ],
      publishedTime: post.Date,
      authors: [post["writer name"]],
    },
  };
}

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  const post = blogs.find((b) => b.slug === slug);

  if (!post) {
    notFound();
  }

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)]">
      {/* Article structured data (JSON-LD) */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(
            getArticleSchema({
              title: post.title,
              description: post["Short Description"],
              url: absoluteUrl(`/${locale}/blog/${slug}`),
              datePublished: post.Date,
              authorName: post["writer name"],
            })
          ),
        }}
      />
      <article className="max-w-6xl mx-auto px-6 md:px-[40px]">
        {/* Back link */}
        <Link
          href="/blog"
          className="inline-flex items-center gap-1 text-sm text-[var(--muted)] hover:text-[var(--accent)] transition-colors mb-10 tracking-[-0.01em]"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16l-4-4m0 0l4-4m-4 4h18" />
          </svg>
          Back to blog
        </Link>

        <div className="max-w-3xl">

        {/* Header */}
        <header className="mb-10">
          <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--muted)] mb-4 tracking-[-0.01em]">
            <span className="px-2.5 py-1 rounded-lg bg-[var(--accent)]/10 text-[var(--accent)]">
              {post.Category}
            </span>
            <span>
              {new Date(post.Date).toLocaleDateString("en-US", {
                month: "long",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          </div>

          <h1 className="text-[32px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-6 font-['Manrope',system-ui,sans-serif]">
            {post.title}
          </h1>

          <p className="text-[17px] text-[var(--muted)] mb-6 tracking-[-0.01em]">
            {post["Short Description"]}
          </p>

          <div className="flex items-center gap-4 text-sm text-[var(--muted)] pb-6 border-b border-[var(--border)] tracking-[-0.01em]">
            <div>
              <p className="text-white font-medium">{post["writer name"]}</p>
              <p className="text-xs">{post["writer title"]}</p>
            </div>
            <span className="w-1 h-1 rounded-full bg-[var(--muted)]" />
            <span>{post["reading lenght"]}</span>
          </div>
        </header>

        {/* Content */}
        <div
          className="prose"
          dangerouslySetInnerHTML={{ __html: post.Content }}
        />

        {/* Footer */}
        <div className="mt-16 pt-8 border-t border-[var(--border)]">
          <Link
            href="/blog"
            className="inline-flex items-center gap-1 text-sm text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors tracking-[-0.01em]"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16l-4-4m0 0l4-4m-4 4h18" />
            </svg>
            Back to all articles
          </Link>
        </div>

        {/* One-field lead capture */}
        <div className="mt-12">
          <CaptureForm />
        </div>
      </div>
      </article>
    </div>
  );
}
