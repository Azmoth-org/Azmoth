"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@workspace/ui/lib/utils";

/**
 * A number that counts up when it scrolls into view — written against `requestAnimationFrame`
 * rather than against `motion`, and rendering its final value on the server.
 *
 * ## Why not `motion`
 *
 * `motion` is already in this bundle for `components/reveal.tsx`, so reaching for `animate()` and
 * `useMotionValue` here would look like the cheap option. It is not, for one reason that is
 * specific to *this* animation: the thing being tweened is a **German-formatted string**, not a
 * style property. `858` has to pass through `Intl.NumberFormat("de-DE")` on every frame to read
 * "858" rather than "858", and a percentage has to render "96 %" with the non-breaking space the
 * German convention wants. That is a `useTransform` with a formatter closure on every frame, which
 * is the same rAF loop written through three abstractions that exist to drive the compositor —
 * and this animation cannot touch the compositor, because it changes text content and therefore
 * re-lays-out its own line on every frame regardless.
 *
 * Forty lines of rAF costs nothing to ship and does the one thing needed. The rule the rest of
 * this site follows — CSS for what composites, JavaScript only where the platform has no answer —
 * puts this on the JavaScript side either way; it does not also require a library.
 *
 * ## Why `display` is a prop rather than computed here
 *
 * The server renders the finished string, and it must be byte-identical to what the client
 * eventually settles on or React logs a hydration mismatch on a number that is the whole point of
 * the section. `Intl` output is not guaranteed to agree across Node's ICU build and the visitor's
 * browser — percent spacing in particular varies — so the authoritative string is formatted once,
 * on the server, by `lib/engine-facts.ts`, and passed down. The client formats only the
 * *intermediate* frames, where a one-character difference is invisible and lasts 16ms, and snaps
 * to `display` on the final frame.
 *
 * That ordering also decides the no-JavaScript story for free: the markup ships with the real
 * number in it. A crawler, a reader mode, a screen reader running ahead of hydration and a
 * visitor who blocks scripts all see "858", not "0" and not an empty span.
 */

type Format = "integer" | "percent";

/** Intermediate-frame formatting only. The final frame uses the server's string verbatim. */
function formatFrame(value: number, format: Format): string {
  if (format === "percent") {
    return new Intl.NumberFormat("de-DE", {
      style: "percent",
      maximumFractionDigits: 0,
    }).format(value);
  }
  return new Intl.NumberFormat("de-DE").format(Math.round(value));
}

export function CountUp({
  to,
  display,
  format = "integer",
  durationMs = 1200,
  className,
}: {
  /** The target, as a number. For `percent`, a fraction: `0.96`, not `96`. */
  to: number;
  /** The finished string, formatted on the server. Rendered before, and after, the tween. */
  display: string;
  format?: Format;
  durationMs?: number;
  className?: string;
}) {
  const [text, setText] = useState(display);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    /*
     * Reduced motion keeps the server's string and never starts a loop. A count-up is decoration
     * on a number that is already legible — there is nothing here to degrade to, so the correct
     * reduced-motion behaviour is simply the static value, which is what is already rendered.
     */
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;
    let start: number | null = null;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry?.isIntersecting) return;
        /*
         * Once. `IntersectionObserver` fires again on every re-entry, and a number that re-counts
         * each time it scrolls back past reads as a glitch rather than as an effect — the same
         * reasoning as `viewport={{ once: true }}` on the reveals.
         */
        observer.disconnect();

        const step = (now: number) => {
          start ??= now;
          const elapsed = now - start;
          const t = Math.min(elapsed / durationMs, 1);
          /* Cubic ease-out, matching `--ease-brand`'s decelerating character. */
          const eased = 1 - Math.pow(1 - t, 3);

          if (t >= 1) {
            setText(display);
            return;
          }
          setText(formatFrame(to * eased, format));
          frame = requestAnimationFrame(step);
        };

        frame = requestAnimationFrame(step);
      },
      { threshold: 0.4 }
    );

    observer.observe(node);

    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [to, display, format, durationMs]);

  /*
   * `azm-tnum` is not optional here. Proportional digits change width as they tick, so an
   * un-tabular count-up shoves everything after it sideways on every frame — the single most
   * common way this effect is shipped broken. Tabular figures make every frame the same width.
   *
   * `aria-hidden` on the animating span with the real value in a visually hidden sibling: a live
   * region would otherwise announce sixty intermediate numbers, and the only one that means
   * anything is the last.
   */
  return (
    <>
      <span ref={ref} aria-hidden="true" className={cn("azm-tnum tabular-nums", className)}>
        {text}
      </span>
      <span className="sr-only">{display}</span>
    </>
  );
}
