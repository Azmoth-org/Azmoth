"use client";

import { useEffect } from "react";

/**
 * Lenis, the inertial scroll that gives the page its weight.
 *
 * This is the one thing on the site that overrides a browser default the visitor did not ask to
 * have overridden, so the conditions it declines to run under matter more than the configuration
 * it runs with.
 *
 * ## It does not run at all when the visitor has asked for less motion
 *
 * Hijacked scrolling is the canonical `prefers-reduced-motion` offender: the page keeps moving
 * after the wheel stops, which for a vestibular-sensitive reader is the symptom, not the polish.
 * The check happens *before* construction rather than by stopping an instance afterwards — Lenis
 * sets `overflow: hidden` on the document and drives scroll from a rAF loop, so an instance that
 * exists but is stopped still owns the scroll container.
 *
 * ## It is loaded on idle, not on mount
 *
 * `import("lenis")` inside the effect, behind `requestIdleCallback`. Smooth scrolling is by
 * definition something that matters only once the visitor has begun to read, so it has no business
 * competing with the hero's Largest Contentful Paint for main-thread time. Until the chunk lands
 * the page scrolls natively, which is not a degraded state — it is simply scrolling.
 *
 * ## `autoRaf`, and what replaced the manual anchor handling
 *
 * The version this is ported from binds a document-level click listener, filters for `href^="#"`,
 * calls `preventDefault()` and drives `lenis.scrollTo` itself. Lenis has shipped `anchors` since
 * 1.1 and does the same job without a listener that sees every click on the page — including the
 * ones the navigation's transition links need to keep. Two handlers racing for the same click is
 * how an anchor inside a menu ends up both scrolling and navigating.
 *
 * `offset: -80` on those anchors clears the fixed header, matching the `scroll-padding-top` the
 * stylesheet sets for the native path.
 */
export function SmoothScroll() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let lenis: { destroy: () => void } | undefined;
    let cancelled = false;

    async function start() {
      /*
       * A failed chunk here is genuinely harmless — the page keeps its native scroll, which is the
       * same state it was in a moment ago. It is caught anyway so it does not surface as an
       * unhandled rejection: a red line in the console of a site whose pitch is "everything we do
       * is inspectable" costs more than the four lines it takes to swallow.
       */
      const Lenis = await import("lenis")
        .then((m) => m.default)
        .catch(() => null);
      if (!Lenis) return;
      // The effect may have torn down while the chunk was in flight — a fast route change on a
      // slow connection is the ordinary way this happens, and without the guard the instance is
      // created after its own cleanup has already run and never gets destroyed.
      if (cancelled) return;

      lenis = new Lenis({
        /*
         * `lerp` rather than `duration`. `duration` fixes how long *any* scroll takes, so a flick
         * down one section and a drag to the footer both settle in 1.2s — the long one feels
         * sluggish and the short one feels floaty. `lerp` is a per-frame approach rate, which
         * makes settling time proportional to distance. 0.1 is close to the stock feel; higher
         * reads as no smoothing at all, lower as syrup.
         */
        /*
         * **`autoRaf` is not optional here, and its default is a trap.**
         *
         * Lenis takes over the wheel — it calls `preventDefault` and advances an interpolated
         * scroll position itself, one step per animation frame. `autoRaf` is what registers that
         * frame loop. It defaults to `false`, on the reasonable assumption that an app with GSAP
         * or a scroll library of its own already has a ticker to drive `lenis.raf(time)` from.
         *
         * This one does not. Without either, Lenis still intercepts every wheel event and still
         * suppresses the browser's own scrolling, but nothing ever moves the page: the site is
         * frozen, with no error in the console, and it looks exactly like a hang. Dropping this
         * line while reorganising the config is what shipped that.
         *
         * It is also invisible to programmatic testing — `window.scrollTo` still works, because
         * that path does not go through the wheel handler. Only a real wheel event shows it.
         */
        autoRaf: true,
        lerp: 0.1,
        smoothWheel: true,
        /*
         * Touch is left alone deliberately. Native momentum scrolling on iOS and Android is
         * tuned by the platform, runs off the main thread, and is what every other application on
         * the device does; replacing it with a JS rAF loop is measurably worse on a mid-range
         * phone and is the single most common reason a "smooth scroll" site feels broken on
         * mobile.
         */
        syncTouch: false,
        anchors: { offset: -80 },
      });
    }

    /*
     * `requestIdleCallback` where it exists, a short timeout where it does not — Safari only
     * shipped it in 17.4, and a site whose audience opens it on a work Mac cannot assume that.
     * The fallback is not equivalent (a timeout fires whether or not the main thread is free) but
     * 400ms is past the hero's paint either way, which is the property being bought here.
     */
    const supportsIdle = typeof window.requestIdleCallback === "function";
    const handle = supportsIdle
      ? window.requestIdleCallback(() => void start(), { timeout: 2000 })
      : window.setTimeout(() => void start(), 400);

    return () => {
      cancelled = true;
      if (supportsIdle) window.cancelIdleCallback(handle);
      else window.clearTimeout(handle);
      lenis?.destroy();
    };
  }, []);

  return null;
}
