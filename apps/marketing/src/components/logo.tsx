import { cn } from "@workspace/ui/lib/utils";

import { siteConfig } from "@/lib/site";

/**
 * The wordmark, with a mark that is doing one job: saying "this reads a document
 * and returns a structured answer". Two stacked rules for the input, a bracket for
 * the output, drawn with `currentColor` so it inherits whatever the surface sets —
 * a placeholder until Phase 2 replaces it with the real Azmoth mark.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <svg
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
        className="size-6 text-primary"
      >
        <rect
          x="3"
          y="3"
          width="18"
          height="18"
          rx="5"
          stroke="currentColor"
          strokeWidth="1.75"
        />
        <path
          d="M8 9.5h8M8 13h5"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
        <path
          d="M14.5 16.5 16.5 18l3-3.5"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="font-heading text-lg font-semibold tracking-tight">
        {siteConfig.name}
      </span>
    </span>
  );
}
