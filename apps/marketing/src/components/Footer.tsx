"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { TransitionLink } from "@/components/TransitionLink";
import { openChat } from "@/lib/openChat";
import { motion, useMotionValue, useTransform } from "framer-motion";

const SOCIAL_LINKS = [
  { label: "fb", href: "https://www.facebook.com/silkdevcorp" },
  { label: "in", href: "https://www.linkedin.com/company/silkdev" },
  { label: "ig", href: "https://www.instagram.com/silk.dev" },
];

function MarqueeContent() {
  return (
    <div className="flex justify-center whitespace-nowrap py-6 md:py-8">
      <span
        className="text-[clamp(64px,21vw,120px)] md:text-[180px] lg:text-[245px] font-bold leading-none select-none"
        style={{
          fontFamily: "'Drystick', system-ui, sans-serif",
          letterSpacing: "-0.03em",
        }}
      >
        SILKDEV
      </span>
    </div>
  );
}

function MarqueeText() {
  // Mobile (<810px): render the marquee statically (no hover to track).
  if (typeof window !== "undefined" && window.matchMedia("(max-width: 810px)")?.matches) {
    return <MarqueeContent />;
  }

  // Desktop: 3D matrix3d skew that tracks the mouse — the withTextSkewAnimation effect.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const mouseX = useMotionValue(0);
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const progress = useTransform(mouseX, [-1, 0, 1], [0, 0.5, 1]);

  const leftMatrix = [
    0.96, 0.11, 0, -0.001, -0.13, 0.29, 0, -0.0006, 0, 0, 1, 0, -150,
    -70, 0, 1,
  ];
  const centerMatrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const rightMatrix = [
    0.91, -0.11, 0, 0.001, 0.27, 0.46, 0, -0.0004, 0, 0, 1, 0, 150, -70,
    0, 1,
  ];

  // eslint-disable-next-line react-hooks/rules-of-hooks
  const matrixTransform = useTransform(progress, (latest) => {
    const interpolatedMatrix = leftMatrix.map((_, i) => {
      let value;
      if (latest <= 0.5) {
        value =
          leftMatrix[i] +
          (centerMatrix[i] - leftMatrix[i]) * (latest * 2);
      } else {
        value =
          centerMatrix[i] +
          (rightMatrix[i] - centerMatrix[i]) * ((latest - 0.5) * 2);
      }
      return Number(value.toFixed(6));
    });
    return `matrix3d(${interpolatedMatrix.join(",")})`;
  });

  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const x = (event.clientX / window.innerWidth) * 2 - 1;
      mouseX.set(x);
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [mouseX]);

  return (
    <motion.div style={{ transformOrigin: "center", transform: matrixTransform }}>
      <MarqueeContent />
    </motion.div>
  );
}

export default function Footer() {
  const t = useTranslations("footer");

  const FOOTER_LINKS = [
    { href: "/" as const, label: t("home") },
    { href: "/products" as const, label: t("products") },
    { href: "/services" as const, label: t("services") },
    { href: "/intake" as const, label: t("startProject") },
    { href: "/blog" as const, label: t("blog") },
    { href: "/about" as const, label: t("about") },
    { href: "/faq" as const, label: t("faq") },
    { href: "/contact" as const, label: t("contact") },
  ];

  const linkGroups = [
    { title: t("ourLinks"), links: FOOTER_LINKS.slice(0, 4) },
    { title: t("ourLinks"), links: FOOTER_LINKS.slice(4) },
  ];

  const linkClass =
    "text-muted-foreground hover:text-primary text-sm duration-150 tracking-[-0.01em]";

  return (
    <footer className="dusk border-t border-[var(--border)] bg-[var(--background)] overflow-hidden">
      {/* SILKDEV Marquee with 3D mouse-skew */}
      <div className="w-full overflow-hidden border-b border-[var(--border)]">
        <MarqueeText />
      </div>

      {/* Dusk-style footer grid */}
      <div className="mx-auto max-w-7xl px-6 pb-16 pt-16">
        <div className="grid grid-cols-2 gap-x-3 gap-y-12 sm:grid-cols-4 lg:grid-cols-5">
          {/* Brand */}
          <div className="max-lg:col-span-full">
            <TransitionLink
              href="/"
              aria-label="go home"
              className="text-[22px] font-semibold tracking-tight text-foreground hover:text-[var(--accent)] transition-colors font-['Drystick',system-ui,sans-serif]"
            >
              SILKDEV
            </TransitionLink>
            <p className="mt-4 max-w-xs text-sm text-muted-foreground leading-relaxed tracking-[-0.01em]">
              {t("description")}
            </p>
          </div>

          {/* Link groups */}
          {linkGroups.map((group, gi) => (
            <div key={gi}>
              <span className="text-sm font-medium text-foreground">{group.title}</span>
              <ul className="mt-4 list-inside space-y-4">
                {group.links.map((link) => (
                  <li key={link.href}>
                    <TransitionLink
                      href={link.href}
                      onClick={
                        link.href === "/intake"
                          ? (e: React.MouseEvent) => { e.preventDefault(); openChat(); }
                          : undefined
                      }
                      className={linkClass}
                    >
                      {link.label}
                    </TransitionLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {/* Legal */}
          <div>
            <span className="text-sm font-medium text-foreground">{t("legal")}</span>
            <ul className="mt-4 list-inside space-y-4">
              <li>
                <TransitionLink href="/terms" className={linkClass}>
                  {t("terms")}
                </TransitionLink>
              </li>
              <li>
                <TransitionLink href="/privacy" className={linkClass}>
                  {t("privacy")}
                </TransitionLink>
              </li>
            </ul>
          </div>

          {/* Contact + socials */}
          <div>
            <span className="text-sm font-medium text-foreground">{t("getInTouch")}</span>
            <ul className="mt-4 list-inside space-y-4">
              <li>
                <a
                  href="mailto:contact@silkdev.com.tn"
                  className="text-muted-foreground hover:text-primary text-sm duration-150 tracking-[-0.01em]"
                >
                  {t("contactEmail")}
                </a>
              </li>
              <li className="text-muted-foreground text-sm leading-relaxed tracking-[-0.01em]">
                {t("address1")}
                <br />
                {t("address2")}
              </li>
              <li className="text-muted-foreground text-sm tracking-[-0.01em]">{t("hours")}</li>
              <li className="flex gap-4 pt-2">
                {SOCIAL_LINKS.map((social) => (
                  <a
                    key={social.label}
                    href={social.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-muted-foreground hover:text-primary text-sm duration-150 tracking-[-0.01em]"
                  >
                    {t(social.label as "fb")}
                  </a>
                ))}
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-12 flex flex-col items-start justify-between gap-4 border-t border-[var(--border)] pt-8 md:flex-row md:items-center">
          <p className="text-xs text-muted-foreground tracking-[-0.01em]">
            {t("copyright", { year: new Date().getFullYear() })}
          </p>
          <button
            type="button"
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="text-muted-foreground hover:text-primary flex items-center gap-1.5 text-xs uppercase tracking-[0.05em] btn-press transition-colors"
          >
            {t("backToTop")}
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
            </svg>
          </button>
        </div>
      </div>
    </footer>
  );
}
