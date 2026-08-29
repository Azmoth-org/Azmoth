import { notFound } from "next/navigation";

/**
 * Catch-all, so an unmatched URL renders the styled 404 inside the site chrome
 * (header, footer) rather than the bare root not-found. `notFound()` keeps the
 * response status at 404.
 */
export default function CatchAllPage() {
  notFound();
}
