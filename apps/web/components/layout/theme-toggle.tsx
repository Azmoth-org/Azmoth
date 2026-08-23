"use client"

import { MoonIcon, SunIcon } from "lucide-react"
import { useTheme } from "next-themes"

import { Button } from "@workspace/ui/components/button"

/**
 * The visible way to switch theme.
 *
 * It replaces a global `keydown` listener that flipped the theme on any bare `d` press outside an
 * input. That was a scaffold leftover and it was actively wrong here: the only place it was
 * documented was the placeholder home page, and a reviewer arrowing through a positions table who
 * happened to press `d` would watch the screen invert with no idea why.
 *
 * **Both icons are rendered and CSS picks one.** The obvious implementation — read `resolvedTheme`
 * and render the matching icon — cannot work on the server, which does not know the reader's theme,
 * so it needs a `mounted` flag set from an effect. That is a hydration workaround, it flags
 * `react-hooks/set-state-in-effect`, and it makes the button briefly empty on first paint. Since
 * `next-themes` puts `class="dark"` on `<html>`, the `dark:` variant already knows the answer at
 * paint time and no React state is involved at all.
 *
 * The label is therefore static, and phrased so it is true in both states: an accessible name that
 * depended on the current theme would put us straight back to needing to know it during render.
 * `resolvedTheme` is read in the click handler, which runs only on the client, where it is known.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      aria-label="Design umschalten (hell / dunkel)"
      title="Design umschalten"
    >
      <MoonIcon className="dark:hidden" aria-hidden />
      <SunIcon className="hidden dark:block" aria-hidden />
    </Button>
  )
}
