import { cn } from "@workspace/ui/lib/utils"

/**
 * The Azmoth monogram, as a shape that takes `currentColor`.
 *
 * ## Why this exists as its own file
 *
 * Two screens need the mark and neither may import the other's module. The sidebar's `Wordmark`
 * lives in `layout/app-shell.tsx`, which is a client component carrying the whole navigation, and
 * `auth/auth-shell.tsx` says at length why it will not pull that in for a few characters of markup:
 * `/login` must not ship the sidebar. So the shared piece is this — no `"use client"`, no imports
 * beyond `cn`, nothing either screen would rather not have.
 *
 * Both of them previously rendered an `AZ` tile in `bg-primary`, a placeholder from before the brand
 * existed. This replaces it in both.
 *
 * ## Why a CSS mask rather than an `<img>`
 *
 * The artwork is a raster — every export of the monogram is a 2676x1492 PNG inside an `<svg>`
 * wrapper, which is why `brand/` is not served and `scripts/build-brand-assets.mjs` emits a trimmed
 * 192 px PNG instead. A raster cannot take `currentColor`, and this application has a dark theme: an
 * `<img>` monogram would stay near-black on the dark sidebar and disappear.
 *
 * Painting it as a `mask-image` over `background-color: currentColor` uses only the file's alpha
 * channel, so the mark is whatever colour its surface says — light theme, dark theme, a muted
 * variant, the indigo of a hover state — from one file. The alternative is a white copy alongside the
 * dark one and a rule about which surface gets which, which is two files to keep in step and a bug
 * the first time somebody adds a third surface.
 *
 * `-webkit-mask-image` is set alongside the standard property: some Safari versions still need the
 * prefix, and a mark that renders as a filled square is worse than one that renders in the wrong
 * shade.
 */
export function AzmothMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("shrink-0 bg-current", className)}
      style={{
        maskImage: "url(/brand/azmoth-mark.png)",
        WebkitMaskImage: "url(/brand/azmoth-mark.png)",
        maskSize: "contain",
        WebkitMaskSize: "contain",
        maskRepeat: "no-repeat",
        WebkitMaskRepeat: "no-repeat",
        maskPosition: "center",
        WebkitMaskPosition: "center",
      }}
    />
  )
}
