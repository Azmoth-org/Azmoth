"use client"

import { Toaster as Sonner, type ToasterProps } from "sonner"
import {
  CircleCheckIcon,
  InfoIcon,
  TriangleAlertIcon,
  OctagonXIcon,
  Loader2Icon,
} from "lucide-react"

/**
 * Toasts, on the one theme this design system has.
 *
 * `theme` is pinned to `"light"` rather than read from a theme hook. Sonner defaults to `"system"`,
 * which follows the operating system and would paint a dark toast over a light application the
 * moment somebody's laptop switched at sunset — the one surface that could still go dark after the
 * rest of the theme machinery was removed.
 *
 * The colours themselves come from the CSS variables below, so a toast stays part of the same
 * palette as everything under it and this prop is only deciding which of Sonner's own two
 * stylesheets loads.
 */
const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
