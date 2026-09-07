import type { Metadata } from "next"
import { Geist_Mono, Inter } from "next/font/google"

import "./globals.css"
import { cn } from "@workspace/ui/lib/utils"

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
  /*
   * The Azmoth mark, replacing the Next.js starter's own `app/favicon.ico`. A reviewer keeps this
   * application open beside four other tabs all day and finds it by its icon, so the icon being the
   * framework's default was a real cost rather than a cosmetic one.
   *
   * Declared here rather than relying on Next's `app/favicon.ico` file convention, because the
   * convention covers exactly that one file: the 96px PNG a high-DPI tab prefers and the
   * `apple-touch-icon` iOS wants have to be named. The five files are at the root of `public/`, which
   * is where a client that reads no `<link>` looks for `/favicon.ico` anyway.
   *
   * No SVG icon: the generated one is 2.0 MB (the monogram raster inside an `<svg>` wrapper) and
   * browsers prefer an SVG when offered, so linking it would cost every cold load two megabytes for
   * a 16-pixel image. `apps/marketing/src/lib/seo.ts` carries the same note.
   *
   * No Open Graph block. This application is behind a session; a link to it pasted into a chat should
   * not render a preview card, because there is nothing here for someone without an account to see.
   * The marketing site is what has a card.
   */
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "48x48 32x32 16x16" },
      { url: "/favicon-96x96.png", type: "image/png", sizes: "96x96" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  manifest: "/site.webmanifest",
  /*
   * The `<html translate="no">` below in the tag Chrome has honoured longest. See the comment on
   * that attribute for why this application refuses machine translation outright — it is the fix
   * for a real crash, not a stylistic objection.
   */
  other: { google: "notranslate" },
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
      /*
       * ## `translate="no"` is a crash fix, not a preference
       *
       * The reported failure was `NotFoundError: Failed to execute 'insertBefore' on 'Node'`,
       * intermittently, on the PADnext refusal screen. Nothing in that screen renders differently
       * on the server than on the client, and it does not have to: the error is what React throws
       * when something *outside* React has moved the nodes it is holding references to.
       *
       * Chrome's built-in translator is that something. It replaces every translatable text node
       * with a `<font>` element of its own, so the sibling React kept a pointer to is no longer a
       * child of the parent it asks to insert before. Intermittent, because it is a race between
       * the translator's pass and React's — which is also why it showed up on the refusal screen
       * first: several hundred words of German arriving at once is the longest translation pass
       * this application ever triggers.
       *
       * `lang="de"` on a browser set to anything else is precisely the condition Chrome offers to
       * translate on, so the two attributes belong together. And the translation was never wanted:
       * every string here is German for a German medical practice, and what the machine would be
       * rewriting is GOÄ codes, XML paths, shell commands and legally-adjacent refusal text, where
       * a plausible mistranslation is worse than no translation. Where a reader genuinely needs
       * English, the engine ships its own and `lib/padnext/issue-language.tsx` serves it.
       *
       * A `<meta name="google" content="notranslate">` goes with it, from `metadata` above — the
       * attribute is the standard, the meta tag is what older Chrome honours, and the two disagree
       * about nothing.
       */
      translate="no"
      // Kept, and now for a different reason than the theme class it was added for: it stops React
      // tearing down the document over an attribute injected by an extension before hydration.
      suppressHydrationWarning
      className={cn(
        "antialiased",
        fontMono.variable,
        "font-sans",
        inter.variable
      )}
    >
      <body>{children}</body>
    </html>
  )
}
