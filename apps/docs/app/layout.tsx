import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { RootProvider } from "fumadocs-ui/provider/next";

import { cn } from "@workspace/ui/lib/utils";

import { absoluteUrl, getDocsUrl, siteConfig } from "@/lib/site";

import "./globals.css";

/**
 * `next/font` rather than an `@import url(fonts.googleapis.com)` in the stylesheet — the CSS
 * import is render-blocking against a third-party origin on every cold visit. This self-hosts
 * the file, emits the `@font-face` inline and sets `--font-sans`, which is the variable
 * `@workspace/ui` already reads. Same setup as the marketing site, deliberately: Inter at
 * weight 300 is DESIGN.md's named substitute for Sohne, and two Azmoth origins rendering the
 * same words in two different faces is the most visible way a brand comes apart.
 */
const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  metadataBase: new URL(getDocsUrl()),
  title: {
    default: siteConfig.title,
    template: `%s · ${siteConfig.name}`,
  },
  description: siteConfig.description,
  alternates: { canonical: "/" },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "48x48 32x32 16x16" },
      { url: "/favicon-96x96.png", type: "image/png", sizes: "96x96" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  openGraph: {
    type: "website",
    url: absoluteUrl("/"),
    title: siteConfig.title,
    description: siteConfig.description,
    siteName: siteConfig.name,
    locale: "de_DE",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" className={cn("antialiased", inter.variable)} suppressHydrationWarning>
      <body className="flex min-h-screen flex-col">
        <RootProvider
          /*
           * Light, with no toggle and no `system` check — the same decision `apps/web` and
           * `apps/marketing` make, for the same reason. This site is one of three origins a
           * single visitor walks across, and a reader who leaves a light marketing page and
           * arrives on a dark reference page has no way to tell it is the same company.
           *
           * `theme.enabled: false` skips the `next-themes` provider entirely rather than
           * pinning it to `light`. Nothing then writes a `dark` class, nothing reads a stored
           * preference, and there is no first-paint flash to guard against — which is also
           * why the palette in `app/globals.css` defines no `.dark` block at all. Turning dark
           * mode back on is those two edits together; neither one alone does anything.
           *
           * `themeSwitch.enabled: false` in `lib/layout.shared.tsx` removes the control from
           * the navbar, so the setting is not merely inert but absent.
           */
          theme={{ enabled: false }}
          i18n={{
            locale: "de",
            /*
             * Fumadocs ships English UI chrome — "Search", "On this page", "Next Page". The
             * prose here is German, and a German page framed in English chrome reads as
             * unfinished.
             *
             * **The keys are the English strings themselves**, with the parenthesised context
             * Fumadocs uses to disambiguate them (`Search(search dialog)` is the dialog's own
             * heading; `Search(search trigger)` is the button in the navbar). That is not a
             * convention worth guessing at — it is `fumadocs-ui/dist/.translations/keys.js`,
             * and a key that does not appear there is silently ignored rather than reported,
             * so a typo here shows up as one English word in an otherwise German navbar.
             *
             * Unlisted keys fall back to English on purpose: the AI-assistant actions, the
             * language switcher and the theme switch are not enabled on this site, so
             * translating them would be maintaining strings nothing renders.
             */
            translations: {
              "Search(search dialog)": "Suchen",
              "Search(search trigger)": "Suchen",
              "Open Search(search trigger)(aria-label)": "Suche öffnen",
              "Close Search(search dialog)(aria-label)": "Suche schließen",
              "No results found(search dialog)": "Keine Treffer",
              "On this page(table of contents)": "Auf dieser Seite",
              "Table of Contents(inline table of contents)": "Inhalt",
              "No Headings(table of contents)": "Keine Abschnitte",
              "Next Page(pagination)": "Weiter",
              "Previous Page(pagination)": "Zurück",
              "Last updated on(page footer)": "Zuletzt geändert am",
              "Toggle Menu(mobile menu)(aria-label)": "Menü umschalten",
              "Open Sidebar(sidebar)(aria-label)": "Navigation öffnen",
              "Close Sidebar(sidebar)(aria-label)": "Navigation schließen",
              "Collapse Sidebar(sidebar)(aria-label)": "Navigation einklappen",
              "Hide Sidebar(sidebar)": "Navigation ausblenden",
              "Show Sidebar(sidebar)": "Navigation einblenden",
              "Copy Text(code block)(aria-label)": "Code kopieren",
              "Copied Text(code block)(aria-label)": "Kopiert",
              "Copy Anchor Link(heading anchor)(aria-label)": "Link zum Abschnitt kopieren",
              "Page Not Found(404 page)": "Seite nicht gefunden",
              "Back to Home(404 page)": "Zur Startseite",
              "The page you are looking for might have been removed, had its name changed, or is temporarily unavailable.(404 page)":
                "Die gesuchte Seite wurde entfernt, umbenannt oder ist vorübergehend nicht erreichbar.",
            },
          }}
        >
          {children}
        </RootProvider>
      </body>
    </html>
  );
}
