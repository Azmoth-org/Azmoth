"use client";

import React from "react";

import { cn } from "@workspace/ui/lib/utils";

/**
 * A slow chromatic drift behind the hero — the moving half of the brand's atmospheric backdrop.
 *
 * ## How it relates to `.azm-mesh`
 *
 * `DESIGN.md` calls the gradient mesh non-negotiable on a marketing hero and it stays: the mesh is
 * the *brand's* colour, static and cheap, and it is what a visitor recognises. This layer sits
 * beneath it and does one thing the mesh cannot, which is move. Together they read as light on a
 * surface; either alone reads as a flat wash or as a screensaver. The stops here are the mesh's
 * own — indigo, lavender, ruby — so the two layers cannot disagree about what colour the brand is.
 *
 * ## Departures from the upstream component
 *
 * **A backdrop, not a page.** Upstream is a `<main>` wrapping a `h-[100vh]` flex container: it is
 * a full-screen layout that happens to have an aurora in it, so using it means giving it your
 * page. This renders an absolutely-positioned decoration and takes no children, which is what lets
 * the hero own its own layout and stack the mesh over the top.
 *
 * **`invert filter` and `mix-blend-difference` are gone.** Upstream reaches its light-mode
 * appearance by rendering the dark-mode gradient and inverting the whole element, then differencing
 * a second copy against it. Two full-viewport filter passes per frame is the single most expensive
 * way to arrive at that image, and on this site it lands directly behind the H1 — the largest
 * contentful paint. Painting the light-mode stops directly costs one composited layer.
 *
 * **Colours resolve through the palette.** Upstream hard-codes eight Tailwind blues as inline CSS
 * variables, which is how a shared component ends up being the one surface in the product that is
 * not the brand's indigo.
 *
 * **Opt-out is real.** The drift is a decorative infinite animation. `prefers-reduced-motion`
 * stops it — the gradient stays, so nothing disappears, it simply holds still. The global backstop
 * in `globals.css` collapses the duration; `motion-reduce:animate-none` here is the explicit half,
 * because an animation "completing" in 0.01ms still leaves it parked at its final frame rather
 * than its authored one.
 *
 * `aria-hidden` and `pointer-events-none`: it is decoration, and it must not sit between a cursor
 * and the call-to-action it washes over.
 */
export function AuroraBackground({
  className,
  /**
   * Masks the drift into an ellipse at the top of the container, matching how `.azm-mesh` fades.
   * Set `false` on a surface that wants the wash edge to edge — a full-bleed dark band, say.
   */
  showRadialGradient = true,
}: {
  className?: string;
  showRadialGradient?: boolean;
}) {
  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}
      style={
        {
          /*
           * Two layers, both driven by the single `aurora` keyframe: a repeating multi-stop band
           * of brand colour, and a repeating white band that breaks it into ribbons. Sliding both
           * at once across different background sizes is what produces the organic interference
           * pattern — a single gradient at any speed only ever reads as a wipe.
           */
          "--aurora":
            "repeating-linear-gradient(100deg, var(--azm-indigo) 10%, var(--azm-indigo-subdued) 15%, var(--azm-indigo-soft) 20%, var(--azm-magenta) 25%, var(--azm-ruby) 30%)",
          "--band":
            "repeating-linear-gradient(100deg, oklch(1 0 0) 0%, oklch(1 0 0) 7%, transparent 10%, transparent 12%, oklch(1 0 0) 16%)",
        } as React.CSSProperties
      }
    >
      <div
        className={cn(
          /*
            `opacity-15`, and the number was arrived at against the mesh rather than on its own.
            The aurora sits *under* `.azm-mesh`, so the two alphas multiply: at the 50 % the
            upstream component ships, the indigo and magenta stops stop being atmosphere and
            become two coloured blobs behind the headline — which is also where the H1's contrast
            ratio starts moving. At 15 % it reads as the light in the mesh shifting, which is the
            entire brief for this layer.
          */
          "animate-aurora absolute -inset-24 opacity-15 blur-[60px] will-change-[background-position] motion-reduce:animate-none",
          "[background-image:var(--band),var(--aurora)] [background-size:300%_200%] [background-position:50%_50%,50%_50%]",
          showRadialGradient &&
            "[mask-image:radial-gradient(ellipse_70%_60%_at_60%_0%,black_10%,transparent_75%)]"
        )}
      />
    </div>
  );
}
