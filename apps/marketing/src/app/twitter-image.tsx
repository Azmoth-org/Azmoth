import { OG_CONTENT_TYPE, OG_SIZE, renderOgImage } from "@/lib/og-image";

/**
 * The same card as `opengraph-image`. Next does not fall back from one convention
 * to the other, so a site with only an `opengraph-image` emits no `twitter:image`
 * at all and X renders a bare text card.
 */
export const alt = "Azmoth – Deterministische GOÄ-Prüfengine";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function TwitterImage() {
  return renderOgImage();
}
