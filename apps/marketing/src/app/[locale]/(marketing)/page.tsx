"use client";

import { openChat } from "@/lib/openChat";
import { BookOpen, Globe, Keyboard, Link2, MessageSquare, Settings2, Sparkles, Workflow, Zap } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import Hero10 from "@/components/Hero10";
import DuskStats from "@/components/DuskStats";
import DuskFeatures from "@/components/DuskFeatures";
import DuskCTA from "@/components/DuskCTA";
import { PRODUCTS } from "@/data/products";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";
import { CustomEase } from "gsap/CustomEase";
import { DrawSVGPlugin } from "gsap/DrawSVGPlugin";
import { ScrambleTextPlugin } from "gsap/ScrambleTextPlugin";
import { ScrollToPlugin } from "gsap/ScrollToPlugin";
import { Observer } from "gsap/Observer";
import { useRef, useState, useCallback, useEffect } from "react";

/* ─── GSAP Plugin Registration ─── */
gsap.registerPlugin(
  ScrollTrigger,
  SplitText,
  CustomEase,
  DrawSVGPlugin,
  ScrambleTextPlugin,
  ScrollToPlugin,
  Observer,
);

/* ─── Custom Easing ─── */
const easeOut = CustomEase.create("ease-out", "0.23, 1, 0.32, 1");

const SERVICES_PREVIEW = [
  { slug: "web-development", labelKey: "Web Dev", accent: "#6c63ff", icon: <Globe className="w-5 h-5" /> },
  { slug: "ai-support-agents", labelKey: "AI Support", accent: "#66e3ff", icon: <MessageSquare className="w-5 h-5" /> },
  { slug: "custom-ai-features", labelKey: "Custom AI", accent: "#f59e0b", icon: <Sparkles className="w-5 h-5" /> },
  { slug: "knowledge-ai", labelKey: "Knowledge AI", accent: "#ec4899", icon: <BookOpen className="w-5 h-5" /> },
  { slug: "automation", labelKey: "Automation", accent: "#22c55e", icon: <Workflow className="w-5 h-5" /> },
  { slug: "fractional-cto", labelKey: "Fractional CTO", accent: "#a78bfa", icon: <Zap className="w-5 h-5" /> },
];
/* ─── Utils ─── */
function clamp(v: number, min: number, max: number) {
  return Math.min(max, Math.max(min, v));
}

/* ─── Components ─── */

function ProductsCarousel({ hoveredIdx, setHoveredIdx }: {
  hoveredIdx: number | null;
  setHoveredIdx: (i: number | null) => void;
}) {
  const homeT = useTranslations("home");
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div ref={ref} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" id="products-grid">
      {PRODUCTS.map((p, i) => {
        const external = p.url.startsWith("http");
        const inner = (
          <>
            {/* Glow blob */}
            <div
              className="absolute -top-16 -right-16 w-32 h-32 rounded-full opacity-0 group-hover:opacity-15 pointer-events-none"
              style={{
                background: p.gradient,
                transition: "opacity 400ms cubic-bezier(0.23,1,0.32,1)",
              }}
            />

            {/* Real product icon */}
            <div
              className="w-11 h-11 rounded-xl flex items-center justify-center mb-4 relative"
              style={{
                background: `${p.accent}18`,
              }}
            >
              {p.iconPath && (
                <img src={p.iconPath} alt={`${p.name} logo`} className="w-8 h-8 object-contain" />
              )}
            </div>

            {/* Meta */}
            <div className="relative">
              <span
                className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-medium tracking-[0.05em] uppercase mb-3"
                style={{
                  background: `${p.accent}15`,
                  color: p.accent,
                }}
              >
                {p.status}
              </span>
              <h3 className="text-[20px] font-bold tracking-[-0.02em] text-white mb-1.5 font-['Manrope',system-ui,sans-serif]">
                {p.name}
              </h3>
              <p className="text-[13px] text-[var(--muted)] leading-[1.5] tracking-[-0.01em]">
                {p.tagline}
              </p>
            </div>

            {/* CTA */}
            <div
              className="mt-4 flex items-center gap-1 text-[13px] font-medium opacity-0 group-hover:opacity-100"
              style={{ color: p.accent, transition: "opacity 200ms ease-out" }}
            >
              <span>{external ? homeT("visitSite") : homeT("servicesCta")}</span>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </>
        );

        const shared =
          "group relative rounded-2xl p-6 overflow-hidden cursor-pointer block text-left product-card";

        return external ? (
          <a
            key={p.name}
            href={p.url}
            target="_blank"
            rel="noopener noreferrer"
            onMouseEnter={() => setHoveredIdx(i)}
            onMouseLeave={() => setHoveredIdx(null)}
            className={shared}
            style={{ background: `var(--surface)`, border: `1px solid var(--border)` }}
            data-accent={p.accent}
            data-gradient={p.gradient}
            data-name={p.name}
            data-tagline={p.tagline}
            data-status={p.status}
          >
            {inner}
          </a>
        ) : (
          <button
            key={p.name}
            type="button"
            onClick={openChat}
            onMouseEnter={() => setHoveredIdx(i)}
            onMouseLeave={() => setHoveredIdx(null)}
            className={shared}
            style={{ background: `var(--surface)`, border: `1px solid var(--border)` }}
            data-accent={p.accent}
            data-gradient={p.gradient}
            data-name={p.name}
            data-tagline={p.tagline}
            data-status={p.status}
          >
            {inner}
          </button>
        );
      })}
    </div>
  );
}

function DecorativePath() {
  return (
    <svg
      className="hidden md:block absolute right-0 top-0 h-full pointer-events-none"
      width="200"
      height="600"
      viewBox="0 0 200 600"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        id="decorative-swoosh"
        d="M160 0 C 160 100, 40 120, 40 200 C 40 280, 180 260, 180 340 C 180 420, 20 400, 20 480 C 20 560, 160 540, 160 600"
        stroke="url(#swoosh-gradient)"
        strokeWidth="1"
        strokeLinecap="round"
        fill="none"
        opacity="0.15"
      />
      <defs>
        <linearGradient id="swoosh-gradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6c63ff" stopOpacity="0" />
          <stop offset="30%" stopColor="#6c63ff" stopOpacity="0.6" />
          <stop offset="70%" stopColor="#ec4899" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#ec4899" stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  );
}

/* ─── Page ─── */
export default function HomePage() {
  const t = useTranslations("home");
  const productsT = useTranslations("common");

  /* Refs for sections */
  const heroRef = useRef<HTMLDivElement>(null);
  const heroHeadingRef = useRef<HTMLHeadingElement>(null);
  const heroTaglineRef = useRef<HTMLParagraphElement>(null);
  const heroCtaRef = useRef<HTMLDivElement>(null);
  const scrollIndicatorRef = useRef<HTMLDivElement>(null);
  const metricsRef = useRef<HTMLDivElement>(null);
  const productsSectionRef = useRef<HTMLDivElement>(null);
  const servicesSectionRef = useRef<HTMLDivElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);
  const decorativePathRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLDivElement>(null);

  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const [bgBlend, setBgBlend] = useState(0);
  const [currentSection, setCurrentSection] = useState(0);

  /* ─── GSAP Timeline ─── */
  /* Gated on the page transition: the homepage's heavy mount work (SplitText
     hero chars, ScrollTriggers, count-ups) runs only after the page-in curtain
     completes — otherwise it contends with the transition on the main thread
     (the "laggy home screen" bug). Falls back to a timeout so the hero is
     never left static. */
  const PAGE_TRANSITION_IN_DONE = "silkdev:page-transition-in-done";

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let cleanupFn: (() => void) | null = null;

    const onDone = () => {
      if (cancelled || cleanupFn) return;
      window.removeEventListener(PAGE_TRANSITION_IN_DONE, onDone);
      window.clearTimeout(timer);
      cleanupFn = setupHomeAnimations();
    };

    if (document.documentElement.dataset.pageTransitionInDone === "true") {
      cleanupFn = setupHomeAnimations();
    } else {
      window.addEventListener(PAGE_TRANSITION_IN_DONE, onDone);
      timer = window.setTimeout(onDone, 2200);
    }

    return () => {
      cancelled = true;
      window.removeEventListener(PAGE_TRANSITION_IN_DONE, onDone);
      window.clearTimeout(timer);
      cleanupFn?.();
    };
  }, []);

  function setupHomeAnimations(): () => void {
    /* ================================================================
       1. HERO — SplitText on heading, stagger chars + fade tagline/CTA
       ================================================================ */
    const heroTl = gsap.timeline({ defaults: { ease: easeOut } });

    // Animate heading via SplitText
    if (heroHeadingRef.current) {
      // We'll split the text into characters with a wrapping approach
      const headingEl = heroHeadingRef.current;
      const split = new SplitText(headingEl, {
        type: "chars",
        charsClass: "hero-char",
      });
      heroTl.fromTo(
        split.chars,
        { opacity: 0, y: 60, rotateX: -30 },
        {
          opacity: 1,
          y: 0,
          rotateX: 0,
          duration: 0.7,
          stagger: 0.025,
          ease: easeOut,
        },
        0,
      );
    }

    // Tagline stagger fade
    if (heroTaglineRef.current) {
      const splitWords = new SplitText(heroTaglineRef.current, {
        type: "lines",
        linesClass: "hero-tagline-line",
      });
      heroTl.fromTo(
        splitWords.lines,
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.5, stagger: 0.12, ease: easeOut },
        0.3,
      );
    }

    // CTA buttons
    if (heroCtaRef.current) {
      const ctas = heroCtaRef.current.children;
      heroTl.fromTo(
        ctas,
        { opacity: 0, y: 15 },
        { opacity: 1, y: 0, duration: 0.5, stagger: 0.1, ease: easeOut },
        0.55,
      );
    }

    // Scroll indicator
    if (scrollIndicatorRef.current) {
      heroTl.fromTo(
        scrollIndicatorRef.current,
        { opacity: 0, y: 10 },
        { opacity: 1, y: 0, duration: 0.5, ease: easeOut },
        1.0,
      );
    }

    /* ================================================================
       2. SCROLLTRIGGER — Metrics Strip => stagger reveal + count-up
       ================================================================ */
    if (metricsRef.current) {
      const metricCards = metricsRef.current.querySelectorAll(".metric-card");
      const metricValues = metricsRef.current.querySelectorAll(".metric-value");

      // Fade up cards
      gsap.fromTo(
        metricCards,
        { opacity: 0, y: 30 },
        {
          opacity: 1,
          y: 0,
          duration: 0.6,
          stagger: 0.1,
          ease: easeOut,
          scrollTrigger: {
            trigger: metricsRef.current,
            start: "top 85%",
            toggleActions: "play none none reverse",
          },
        },
      );
    }

    /* ================================================================
       3. SCROLLTRIGGER — Products Section
       ================================================================ */
    if (productsSectionRef.current) {
      const cards = productsSectionRef.current.querySelectorAll(".product-card");
      gsap.fromTo(
        cards,
        { opacity: 0, y: 30, scale: 0.95 },
        {
          opacity: 1,
          y: 0,
          scale: 1,
          duration: 0.5,
          stagger: 0.08,
          ease: easeOut,
          scrollTrigger: {
            trigger: productsSectionRef.current,
            start: "top 80%",
            toggleActions: "play none none reverse",
          },
        },
      );
    }

    /* ================================================================
       4. SCROLLTRIGGER — Services Section
       ================================================================ */
    if (servicesSectionRef.current) {
      const cards = servicesSectionRef.current.querySelectorAll(".service-card");
      gsap.fromTo(
        cards,
        { opacity: 0, y: 30, scale: 0.95 },
        {
          opacity: 1,
          y: 0,
          scale: 1,
          duration: 0.5,
          stagger: 0.1,
          ease: easeOut,
          scrollTrigger: {
            trigger: servicesSectionRef.current,
            start: "top 80%",
            toggleActions: "play none none reverse",
          },
        },
      );
    }

    /* ================================================================
       6. SCROLLTRIGGER — CTA Section
       ================================================================ */
    if (ctaRef.current) {
      gsap.fromTo(
        ctaRef.current,
        { opacity: 0, y: 30 },
        {
          opacity: 1,
          y: 0,
          duration: 0.7,
          ease: easeOut,
          scrollTrigger: {
            trigger: ctaRef.current,
            start: "top 85%",
            toggleActions: "play none none reverse",
          },
        },
      );
    }

    /* ================================================================
       7. DRAW SVG — Decorative line draws as user scrolls
       ================================================================ */
    if (decorativePathRef.current) {
      const path = document.getElementById("decorative-swoosh");
      if (path) {
        gsap.fromTo(
          path,
          { drawSVG: "0% 0%" },
          {
            drawSVG: "0% 100%",
            duration: 1.5,
            ease: "power2.out",
            scrollTrigger: {
              trigger: decorativePathRef.current,
              start: "top bottom",
              end: "bottom top",
              scrub: 1.5,
            },
          },
        );
      }
    }

    /* ================================================================
       8. OBSERVER — Track which section is in view for bg color blend
       ================================================================ */
    const sections = mainRef.current
      ? Array.from(mainRef.current.querySelectorAll("[data-section]"))
      : [];

    if (sections.length > 0) {
      sections.forEach((section, idx) => {
        ScrollTrigger.create({
          trigger: section,
          start: "top 50%",
          end: "bottom 50%",
          onEnter: () => setCurrentSection(idx),
          onEnterBack: () => setCurrentSection(idx),
        });
      });
    }

    /* ─── Cleanup ─── */
    return () => {
      ScrollTrigger.getAll().forEach((st) => st.kill());
    };
  }

  /* ─── Scroll indicator click ─── */
  const scrollToMetrics = useCallback(() => {
    if (metricsRef.current) {
      gsap.to(window, {
        duration: 0.8,
        scrollTo: { y: metricsRef.current, offsetY: 80 },
        ease: easeOut,
      });
    }
  }, []);

  /* ─── Section colors for bg blend ─── */
  const sectionColors = [
    "hsla(0, 0%, 5%, 1)",
    "hsla(0, 0%, 5%, 1)",
    "hsla(260, 30%, 6%, 1)",
    "hsla(260, 30%, 6%, 1)",
    "hsla(0, 0%, 5%, 1)",
    "hsla(0, 0%, 5%, 1)",
  ];

  return (
    <div ref={mainRef}>
      {/* ─── HERO ─── */}
      <section
        data-section="0"
        ref={heroRef}
        className="relative min-h-screen flex items-center justify-center overflow-hidden"
        style={{
          background: `linear-gradient(180deg, ${sectionColors[0]}, ${sectionColors[1]})`,
        }}
      >
        {/* Ambient glow */}
        <div className="absolute inset-0 opacity-25 pointer-events-none">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full bg-[var(--accent)]/8 blur-[90px]" />
          <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full bg-[var(--accent)]/5 blur-[70px]" />
        </div>

        {/* Grid pattern overlay */}
        <div
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.07) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }}
        />

        <div className="relative z-10 w-full">
          <Hero10 />
        </div>

        {/* Scroll indicator — mouse icon, desktop only */}
        <div
          ref={scrollIndicatorRef}
          className="absolute bottom-8 left-1/2 -translate-x-1/2 cursor-pointer hidden md:block"
          onClick={scrollToMetrics}
        >
          <div className="w-5 h-8 rounded-full border border-[var(--border)] flex items-start justify-center p-1.5">
            <div
              className="w-1 h-2 rounded-full bg-[var(--muted)] scroll-dot"
            />
          </div>
        </div>

        {/* Decorative SVG path */}
        <div ref={decorativePathRef} className="absolute right-0 top-0 h-full w-[200px] hidden md:block">
          <DecorativePath />
        </div>
      </section>

      {/* ─── METRICS ─── */}
      <section
        data-section="1"
        ref={metricsRef}
        className="py-[60px]"
        style={{
          background: `linear-gradient(180deg, ${sectionColors[1]}, ${sectionColors[2]})`,
        }}
      >
        <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
          <DuskStats />
        </div>
      </section>

      {/* ─── SERVICES — the funnel ─── */}
      <section
        data-section="2"
        ref={servicesSectionRef}
        className="py-[80px]"
        style={{
          background: `linear-gradient(180deg, ${sectionColors[2]}, ${sectionColors[3]})`,
        }}
      >
        <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
          <DuskFeatures services={SERVICES_PREVIEW} />
        </div>
      </section>

      {/* ─── OUR PRODUCTS — secondary ─── */}
      <section
        data-section="3"
        ref={productsSectionRef}
        className="py-[80px]"
        style={{
          background: `linear-gradient(180deg, ${sectionColors[3]}, ${sectionColors[4]})`,
        }}
      >
        <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
          <div className="flex items-center gap-3 mb-3">
            <div className="h-px flex-1" style={{ background: "linear-gradient(90deg, transparent, var(--border), transparent)" }} />
            <span className="text-[11px] uppercase tracking-[0.15em] text-[var(--muted)] font-medium">
              {productsT("badgeProducts")}
            </span>
            <div className="h-px flex-1" style={{ background: "linear-gradient(90deg, transparent, var(--border), transparent)" }} />
          </div>
          <h2 className="text-[32px] md:text-[40px] font-bold tracking-[-0.03em] text-white text-center mb-2 font-['Manrope',system-ui,sans-serif]">
            {t("productsTitle")}
          </h2>
          <p className="text-[15px] text-[var(--muted)] text-center mb-10 max-w-md mx-auto tracking-[-0.01em]">
            {t("productsSub")}
          </p>
          <ProductsCarousel hoveredIdx={hoveredIdx} setHoveredIdx={setHoveredIdx} />
        </div>
      </section>

      {/* ─── CTA ─── */}
      <section
        data-section="5"
        ref={ctaRef}
        className="py-[80px]"
        style={{
          background: `linear-gradient(180deg, hsla(0, 0%, 5%, 1) 0%, hsla(260, 30%, 6%, 1) 22%, hsla(260, 35%, 8%, 1) 55%, var(--background) 100%)`,
        }}
      >
        <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
          <DuskCTA />
        </div>
      </section>
    </div>
  );
}
