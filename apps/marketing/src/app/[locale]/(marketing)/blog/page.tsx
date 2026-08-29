import { Link } from "@/i18n/navigation";
import blogs from "@/data/blogs.json";

export default function BlogPage() {
  const sorted = [...blogs].sort(
    (a, b) => new Date(b.Date).getTime() - new Date(a.Date).getTime()
  );

  const latest = sorted[0];
  const rest = sorted.slice(1);

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)]">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        {/* Header */}
        <div className="mb-[100px]">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-6">
            <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
              Insights / Blog
            </span>
          </div>
          <h1 className="text-[36px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            Field notes for building digital momentum
          </h1>
          <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em] max-w-xl">
            Stories, systems, and practical thinking from the Silk Nexus team —
            organized from the CMS so new articles stay easy to publish.
          </p>
        </div>

        {/* Latest article */}
        {latest && (
          <div className="mb-[100px]">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-medium mb-6 tracking-[-0.01em]">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]" />
              Latest insight
            </div>
            <div className="glass rounded-2xl p-8 md:p-10 hover:border-[var(--accent)]/30 transition-colors duration-200">
              <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--muted)] mb-4 tracking-[-0.01em]">
                <span className="px-2.5 py-1 rounded-lg bg-[var(--accent)]/10 text-[var(--accent)]">
                  {latest.Category}
                </span>
                <span>
                  {new Date(latest.Date).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })}
                </span>
                <span>Updated from the CMS</span>
              </div>
              <h2 className="text-[28px] md:text-[32px] font-bold tracking-[-0.02em] text-white mb-4 leading-[1.2] font-['Manrope',system-ui,sans-serif]">
                <Link href={`/blog/${latest.slug}`} className="hover:text-[var(--accent)] transition-colors">
                  {latest.title}
                </Link>
              </h2>
              <p className="text-[var(--muted)] mb-6 max-w-2xl text-[15px] leading-[1.7] tracking-[-0.01em]">
                {latest["Short Description"]}
              </p>
              <div className="flex items-center gap-3 text-sm text-[var(--muted)] tracking-[-0.01em]">
                <span>{latest["writer name"]}</span>
                <span className="w-1 h-1 rounded-full bg-[var(--muted)]" />
                <span>{latest["reading lenght"]}</span>
              </div>
              <div className="mt-6">
                <Link
                  href={`/blog/${latest.slug}`}
                  className="inline-flex items-center gap-1 text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium text-sm transition-colors"
                >
                  Read more
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                  </svg>
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* All articles */}
        <div>
          <h2 className="text-[13px] font-semibold text-white uppercase tracking-[0.05em] mb-6">
            All articles
          </h2>
          {rest.length === 0 && sorted.length <= 1 && (
            <p className="text-[var(--muted)]">No articles yet.</p>
          )}
          <div className="space-y-4">
            {rest.map((post) => (
              <Link
                key={post.slug}
                href={`/blog/${post.slug}`}
                className="block glass rounded-xl p-6 hover:border-[var(--accent)]/30 transition-colors duration-200 group"
              >
                <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--muted)] mb-2 tracking-[-0.01em]">
                  <span className="px-2.5 py-1 rounded-lg bg-[var(--accent)]/10 text-[var(--accent)]">
                    {post.Category}
                  </span>
                  <span>
                    {new Date(post.Date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                  </span>
                </div>
                <h3 className="text-[17px] font-semibold tracking-[-0.01em] text-white group-hover:text-[var(--accent)] transition-colors mb-2">
                  {post.title}
                </h3>
                <p className="text-sm text-[var(--muted)] line-clamp-2 leading-[1.6] tracking-[-0.01em]">
                  {post["Short Description"]}
                </p>
                <div className="flex items-center gap-3 mt-3 text-xs text-[var(--muted)] tracking-[-0.01em]">
                  <span>{post["writer name"]}</span>
                  <span className="w-1 h-1 rounded-full bg-[var(--muted)]" />
                  <span>{post["reading lenght"]}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
