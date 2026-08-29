"use client";

/**
 * Persistent page-transition overlay — the curved sheet that sweeps over
 * the page during navigation (ported from silklearn-website).
 * Lives in the layout so it never remounts between navigations.
 * z-[9500]: above nav (50) and modals (60), below the custom cursor (9998).
 */
export function PageTransitionOverlay() {
  return (
    <div
      id="curve-transition"
      className="pointer-events-none fixed inset-0 z-[9500] overflow-hidden"
      style={{ visibility: "hidden" }}
    >
      <svg
        id="curve-svg"
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="curveGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#5a52e0" />
            <stop offset="100%" stopColor="#4a44c9" />
          </linearGradient>
        </defs>
        <path
          id="curve-path"
          d="M 0,0 Q 50,-15 100,0 L 100,100 Q 50,115 0,100 Z"
          fill="url(#curveGradient)"
        />
      </svg>

      <div
        id="page-name-display"
        className="absolute inset-0 flex items-center justify-center opacity-0"
      >
        <span
          id="page-name-text"
          className="text-5xl font-semibold tracking-[-0.04em] text-white md:text-6xl"
          style={{ fontFamily: "'Drystick', system-ui, sans-serif" }}
        />
      </div>
    </div>
  );
}
