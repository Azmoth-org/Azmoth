import { cn } from "@workspace/ui/lib/utils";

/**
 * A card title that is a real heading.
 *
 * The shared `CardTitle` is a `<div>` and takes no `render` prop, which is correct for
 * the application — a card in a dashboard grid is a widget, not a section of a document.
 * A marketing page is the opposite case: fifteen of these are the *only* subheadings
 * under their `<h2>`, so rendering them as divs leaves the page with a nine-item outline
 * and nothing beneath it. That costs a screen-reader user the ability to skim the page by
 * heading, and it is the outline a search engine reads.
 *
 * It keeps `data-slot="card-title"`, because `CardHeader` is a grid whose row template
 * keys off exactly that attribute — dropping it re-lays-out every card on the site.
 */
export function CardHeading({
  className,
  as: Heading = "h3",
  ...props
}: React.ComponentProps<"h3"> & { as?: "h2" | "h3" }) {
  return (
    <Heading
      data-slot="card-title"
      className={cn("font-heading text-lg font-medium", className)}
      {...props}
    />
  );
}
