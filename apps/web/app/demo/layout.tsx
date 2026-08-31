import Link from "next/link"

import { AzmothMark } from "@/components/brand/azmoth-mark"

import { buttonVariants } from "@workspace/ui/components/button"
import { cn } from "@workspace/ui/lib/utils"

import { ThemeToggle } from "@/components/layout/theme-toggle"

/**
 * The shell for the public demo. **No session, no sidebar, no organisation switcher.**
 *
 * `/demo` is outside the `(app)` route group deliberately, so it does not inherit
 * `app/(app)/layout.tsx` — which calls `requireSession()` and renders a rail full of links to
 * screens an anonymous visitor cannot open. Sharing that shell would mean either weakening the
 * session check that guards every clinical screen, or rendering a navigation menu that answers
 * `/login` to every click.
 *
 * What is left is the minimum a public page needs: the product name, a way back, the theme toggle
 * (a visitor arriving in dark mode should not be handed a white page), and the route to the gated
 * track. The header is where the two tracks are visibly different things rather than two buttons
 * that look alike.
 *
 * ## The mesh
 *
 * `DESIGN.md` calls the gradient mesh non-negotiable on a hero and says a bare canvas breaks the
 * brand. It meant the marketing site, but this is the same visitor's next screen: somebody who
 * clicks "Demo ansehen" on azmoth.com and lands on a plain white page has been handed what looks
 * like a different company's application. So the mesh washes the top of this shell, behind the nav
 * as well as the page — `nav-bar-on-mesh` in `DESIGN.md`'s own component list.
 *
 * It is **not** applied to `(app)`. Those screens are a working day, not a first impression, and a
 * coloured wash behind six hours of invoice tables is decoration charged to the reader.
 *
 * No `overflow-hidden` on the wrapper, deliberately: it would make this element a scroll container
 * and silently kill the sticky header. `.azm-mesh` is bounded by `inset-inline: 0` and
 * `max-block-size: 100%`, so it has nothing to clip.
 */
export default function DemoLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="relative flex min-h-svh flex-col bg-background">
      <div aria-hidden="true" className="azm-mesh print:hidden" />

      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur print:hidden">
        <div className="mx-auto flex w-full max-w-5xl items-center gap-4 px-4 py-3">
          <Link
            href="/demo"
            className="flex min-w-0 items-center gap-2 rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            {/*
              The mark, on the one screen in this application a visitor reaches without signing in.
              `items-center` rather than `items-baseline` now that there is a graphic beside the
              words: a baseline is a property of type, and a 20px square has none.
            */}
            <AzmothMark className="size-5" />
            <span className="text-sm font-semibold tracking-tight">Azmoth</span>
            <span className="truncate text-xs text-muted-foreground">
              GOÄ-Prüfung
            </span>
          </Link>

          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <Link
              href="/login"
              className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}
            >
              Anmelden
            </Link>
            <Link
              href="/signup"
              className={cn(buttonVariants({ size: "sm" }))}
            >
              Pilot-Zugang anfordern
            </Link>
          </div>
        </div>
      </header>

      <main className="relative mx-auto w-full max-w-5xl flex-1 space-y-8 px-4 py-8">
        {children}
      </main>

      <footer className="relative border-t print:hidden">
        <div className="mx-auto w-full max-w-5xl px-4 py-6 text-xs leading-relaxed text-muted-foreground">
          Azmoth prüft GOÄ-Abrechnungen deterministisch und ohne Sprachmodell.
          Das Ergebnis ist ein Prüfbericht und keine Rechnung; die ärztliche und
          abrechnungsfachliche Verantwortung bleibt beim Rechnungssteller. Diese
          Demo verarbeitet ausschliesslich synthetische Testdaten.
        </div>
      </footer>
    </div>
  )
}
