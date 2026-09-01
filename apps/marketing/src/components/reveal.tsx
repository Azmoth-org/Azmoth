"use client";

import { LazyMotion, domAnimation, m, type Variants } from "motion/react";

import { cn } from "@workspace/ui/lib/utils";

/**
 * The scroll reveal: content fades up and resolves out of a slight blur as it enters the viewport.
 *
 * One primitive, used by every section on the site, because the alternative — each section
 * choosing its own distance, duration and easing — is how a page ends up with nine subtly
 * different ideas of what "appearing" means. The brief asks for "subtle, professional" and that is
 * mostly a question of restraint: 16px of travel, 4px of blur, no scale, no rotation, no parallax.
 *
 * ## `LazyMotion` with `domAnimation`, not the full `motion` bundle
 *
 * `import { motion } from "motion/react"` pulls the whole feature set — layout projection, drag,
 * SVG path drawing — into any bundle that touches it, around 34 kB gzipped. These reveals need
 * opacity, transform and filter and nothing else. `domAnimation` is roughly 15 kB and `m` is the
 * same component with the features supplied by the provider rather than bundled with it.
 *
 * The navigation deliberately does *not* use this: it needs `layoutId`, which lives in
 * `domMax`, and mixing the two providers in one tree costs more than either alone.
 *
 * ## Why `filter` is on the list at all
 *
 * A blur transition is expensive — it forces a repaint per frame rather than a composite — and on
 * a large element it is exactly the kind of effect that shows up in a Lighthouse trace. It is
 * worth it here at 4px, over 0.6s, on elements that animate once and never again, because it is
 * what separates "content faded in" from the depth-of-field settle that reads as expensive. The
 * cost is bounded by `once: true`: each element pays it a single time per page load.
 *
 * ## `margin: "-80px"` on the viewport
 *
 * The reveal starts when the element is 80px *past* the bottom edge, not at it. Firing exactly on
 * intersection means content animates in the visitor's peripheral vision and is already still by
 * the time they look at it — the animation happens, and nobody sees it.
 *
 * ## `data-reveal`, and the blank page it prevents
 *
 * `initial="hidden"` is rendered by the server as a literal
 * `style="opacity:0;filter:blur(4px);transform:translateY(16px)"` on the element — that is how
 * these libraries avoid a flash of unstyled content, and it is correct right up until the
 * JavaScript does not arrive. A chunk that 404s behind a corporate proxy, a CSP that blocks it, a
 * reader with scripting off: the response is a complete, correct document with every word of it at
 * zero opacity.
 *
 * That is a bad failure for any page and a disqualifying one for this page, whose entire job is to
 * be read by a stranger evaluating whether the company is serious. The marker attribute is what
 * lets `layout.tsx` ship a three-line `<noscript>` rule that overrides the inline styles; see it
 * there for why the `!important`s are load-bearing. Every element that starts hidden carries it.
 */

const VARIANTS: Variants = {
  hidden: { opacity: 0, y: 16, filter: "blur(4px)" },
  visible: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] },
  },
};

/**
 * The container variant used by `RevealGroup`.
 *
 * `delayChildren` is what makes a stagger read as one gesture: without it the first child starts
 * at t=0 while the group is still crossing the threshold, and the sequence looks like it began
 * before the section arrived.
 */
const GROUP: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
};

type RevealProps = {
  children: React.ReactNode;
  className?: string;
  /** Seconds to hold before starting. For a hero's second and third lines, not for a grid. */
  delay?: number;
  /** The element to render. A reveal around a list item must still be an `<li>`. */
  as?: "div" | "li" | "section" | "figure";
};

export function Reveal({ children, className, delay = 0, as = "div" }: RevealProps) {
  const Tag = m[as];

  return (
    <LazyMotion features={domAnimation} strict>
      <Tag
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-80px" }}
        variants={VARIANTS}
        transition={{ delay }}
        className={className}
        data-reveal=""
      >
        {children}
      </Tag>
    </LazyMotion>
  );
}

/**
 * A staggered reveal for a grid or list: the container observes the viewport once and its children
 * arrive in sequence.
 *
 * Children must be `RevealItem`s. Nine separate `Reveal`s in a grid would each observe the
 * viewport independently and all fire within the same frame anyway — the stagger has to be owned
 * by the parent to exist at all.
 */
export function RevealGroup({
  children,
  className,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "ul" | "ol";
}) {
  const Tag = m[as];

  return (
    <LazyMotion features={domAnimation} strict>
      <Tag
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-80px" }}
        variants={GROUP}
        className={className}
        data-reveal=""
      >
        {children}
      </Tag>
    </LazyMotion>
  );
}

/**
 * One row of a `RevealGroup`. Carries no `whileInView` of its own — it inherits `hidden`/`visible`
 * from the parent's variant propagation, which is the mechanism the stagger runs on.
 *
 * No `LazyMotion` wrapper: it is always inside a `RevealGroup`, which provides one. Nesting two
 * strict providers throws.
 */
export function RevealItem({
  children,
  className,
  as = "li",
}: {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "li";
}) {
  const Tag = m[as];
  return (
    <Tag variants={VARIANTS} className={cn(className)} data-reveal="">
      {children}
    </Tag>
  );
}
