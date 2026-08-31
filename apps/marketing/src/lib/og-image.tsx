import { ImageResponse } from "next/og";

import { AZMOTH_MARK_DATA_URI } from "@/lib/brand-mark";
import { siteConfig } from "@/lib/site";

/**
 * The Open Graph card, drawn rather than stored.
 *
 * A PNG committed to `public/` is a file somebody has to remember to regenerate
 * when the tagline changes, and the one that shipped with the template was the
 * original author's artwork. This renders from the same `siteConfig` strings the
 * pages use, so the card and the site cannot disagree.
 *
 * **It now carries the mark.** The card used to be deliberately typographic because
 * there was no logo to embed; there is one, and a social preview without it is the
 * one place the brand is guaranteed to be seen by somebody who has never heard of
 * us. It arrives as a bundled data URI (`brand-mark.ts`) rather than a URL Satori
 * would have to fetch — the note below about a fetch failing applies just as much to
 * an image as to a font, and an OG route that 500s when a CDN blinks is a preview
 * that silently stops working.
 *
 * Still no font over the network at request time (a fetch that fails takes the whole
 * route with it), so the type is the platform's own sans. The colours are the light
 * palette's literal values — `oklch()` and CSS custom properties are not available in
 * Satori, which is what renders this.
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
        {/*
          The mark, at the top where a masthead goes, with the rule beside it. Satori
          supports a subset of flexbox and no `gap` on some versions, so the spacing is a
          margin rather than a gap — a card that renders with the two elements touching
          is not worth the tidier property.
        */}
        <div style={{ display: "flex", alignItems: "center" }}>
          <img
            src={AZMOTH_MARK_DATA_URI}
            width={72}
            height={72}
            alt=""
            style={{ marginRight: 24 }}
          />
          <div style={{ display: "flex", width: 96, height: 8, backgroundColor: BLUE }} />
        </div>

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
