import type { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";

/**
 * The curved-sheet page transition — a coloured curtain that sweeps up over the page, names where
 * the visitor is going, and lifts away to reveal it.
 *
 * Ported from `silkdev-website`, with three changes, one of which is the reason it is viable on a
 * site whose brief says the Lighthouse score is non-negotiable.
 *
 * ## 1. GSAP is loaded on the first navigation, not on the first paint
 *
 * The animation is an SVG path morph — interpolating the `d` attribute between two cubic curves —
 * and that is genuinely GSAP's job rather than something to reimplement. `motion` (already in this
 * bundle for the scroll reveals) animates numbers and transforms; it does not interpolate path
 * data, so "just use the library we already have" would mean hand-rolling a path interpolator to
 * save a dependency.
 *
 * What it does not have to be is *in the entry bundle*. GSAP's core is ~23 kB gzipped and the
 * home page's Largest Contentful Paint has no use for it, so both entry points below `await
 * import("gsap")` at call time. The first curtain therefore costs a chunk fetch; every subsequent
 * one is warm. On a marketing site — where a large share of visitors read one page and leave — the
 * majority never download it at all.
 *
 * ## 2. The curtain does not play on a cold load
 *
 * The upstream template calls `animatePageIn()` on every mount, including the first. On a cold
 * load that means the visitor's first frame is a full-screen indigo sheet that then lifts to
 * reveal the page they asked for — a 1.4-second delay in front of the content, and a Largest
 * Contentful Paint measured against the curtain rather than against the hero.
 *
 * A transition is a *transition*: it needs a previous page to leave. `outbound` records that
 * `animatePageOut` ran, and page-in no-ops unless it did. This is also what makes the lazy import
 * above pay off — with no click there is no navigation, so GSAP is never fetched.
 *
 * ## 3. It yields to `prefers-reduced-motion`
 *
 * A full-screen sheet sweeping across the viewport is exactly the vestibular trigger the media
 * query exists for. When it is set, `animatePageOut` navigates immediately and page-in does
 * nothing — the visitor gets an ordinary instant route change, which is the correct behaviour and
 * not a degraded one.
 */

/** The DOM contract with `page-transition-overlay.tsx`. Ids, because GSAP tweens raw elements. */
const CURTAIN_ID = "azm-curtain";
const CURVE_ID = "azm-curtain-path";
const LABEL_ID = "azm-curtain-label";

/**
 * The four path states, as a bottom-anchored curve travelling up the viewport.
 *
 * Each is `M → Q → L → Q → Z` with identical command counts, which is what lets the `d` attribute
 * be interpolated at all — GSAP tweens the numbers in place and cannot reconcile two paths with
 * different structures.
 */
const CURVE = {
  /** Bulging just off the bottom edge: the resting state before a page-out. */
  belowViewport: "M 0,120 Q 50,135 100,120 L 100,100 Q 50,85 0,100 Z",
  /** Covering the viewport, with a slight bow top and bottom. */
  covering: "M 0,0 Q 50,-15 100,0 L 100,100 Q 50,115 0,100 Z",
  /** Swept off the top edge: the end of a page-in. */
  aboveViewport: "M 0,-100 Q 50,-115 100,-100 L 100,0 Q 50,15 0,0 Z",
} as const;

/**
 * Set by `animatePageOut`, read and cleared by `animatePageIn`.
 *
 * Module scope survives a client-side navigation (same document, same module instance) but not a
 * full page load — which is precisely the distinction being drawn, so it needs no storage.
 */
let outbound = false;

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** The three overlay nodes, or `null` if the overlay is not mounted (it lives in the layout). */
function elements() {
  const curtain = document.getElementById(CURTAIN_ID);
  const curve = document.getElementById(CURVE_ID);
  const label = document.getElementById(LABEL_ID);
  if (!curtain || !curve || !label) return null;
  return { curtain, curve, label };
}

/**
 * Draw the curtain up over the current page, then navigate.
 *
 * The router push happens in the timeline's `.call()` rather than immediately: pushing first lets
 * the destination render behind a curtain that is still rising, so the visitor sees the new page
 * flash at the edges of the old one.
 */
export async function animatePageOut(href: string, router: AppRouterInstance) {
  if (prefersReducedMotion()) {
    router.push(href);
    return;
  }

  const nodes = elements();
  if (!nodes) {
    router.push(href);
    return;
  }

  const { default: gsap } = await import("gsap");
  outbound = true;

  gsap
    .timeline()
    .set(nodes.curtain, { visibility: "visible" })
    .set(nodes.curve, { attr: { d: CURVE.belowViewport } })
    .set(nodes.label, { opacity: 0, scale: 0.94 })
    .to(nodes.curve, {
      attr: { d: CURVE.covering },
      duration: 0.6,
      ease: "power3.out",
    })
    .call(() => router.push(href));
}

/**
 * Reveal the destination: hold the name for a beat, then lift the sheet off the top.
 *
 * Called from the route template, which remounts on every navigation. The `outbound` guard is what
 * keeps it from firing on a cold load — see the module header.
 *
 * `killTweensOf` first: a visitor who clicks a second link while the first curtain is still rising
 * would otherwise have two timelines writing the same `d` attribute on alternate frames.
 */
export async function animatePageIn() {
  if (!outbound) return;
  outbound = false;

  if (prefersReducedMotion()) return;

  const nodes = elements();
  if (!nodes) return;

  const { default: gsap } = await import("gsap");
  gsap.killTweensOf([nodes.curve, nodes.label]);

  gsap
    .timeline()
    .set(nodes.curtain, { visibility: "visible" })
    .set(nodes.curve, { attr: { d: CURVE.covering } })
    .set(nodes.label, { opacity: 0, y: 24 })
    .to(nodes.label, { opacity: 1, y: 0, duration: 0.5, ease: "power3.out" })
    .to(nodes.label, {
      opacity: 0,
      y: -40,
      duration: 0.4,
      ease: "power2.in",
    })
    .to(
      nodes.curve,
      { attr: { d: CURVE.aboveViewport }, duration: 0.6, ease: "power3.in" },
      /*
        "<" — start with the label's exit rather than after it. Sequentially the whole transition
        runs 1.5s, which is long enough that a visitor who has seen it twice starts waiting for it.
        Overlapping the two brings it to 1.1s and reads as one gesture instead of two.
      */
      "<"
    )
    /*
      Back to `hidden`, not left visible-but-offscreen. The overlay is `fixed inset-0`; a
      `pointer-events-none` element still participates in hit-testing for its own descendants and,
      more to the point, an always-composited full-viewport SVG is a layer the browser keeps alive
      for the rest of the session.
    */
    .set(nodes.curtain, { visibility: "hidden" });
}
