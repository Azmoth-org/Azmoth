import { TriangleAlertIcon } from "lucide-react";

import { cn } from "@workspace/ui/lib/utils";

/**
 * The banner on a legal page that is not finished yet.
 *
 * Amber rather than red, and stated in German in the visitor's own reading flow rather
 * than hidden in a comment: the audience is partly the person who has to supply the
 * missing details, and partly a visitor who deserves to know that what they are reading
 * is a draft before they rely on it.
 *
 * It disappears on its own when the placeholders do — see `hasPlaceholder`.
 */
export function PlaceholderNotice({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  return (
    <div
      role="note"
      className={cn(
        "flex items-start gap-3 rounded-xl bg-azm-unconfirmed-bg p-5 ring-1 ring-azm-unconfirmed/30",
        className
      )}
    >
      <TriangleAlertIcon
        aria-hidden="true"
        className="mt-0.5 size-4.5 shrink-0 text-azm-unconfirmed"
      />
      <p className="text-sm leading-relaxed text-azm-ink-secondary">{text}</p>
    </div>
  );
}
