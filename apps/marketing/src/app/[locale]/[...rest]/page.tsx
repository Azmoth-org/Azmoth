import { notFound } from "next/navigation";

/**
 * Catch-all so unmatched URLs (e.g. a link to a page that doesn't exist yet,
 * a removed post, a typo'd path) render inside the [locale] layout instead of
 * the bare root not-found. Matching a real route here means the page
 * transition overlay + template still run, so the reveal always shows a
 * fallback title (never an empty/broken transition). notFound() keeps the
 * response at 404 with the styled [locale]/not-found page.
 */
export default function CatchAllPage() {
  notFound();
}
