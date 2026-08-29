"use client";

import { useState, useEffect } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import { Link } from "@/i18n/navigation";
import { TransitionLink } from "@/components/TransitionLink";
import { usePathname } from "next/navigation";
import NextLink from "next/link";

const LOCALES = [
  { code: "en", label: "langEn" },
  { code: "fr", label: "langFr" },
] as const;

function stripLocale(path: string, locale: string): string {
  if (path === `/${locale}` || path === `/${locale}/`) return "/";
  if (path.startsWith(`/${locale}/`)) return path.slice(3);
  return path;
}

export default function Navigation() {
  const t = useTranslations("navigation");
  const locale = useLocale();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [visible, setVisible] = useState(true);
  const [langOpen, setLangOpen] = useState(false);
  const pathname = usePathname();

  // Keep the nav on-screen while the mobile menu is open — otherwise a stray
  // scroll event during the tap hides the nav and swallows the toggle.
  const showNav = mobileOpen || visible;

  const basePath = stripLocale(pathname, locale);

  const NAV_LINKS = [
    { href: "/" as const, label: t("home") },
    { href: "/products" as const, label: t("products") },
    { href: "/services" as const, label: t("services") },
    { href: "/blog" as const, label: t("blog") },
    { href: "/about" as const, label: t("about") },
    { href: "/faq" as const, label: t("faq") },
    { href: "/contact" as const, label: t("contact") },
  ];

  const openChat = () => window.dispatchEvent(new CustomEvent("silkdev:open-chat"));

  useEffect(() => {
    let lastScrollY = 0;

    const handleScroll = () => {
      const currentScroll = window.scrollY;
      const delta = currentScroll - lastScrollY;

      setScrolled(currentScroll > 50);

      // At the top: always show (takes precedence over a final downward
      // momentum/overshoot tick that would otherwise leave the nav hidden).
      if (currentScroll < 80) {
        setVisible(true);
      } else if (delta > 0) {
        // Scrolling down — hide
        setVisible(false);
      } else if (delta < 0) {
        // Scrolling up — show
        setVisible(true);
      }

      lastScrollY = currentScroll;
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  const isActive = (href: string) => (href === "/" ? basePath === "/" : basePath === href);

  return (
    <>
      <nav
        className={`dusk fixed top-0 left-0 right-0 z-50 ${
          scrolled && !mobileOpen ? "nav-glass shadow-lg shadow-black/20" : ""
        } ${showNav ? "translate-y-0" : "-translate-y-[120px]"}`}
        style={{
          transition:
            "color 200ms, background-color 200ms, border-color 200ms, box-shadow 200ms, transform 400ms cubic-bezier(0.23,1,0.32,1)",
        }}
      >
        <div className="mx-auto max-w-7xl px-6">
          <div className="flex h-16 items-center justify-between gap-6">
            {/* Logo */}
            <TransitionLink
              href="/"
              aria-label="home"
              className="flex items-center text-[22px] font-semibold tracking-tight text-foreground transition-colors hover:text-[var(--accent)] font-['Drystick',system-ui,sans-serif]"
            >
              SILKDEV
            </TransitionLink>

            {/* Desktop: links + dusk buttons + language */}
            <div className="hidden items-center gap-8 lg:flex">
              <ul className="flex gap-8 text-sm">
                {NAV_LINKS.map((item) => (
                  <li key={item.href}>
                    <TransitionLink
                      href={item.href}
                      className={`block duration-150 ${
                        isActive(item.href)
                          ? "text-[var(--accent)]"
                          : "text-muted-foreground hover:text-accent-foreground"
                      }`}
                    >
                      <span>{item.label}</span>
                    </TransitionLink>
                  </li>
                ))}
              </ul>

              <div className="flex items-center gap-3">
                {/* Portal — dusk outline button */}
                <TransitionLink
                  href="/dashboard"
                  className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full bg-foreground/5 px-5 py-2 text-sm font-medium text-foreground ring-1 ring-foreground/10 duration-200 hover:bg-muted/50"
                >
                  {t("portal")}
                </TransitionLink>

                {/* Start a project — dusk primary button */}
                <button
                  type="button"
                  onClick={openChat}
                  className="inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-full bg-primary px-5 py-2 text-sm font-medium text-primary-foreground duration-200 hover:bg-primary/90"
                >
                  {t("intake")}
                </button>

                {/* Language switcher */}
                <div className="relative">
                  <button
                    onClick={() => setLangOpen(!langOpen)}
                    className="inline-flex cursor-pointer items-center gap-1.5 px-3 py-2 text-[13px] font-medium uppercase tracking-[0.05em] text-muted-foreground duration-150 hover:text-accent-foreground"
                  >
                    {locale.toUpperCase()}
                    <svg
                      className={`h-3 w-3 transition-transform duration-150 ${langOpen ? "rotate-180" : ""}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {langOpen && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setLangOpen(false)} />
                      <div className="absolute right-0 top-full z-20 mt-1 min-w-[120px] rounded-xl border border-[var(--border)] bg-[var(--surface)] py-1 shadow-xl">
                        {LOCALES.map((l) => {
                          const localeHref = `/${l.code}${basePath === "/" ? "" : basePath}`;
                          return (
                            <NextLink
                              key={l.code}
                              href={localeHref}
                              className={`flex items-center gap-2 px-4 py-2 text-[13px] font-medium uppercase tracking-[0.05em] duration-150 ${
                                l.code === locale
                                  ? "bg-[var(--accent)]/10 text-[var(--accent)]"
                                  : "text-muted-foreground hover:bg-white/5 hover:text-accent-foreground"
                              }`}
                              onClick={() => setLangOpen(false)}
                            >
                              {t(l.label)}
                            </NextLink>
                          );
                        })}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Mobile hamburger — 44px touch target, always visible on <lg */}
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label={mobileOpen ? "Close Menu" : "Open Menu"}
              aria-expanded={mobileOpen}
              className="relative z-20 flex h-11 w-11 items-center justify-center lg:hidden"
            >
              <div className="flex flex-col gap-1.5">
                <span
                  className={`block h-[1.5px] w-6 bg-white transition-all duration-200 ${
                    mobileOpen ? "translate-y-[3.5px] rotate-45" : ""
                  }`}
                />
                <span className={`block h-[1.5px] w-6 bg-white transition-all duration-200 ${mobileOpen ? "opacity-0" : ""}`} />
                <span
                  className={`block h-[1.5px] w-6 bg-white transition-all duration-200 ${
                    mobileOpen ? "-translate-y-[3.5px] -rotate-45" : ""
                  }`}
                />
              </div>
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile drawer */}
      <div
        className={`fixed inset-0 z-40 transition-opacity duration-200 lg:hidden ${
          mobileOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
        }`}
        style={{
          background: "rgba(28, 31, 52, 0.77)",
          backdropFilter: "blur(4px)",
          WebkitBackdropFilter: "blur(4px)",
        }}
        onClick={() => setMobileOpen(false)}
      >
        <div
          className="absolute right-0 top-0 flex h-full w-[85%] max-w-[320px] flex-col bg-[var(--surface)] border-l border-[var(--border)] p-8 pt-[100px] transition-transform duration-300"
          style={{
            transform: mobileOpen ? "translateX(0)" : "translateX(100%)",
            transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
            visibility: mobileOpen ? "visible" : "hidden",
            transitionProperty: "transform, visibility",
            transitionDuration: mobileOpen ? "300ms" : "200ms",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Links */}
          <div className="flex flex-col gap-1 overflow-y-auto">
            {NAV_LINKS.map((link) => (
              <TransitionLink
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className={`rounded-lg px-4 py-3 text-lg font-medium uppercase tracking-[-0.01em] transition-colors duration-150 btn-press ${
                  isActive(link.href)
                    ? "bg-[var(--accent)]/10 text-[var(--accent)]"
                    : "text-[var(--muted)] hover:bg-white/5 hover:text-white"
                }`}
              >
                {link.label}
              </TransitionLink>
            ))}
          </div>

          {/* CTAs */}
          <div className="mt-6 flex flex-col gap-3">
            <TransitionLink
              href="/dashboard"
              onClick={() => setMobileOpen(false)}
              className="inline-flex items-center justify-center rounded-full bg-foreground/5 px-5 py-3 text-sm font-medium text-foreground ring-1 ring-foreground/10 duration-200 hover:bg-muted/50"
            >
              {t("portal")}
            </TransitionLink>
            <button
              type="button"
              onClick={() => {
                setMobileOpen(false);
                openChat();
              }}
              className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-5 py-3 text-sm font-medium text-primary-foreground duration-200 hover:bg-primary/90"
            >
              {t("intake")}
            </button>
          </div>

          {/* Language switcher */}
          <div className="mt-6 border-t border-[var(--border)] pt-6">
            <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.1em] text-[var(--muted)]">
              {t("language")}
            </p>
            <div className="flex gap-2">
              {LOCALES.map((l) => (
                <NextLink
                  key={l.code}
                  href={`/${l.code}${basePath === "/" ? "" : basePath}`}
                  onClick={() => setMobileOpen(false)}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-[13px] font-medium uppercase tracking-[0.05em] transition-colors duration-150 btn-press ${
                    l.code === locale
                      ? "border-[var(--accent)]/20 bg-[var(--accent)]/10 text-[var(--accent)]"
                      : "border-transparent text-[var(--muted)] hover:bg-white/5 hover:text-white"
                  }`}
                >
                  {t(l.label)}
                </NextLink>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
