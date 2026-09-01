/**
 * The curtain itself: a full-viewport SVG whose single path is morphed by `lib/page-transition.ts`.
 *
 * A **server** component, unlike the version this is ported from. It has no state, no effects and
 * no handlers — every property that ever changes is written imperatively by GSAP against the three
 * ids below. Marking it `"use client"` would ship it and its markup to the browser twice for no
 * behaviour, and this is the one element that must be in the very first HTML: it lives in the
 * layout precisely so it survives every navigation without remounting.
 *
 * `visibility: hidden` inline rather than in a class, because GSAP writes the same inline property
 * to reveal it — a class would win on the first frame and the curtain would never appear.
 *
 * `z-100`: above the header (`z-50`) and anything the pages themselves stack, which is the whole
 * point of a curtain. Nothing on this site goes higher.
 *
 * `aria-hidden`: the transition is decoration over a route change the router already announces.
 * A screen reader reading the destination name off the sheet would announce every page twice.
 */
export function PageTransitionOverlay() {
  return (
    <div
      id="azm-curtain"
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-100 overflow-hidden"
      style={{ visibility: "hidden" }}
    >
      <svg
        className="absolute inset-0 size-full"
        viewBox="0 0 100 100"
        /*
          `none` — the curve is a full-bleed sheet, not a shape whose proportions carry meaning.
          Preserving the aspect ratio would letterbox it on any viewport that is not square.
        */
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="azm-curtain-fill" x1="0%" y1="0%" x2="100%" y2="100%">
            {/* `{colors.primary}` into `{colors.brand-dark-900}` — the brand's own two darks. */}
            <stop offset="0%" stopColor="#533afd" />
            <stop offset="100%" stopColor="#1c1e54" />
          </linearGradient>
        </defs>
        <path
          id="azm-curtain-path"
          d="M 0,120 Q 50,135 100,120 L 100,100 Q 50,85 0,100 Z"
          fill="url(#azm-curtain-fill)"
        />
      </svg>

      <div className="absolute inset-0 flex items-center justify-center px-6">
        <span
          id="azm-curtain-label"
          /*
            `azm-display` — weight 300 with negative tracking. The destination's name is set in the
            brand's display tier because that is the only type on this site large enough to be read
            in the half-second it is on screen, and rendering it at weight 600 (the upstream value)
            would be the one place the brand's editorial weight is contradicted.
          */
          className="azm-display text-center text-4xl text-white opacity-0 sm:text-6xl"
        />
      </div>
    </div>
  );
}
