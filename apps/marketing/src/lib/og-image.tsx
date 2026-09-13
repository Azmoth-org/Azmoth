import { ImageResponse } from "next/og";

import { AZMOTH_MARK_DATA_URI } from "@/lib/brand-mark";

/**
 * The Open Graph card, drawn rather than stored.
 *
 * A PNG committed to `public/` is a file somebody has to remember to regenerate when the
 * headline changes, and the one that shipped with the template was the original author's
 * artwork. This renders the hero's own headline, so the card and the site cannot disagree.
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
 *
 * **Brand mark and one line of copy — nothing else.** No tagline, no numbers, no date. This
 * card is what a link preview shows on every page this site has, for as long as it is shared —
 * a stat tile below the fold gets a fresh "Stand:" date every time the engine is re-verified
 * (see `lib/engine-facts.ts`), but a cached social-preview image does not get re-fetched on that
 * schedule. A card that baked "944 von 980" or "80 ms" into pixels would go stale exactly like
 * the shipped-prose numbers `engine-facts.ts` exists to prevent, except unfixable without a
 * redeploy and unnoticed until somebody screenshots an old share.
 */
export const OG_SIZE = { width: 1200, height: 630 };
export const OG_CONTENT_TYPE = "image/png";

const INK = "#101828"; // gray-900, --foreground
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
          justifyContent: "center",
          backgroundColor: PAPER,
          padding: "80px",
          fontFamily: "sans-serif",
        }}
      >
        {/*
          The mark, above the line it accompanies. Satori supports a subset of flexbox and no
          `gap` on some versions, so the spacing is a margin rather than a gap.
        */}
        <div style={{ display: "flex", alignItems: "center", marginBottom: 48 }}>
          <img
            src={AZMOTH_MARK_DATA_URI}
            width={72}
            height={72}
            alt=""
            style={{ marginRight: 24 }}
          />
          <div style={{ display: "flex", width: 96, height: 8, backgroundColor: BLUE }} />
        </div>

        <div
          style={{
            display: "flex",
            fontSize: 64,
            fontWeight: 700,
            letterSpacing: "-0.03em",
            color: INK,
            lineHeight: 1.15,
            maxWidth: 1000,
          }}
        >
          Jede Position geprüft. Jeder Befund belegt.
        </div>
      </div>
    ),
    OG_SIZE
  );
}
