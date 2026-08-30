import { cn } from "@workspace/ui/lib/utils";

/**
 * Vertical rhythm and surface tone for the marketing pages, in one place.
 *
 * Every section on the site is the same max width and the same padding, so a page is
 * a list of `<Section>`s rather than a list of `mx-auto max-w-6xl px-4 py-20 sm:px-6
 * lg:py-28`s that drift by four pixels from each other.
 *
 * `tone` is the second half of that job. DESIGN.md builds its page rhythm out of four
 * surfaces — white canvas, a cool off-white band, a warm cream interlude, and a deep
 * navy panel — and alternating them is what keeps a nine-section page from reading as
 * one undifferentiated scroll. Naming the four here means a page declares *which band
 * it is* rather than restating a background colour and hoping it matches the last one.
 */
const TONES = {
  /** `{colors.canvas}` — the default page surface. */
  canvas: "bg-white text-azm-ink",
  /** `{colors.canvas-soft}` — feature bands beneath the hero. */
  soft: "bg-azm-canvas-soft text-azm-ink",
  /** `{colors.canvas-cream}` — the warm interlude, used at most once per page. */
  cream: "bg-azm-canvas-cream text-azm-ink",
  /*
   * `{colors.brand-dark-900}` — the inverted panel.
   *
   * It repoints `--foreground` and `--muted-foreground` rather than only setting a
   * text colour, because the shared `Card`, `Badge` and `Separator` all resolve
   * against those two. Without the override a `text-muted-foreground` paragraph keeps
   * its light-surface grey and lands at about 2:1 on navy — legible on a designer's
   * monitor and not on anybody else's.
   */
  navy: "bg-azm-navy text-white [--foreground:oklch(1_0_0)] [--muted-foreground:oklch(0.83_0.03_270)] [--border:oklch(1_0_0/0.16)]",
} as const;

export function Section({
  className,
  tone = "canvas",
  backdrop,
  children,
  ...props
}: React.ComponentProps<"section"> & {
  tone?: keyof typeof TONES;
  /**
   * Full-bleed decoration behind the content — in practice, the hero's gradient mesh.
   *
   * A separate slot rather than a first child, because the content container is
   * `max-w-6xl` with horizontal padding: anything passed as a child is positioned
   * against *that* box and stops 24px short of both edges, which on a backdrop is
   * immediately visible as two pale gutters.
   */
  backdrop?: React.ReactNode;
}) {
  return (
    <section className={cn("relative py-20 lg:py-28", TONES[tone], className)} {...props}>
      {backdrop}
      <div className="relative mx-auto max-w-6xl px-4 sm:px-6">{children}</div>
    </section>
  );
}

/**
 * A section's opening block: eyebrow, headline, standfirst.
 *
 * The headline renders at weight 300 with negative tracking (`azm-display`), which is
 * DESIGN.md's typographic signature and the one thing it says never to override —
 * "at 400 the brand's editorial air collapses". Sizes stair-step 56 → 36px per its
 * breakpoint table.
 */
export function SectionHeading({
  eyebrow,
  title,
  subtitle,
  align = "center",
  as: Heading = "h2",
  className,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  align?: "center" | "start";
  as?: "h1" | "h2";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex max-w-3xl flex-col gap-4",
        align === "center" && "mx-auto text-center",
        className
      )}
    >
      {eyebrow ? (
        <p className="text-[0.6875rem] font-medium tracking-[0.12em] text-primary uppercase">
          {eyebrow}
        </p>
      ) : null}
      <Heading
        className={cn(
          "azm-display text-balance",
          Heading === "h1"
            ? "text-[2.25rem] sm:text-5xl lg:text-[3.5rem]"
            : "text-[2rem] sm:text-[2.5rem] lg:text-[3rem]"
        )}
      >
        {title}
      </Heading>
      {subtitle ? (
        <p
          className={cn(
            "text-pretty text-base leading-relaxed text-muted-foreground sm:text-lg",
            align === "center" && "mx-auto max-w-2xl"
          )}
        >
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}
