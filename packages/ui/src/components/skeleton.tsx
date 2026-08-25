import { cn } from "@workspace/ui/lib/utils"

/**
 * A placeholder block for content that has not arrived.
 *
 * Used for the shape of a panel, never for a number. A skeleton where an amount will appear is fine;
 * a skeleton that a reader could mistake for a rendered zero is not, which is why the audit screens
 * use a labelled spinner for figures and this only ever stands in for layout.
 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-2xl bg-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }
