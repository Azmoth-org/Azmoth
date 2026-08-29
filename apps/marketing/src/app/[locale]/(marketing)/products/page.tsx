"use client";

import { openChat } from "@/lib/openChat";
import { PRODUCTS } from "@/data/products";
import { Link } from "@/i18n/navigation";

export default function ProductsPage() {
  const [featured, ...rest] = PRODUCTS;

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)]">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        {/* Header */}
        <div className="mb-[100px]">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-6">
            <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
              Products
            </span>
          </div>
          <h1 className="text-[36px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            Our Products
          </h1>
          <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em] max-w-xl">
            Each product is a bet on a specific future we want to bring closer.
            From knowledge infrastructure to team matching to accounting —
            here&apos;s what we&apos;re building.
          </p>
        </div>

        {/* Featured product — hero card */}
        <div className="mb-[100px]">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium mb-6 tracking-[-0.01em]"
            style={{ background: `${featured.accent}15`, color: featured.accent }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: featured.accent }} />
            Featured product
          </div>

          <a
            href={featured.url}
            target="_blank"
            rel="noopener noreferrer"
            className="group block glass rounded-2xl p-10 md:p-14 hover:border-transparent transition-colors duration-250 relative overflow-hidden"
          >
            <div
              className="absolute inset-0 opacity-0 group-hover:opacity-10 transition-opacity duration-500 rounded-2xl"
              style={{ background: `linear-gradient(135deg, ${featured.accent}33, transparent)` }}
            />
            {featured.iconPath && (
              <img
                src={featured.iconPath}
                alt={featured.name}
                className="h-12 w-auto mb-6"
              />
            )}
            <div
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium mb-6 tracking-[-0.01em]"
              style={{ background: `${featured.accent}15`, color: featured.accent }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: featured.accent }} />
              {featured.status}
            </div>
            <h2 className="text-[32px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-3 font-['Manrope',system-ui,sans-serif]">
              {featured.name}
            </h2>
            <p
              className="text-[20px] md:text-[24px] font-medium mb-4"
              style={{ color: featured.accent }}
            >
              {featured.tagline}
            </p>
            <p className="text-[16px] text-[var(--muted)] leading-[1.7] tracking-[-0.01em] max-w-2xl mb-8">
              {featured.description}
            </p>
            <div
              className="inline-flex items-center gap-2 text-sm font-medium transition-colors duration-200 group-hover:gap-3"
              style={{ color: featured.accent }}
            >
              Visit {featured.name}
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </div>
          </a>
        </div>

        {/* Other products */}
        <div className="mb-[100px]">
          <h2 className="text-[13px] font-semibold text-white uppercase tracking-[0.05em] mb-6">
            All Products
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {rest.map((product) => (
              <a
                key={product.name}
                href={product.url}
                target={product.url.startsWith("http") ? "_blank" : undefined}
                rel={product.url.startsWith("http") ? "noopener noreferrer" : undefined}
                className="group block glass rounded-2xl p-8 hover:border-transparent transition-colors duration-250 relative overflow-hidden"
              >
                <div
                  className="absolute inset-0 opacity-0 group-hover:opacity-5 transition-opacity duration-500 rounded-2xl"
                  style={{ background: `linear-gradient(135deg, ${product.accent}22, transparent)` }}
                />
                {product.iconPath && (
                  <img
                    src={product.iconPath}
                    alt={product.name}
                    className="h-10 w-auto mb-5"
                  />
                )}
                <div
                  className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium mb-5 tracking-[-0.01em]"
                  style={{ background: `${product.accent}15`, color: product.accent }}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: product.accent }} />
                  {product.status}
                </div>
                <h3 className="text-[24px] font-bold tracking-[-0.02em] text-white mb-2 font-['Manrope',system-ui,sans-serif]">
                  {product.name}
                </h3>
                <p className="text-[16px] font-medium mb-3" style={{ color: product.accent }}>
                  {product.tagline}
                </p>
                <p className="text-[14px] text-[var(--muted)] leading-[1.7] tracking-[-0.01em] mb-6">
                  {product.description}
                </p>
                <div
                  className="inline-flex items-center gap-1 text-sm font-medium transition-colors duration-200 group-hover:gap-2"
                  style={{ color: product.accent }}
                >
                  {product.url === "#" ? "Coming soon" : "Learn more"}
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                  </svg>
                </div>
              </a>
            ))}
          </div>
        </div>

        {/* CTA */}
        <div className="glass rounded-2xl p-10 md:p-14 text-center max-w-3xl mx-auto">
          <h2 className="text-[28px] md:text-[32px] font-bold tracking-[-0.02em] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            Want to know more?
          </h2>
          <p className="text-[var(--muted)] text-[16px] mb-8 max-w-lg mx-auto tracking-[-0.01em]">
            Each product has its own story. Reach out if something resonates —
            or if you have an idea that doesn&apos;t fit any of these boxes.
          </p>
          <Link
            href="/contact" onClick={(e: React.MouseEvent) => { e.preventDefault(); openChat(); }}
            className="inline-flex items-center px-8 py-3 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[15px] hover:bg-[var(--accent-hover)] transition-colors duration-150 btn-press"
          >
            Get in touch →
          </Link>
        </div>
      </div>
    </div>
  );
}
