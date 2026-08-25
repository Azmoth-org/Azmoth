import type { Metadata } from "next"
import { cookies } from "next/headers"
import { Geist_Mono, Inter } from "next/font/google"

import "@workspace/ui/globals.css"
import { cn } from "@workspace/ui/lib/utils"

import { AppShell } from "@/components/layout/app-shell"
import { ThemeProvider } from "@/components/theme-provider"

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" })

const fontMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
})

/**
 * The default tab title and the template every screen's own title fills in.
 *
 * Without this the root had no metadata at all, so the dashboard's tab carried whatever Next
 * inferred. `%s` keeps each screen's German title first — a reviewer with four tabs open needs the
 * screen name before the product name.
 */
export const metadata: Metadata = {
  title: {
    default: "Govatax — GOÄ-Prüfung",
    template: "%s · Govatax",
  },
  description:
    "Deterministische GOÄ-Kodierung und Rechnungsprüfung mit nachvollziehbarer Begründung. " +
    "Interne Anwendung, nur synthetische Daten.",
}

/**
 * `defaultOpen` for the sidebar, read on the server.
 *
 * `SidebarProvider` writes `sidebar_state` when the rail is toggled but cannot read it during the
 * server render, so without this every first paint is the expanded rail — which then snaps shut for
 * anyone who collapsed it. Reading the cookie here makes the server render the state the reader left
 * behind. Any value other than a literal `"false"` means open, including a missing cookie.
 *
 * This is what makes the layout dynamic, which is correct: the rendered frame depends on the request.
 */
async function sidebarDefaultOpen(): Promise<boolean> {
  const store = await cookies()
  return store.get("sidebar_state")?.value !== "false"
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const defaultOpen = await sidebarDefaultOpen()

  return (
    // `lang="de"` because every string in this application is German. It was `en`, which makes a
    // screen reader pronounce "Abrechnungsvorschlag" with English phonemes and tells the browser to
    // offer the wrong translation and the wrong hyphenation.
    <html
      lang="de"
      suppressHydrationWarning
      className={cn("antialiased", fontMono.variable, "font-sans", inter.variable)}
    >
      <body>
        <ThemeProvider>
          <AppShell defaultOpen={defaultOpen}>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  )
}
