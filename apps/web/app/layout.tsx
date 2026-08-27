import type { Metadata } from "next"
import { Geist_Mono, Inter } from "next/font/google"

import "@workspace/ui/globals.css"
import { cn } from "@workspace/ui/lib/utils"

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
    default: "Azmoth — GOÄ-Prüfung",
    template: "%s · Azmoth",
  },
  description:
    "Deterministische GOÄ-Kodierung und Rechnungsprüfung mit nachvollziehbarer Begründung. " +
    "Interne Anwendung, nur synthetische Daten.",
}

/**
 * The document, and nothing else.
 *
 * It used to render the app shell too. It cannot any more: `/login` and `/signup` are served by the
 * same root and must not carry a sidebar full of links to screens their visitor cannot open. The
 * shell — and the session check that has to happen before anything renders inside it — moved to
 * `app/(app)/layout.tsx`, which wraps every screen that shows clinical data. The sidebar's
 * `sidebar_state` cookie moved with it, so signing in is no longer a dynamic render that depends on
 * a cookie about a component the page does not have.
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
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
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  )
}
