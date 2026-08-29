"use client";

import { Link } from "@/i18n/navigation";
import { useTranslations } from "next-intl";
import { PRODUCTS } from "@/data/products";

export default function ProductsSection({ limit }: { limit?: number }) {
  const t = useTranslations("home");
  const common = useTranslations("common");
  const display = limit ? PRODUCTS.slice(0, limit) : PRODUCTS;

  return (
    <section className="py-[100px]">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        {/* Section header */}
        <div className="max-w-3xl mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-6">
            <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
              {common("badgeProducts")}
            </span>
          </div>
          <h2 className="text-[36px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-4 font-['Manrope',system-ui,sans-serif]">
            {t("productsTitle")}
          </h2>
          <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em] max-w-xl">
            {t("productsSub")}
          </p>
        </div>

        {/* Product cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {display.map((product) => (
            <a
              key={product.name}
              href={product.url}
              target={
                product.url.startsWith("http") ? "_blank" : undefined
              }
              rel={
                product.url.startsWith("http")
                  ? "noopener noreferrer"
                  : undefined
              }
              className="group block glass rounded-2xl p-8 hover:border-transparent transition-colors duration-250 relative overflow-hidden"
              style={{
                borderColor: "var(--border)",
              }}
            >
              {/* Gradient hover glow */}
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-5 transition-opacity duration-500 rounded-2xl"
                style={{
                  background: `linear-gradient(135deg, ${product.accent}22, transparent)`,
                }}
              />

              {/* Status badge */}
              <div className="flex items-center justify-between mb-5">
                <div
                  className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium tracking-[-0.01em]"
                  style={{
                    background: `${product.accent}15`,
                    color: product.accent,
                  }}
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ background: product.accent }}
                  />
                  {product.status}
                </div>
              </div>

              {/* Name + icon */}
              <div className="flex items-center gap-3 mb-2">
                {product.iconPath && (
                  <img
                    src={product.iconPath}
                    alt={`${product.name} icon`}
                    className="w-8 h-8 flex-shrink-0"
                  />
                )}
                <h3
                  className="text-[28px] font-bold tracking-[-0.02em] font-['Manrope',system-ui,sans-serif] transition-colors duration-200"
                  style={{ color: "var(--foreground)" }}
                >
                  {product.name}
                </h3>
              </div>

              {/* Tagline */}
              <p
                className="text-[17px] font-medium mb-3 transition-colors duration-300"
                style={{ color: product.accent }}
              >
                {product.tagline}
              </p>

              {/* Description */}
              <p className="text-[15px] text-[var(--muted)] leading-[1.7] tracking-[-0.01em] mb-6">
                {product.description}
              </p>

              {/* Arrow */}
              <div
                className="inline-flex items-center gap-1 text-sm font-medium transition-colors duration-200 group-hover:gap-2"
                style={{ color: product.accent }}
              >
                {product.url === "#" ? "Coming soon" : "Learn more"}
                <svg
                  className="w-4 h-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17 8l4 4m0 0l-4 4m4-4H3"
                  />
                </svg>
              </div>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
