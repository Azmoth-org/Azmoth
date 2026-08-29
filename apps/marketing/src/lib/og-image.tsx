import { ImageResponse } from "next/og";

import { siteConfig } from "@/lib/site";

/**
 * The Open Graph card, drawn rather than stored.
 *
 * A PNG committed to `public/` is a file somebody has to remember to regenerate
 * when the tagline changes, and the one that shipped with the template was the
 * original author's artwork. This renders from the same `siteConfig` strings the
 * pages use, so the card and the site cannot disagree.
 *
 * Deliberately typographic: no logo file to embed, no font to fetch over the
 * network at build time (a fetch that fails takes the whole route with it). The
 * colours are the light palette's literal values — `oklch()` and CSS custom
 * properties are not available in Satori, which is what renders this.
 */
export const OG_SIZE = { width: 1200, height: 630 };
export const OG_CONTENT_TYPE = "image/png";

const INK = "#101828"; // gray-900, --foreground
const MUTED = "#4a5565"; // gray-600, --muted-foreground
const BLUE = "#1447e6"; // blue-600, --primary
const PAPER = "#f9fafb"; // gray-50, --background

export function renderOgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          backgroundColor: PAPER,
          padding: "72px 80px",
          fontFamily: "sans-serif",
        }}
      >
        {/* A rule in the brand blue, so the card is not a slab of text. */}
        <div style={{ display: "flex", width: 96, height: 8, backgroundColor: BLUE }} />

        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              fontSize: 76,
              fontWeight: 700,
              letterSpacing: "-0.03em",
              color: INK,
              lineHeight: 1.05,
            }}
          >
            {siteConfig.name}
          </div>
          <div
            style={{
              marginTop: 16,
              fontSize: 40,
              fontWeight: 600,
              letterSpacing: "-0.02em",
              color: BLUE,
            }}
          >
            {siteConfig.tagline}
          </div>
          <div
            style={{
              marginTop: 28,
              fontSize: 27,
              color: MUTED,
              lineHeight: 1.4,
              maxWidth: 900,
            }}
          >
            Mathematische Gewissheit für die medizinische Abrechnung. Keine Blackbox,
            keine KI-Halluzinationen.
          </div>
        </div>

        <div style={{ display: "flex", fontSize: 24, color: MUTED }}>
          100% nachvollziehbare GOÄ-Compliance
        </div>
      </div>
    ),
    OG_SIZE
  );
}
