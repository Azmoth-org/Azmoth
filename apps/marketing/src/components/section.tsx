import { cn } from "@workspace/ui/lib/utils";

/**
 * Vertical rhythm for the marketing pages, in one place.
 *
 * Every section on the site is the same max width and the same padding, so a page
 * is a list of `<Section>`s rather than a list of `<div className="mx-auto max-w-6xl
 * px-4 py-20 sm:px-6 lg:py-28">`s that drift by four pixels from each other.
 */
export function Section({
  className,
  children,
  ...props
}: React.ComponentProps<"section">) {
  return (
    <section className={cn("py-20 lg:py-28", className)} {...props}>
      <div className="mx-auto max-w-6xl px-4 sm:px-6">{children}</div>
    </section>
  );
}

export function SectionHeading({
  title,
  subtitle,
  align = "center",
  as: Heading = "h2",
}: {
  title: string;
  subtitle?: string;
  align?: "center" | "start";
  as?: "h1" | "h2";
}) {
  return (
    <div
      className={cn(
        "flex max-w-2xl flex-col gap-4",
        align === "center" && "mx-auto text-center"
      )}
    >
      <Heading
        className={cn(
          "font-heading text-balance",
          Heading === "h1"
            ? "text-4xl font-semibold tracking-tight sm:text-5xl"
            : "text-3xl font-semibold tracking-tight sm:text-4xl"
        )}
      >
        {title}
      </Heading>
      {subtitle ? (
        <p className="text-pretty text-base text-muted-foreground sm:text-lg">
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}
