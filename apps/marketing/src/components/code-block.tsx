"use client";

import { useState } from "react";
import { CheckIcon, CopyIcon } from "lucide-react";

import { Button } from "@workspace/ui/components/button";
import { cn } from "@workspace/ui/lib/utils";

/**
 * A terminal panel with a copy button — DESIGN.md's dark "dashboard track", applied to
 * the one place on this site where a reader wants to take something away with them.
 *
 * The only client component on any marketing page besides the header and the cookie
 * banner, and it earns that: the audience for this block is an integrator evaluating
 * whether the API is real, and hand-transcribing a curl invocation from a screenshot
 * is exactly the friction that ends an evaluation. The interactive part is a `useState`
 * boolean and a clipboard write.
 *
 * `navigator.clipboard` is unavailable on a plain-HTTP origin and can be refused by
 * permissions policy, so the failure path leaves the button alone rather than throwing:
 * the text is selectable regardless, which is what the reader falls back to.
 */
export function CodeBlock({
  code,
  label,
  copyLabel,
  copiedLabel,
  className,
}: {
  code: string;
  label: string;
  copyLabel: string;
  copiedLabel: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* No clipboard (insecure origin, denied permission) — the text stays selectable. */
    }
  }

  return (
    <figure
      className={cn(
        /*
          A surface of its own, not `bg-azm-navy`.
          The home page renders this block *on* the navy band, where a navy panel is
          invisible: only the drop shadow separated the two, and a shadow on a dark
          ground is nothing. `--azm-ink` is the deeper of the brand's two darks, and the
          hairline ring draws the panel edge on either surface.
        */
        "overflow-hidden rounded-xl bg-azm-ink ring-1 ring-white/12 shadow-[0_8px_24px_rgba(0,55,112,0.18),0_2px_6px_rgba(0,55,112,0.1)]",
        className
      )}
    >
      <figcaption className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-2.5">
        <span className="flex items-center gap-2 text-xs font-medium text-white/70">
          <span aria-hidden="true" className="flex gap-1.5">
            <span className="size-2.5 rounded-full bg-white/20" />
            <span className="size-2.5 rounded-full bg-white/20" />
            <span className="size-2.5 rounded-full bg-white/20" />
          </span>
          {label}
        </span>
        <Button
          variant="ghost"
          size="xs"
          onClick={copy}
          aria-live="polite"
          className="text-white/70 hover:bg-white/10 hover:text-white"
        >
          {copied ? (
            <CheckIcon data-icon="inline-start" aria-hidden="true" />
          ) : (
            <CopyIcon data-icon="inline-start" aria-hidden="true" />
          )}
          {copied ? copiedLabel : copyLabel}
        </Button>
      </figcaption>
      {/*
        `overflow-x-auto` on the <pre>, not on the page. A long curl line must scroll
        inside this panel; a marketing page whose <body> scrolls sideways on a phone
        because of one code sample is the classic version of this bug.
      */}
      <pre className="azm-tnum overflow-x-auto px-4 py-4 text-[0.8125rem] leading-relaxed text-white/90">
        <code>{code}</code>
      </pre>
    </figure>
  );
}
