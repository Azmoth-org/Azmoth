"use client"

import { ThemeProvider as NextThemesProvider } from "next-themes"
import * as React from "react"

/**
 * Theme state for the whole app. Nothing else.
 *
 * It used to also install a global `keydown` listener that flipped the theme on any bare `d` press
 * outside a form field. That came from the project scaffold and was removed rather than kept: the
 * only place it was ever documented was the placeholder home page, and an invisible global shortcut
 * that inverts the screen is the wrong thing to have on a page where somebody is reading invoice
 * positions. The switch is now a labelled button in the top bar — see
 * `components/layout/theme-toggle.tsx`.
 */
function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="class"
      // Light, whatever the operating system says. `system` was the scaffold's default and it is
      // the wrong default for this product: a screen carrying an amount and a signature should not
      // arrive dark because somebody's laptop switched at sunset, and a physician who has never
      // opened the toggle should never see the developer-tool version of it. Dark is still one
      // click away in the top bar, and the choice persists — it is a preference, not the product.
      defaultTheme="light"
      enableSystem={false}
      disableTransitionOnChange
      {...props}
    >
      {children}
    </NextThemesProvider>
  )
}

export { ThemeProvider }
