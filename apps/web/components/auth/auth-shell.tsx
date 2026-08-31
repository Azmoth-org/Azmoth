import Link from "next/link"

import { AzmothMark } from "@/components/brand/azmoth-mark"

/**
 * The frame both auth screens sit in: the wordmark, the form, the standing disclaimer, and the
 * panel on the right.
 *
 * This is shadcn's `login-02` page shell, with the block's three placeholders replaced by the real
 * thing — "Acme Inc." became the Azmoth mark, the `href="#"` became `/`, and the `/placeholder.svg`
 * cover became the panel below, because `public/` holds no photograph and shipping a broken `<img>`
 * to the first screen anybody sees is worse than shipping no image.
 *
 * One component rather than two copies, because `/login` and `/signup` are read as a pair — a reader
 * moves between them mid-task — and two shells that drift by a few pixels of padding make that
 * movement feel like leaving the application.
 *
 * ## The second column is `lg:` and up, and carries nothing load-bearing
 *
 * Below `lg` it is not rendered at all and the form is simply centred in the viewport, which is the
 * layout a phone gets. Nothing in it is required to sign in, so a narrow screen loses decoration
 * and no function.
 *
 * The mark is the real Azmoth monogram, from `@/components/brand/azmoth-mark` — the same component
 * the sidebar renders. It used to be an `AZ` tile duplicated from `app-shell.tsx` rather than
 * imported, because that file is a client component holding the whole navigation and pulling it in
 * to reuse eleven characters of markup would ship the sidebar to a screen that must not have one.
 * `AzmothMark` exists so both can share the mark without either importing the other.
 */
export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <div className="flex justify-center md:justify-start">
          <Link
            href="/"
            className="flex items-center gap-2.5"
            aria-label="Azmoth"
          >
            <AzmothMark className="size-9" />
            <span className="grid text-left leading-tight">
              <span className="text-base font-semibold">Azmoth</span>
              <span className="text-xs text-muted-foreground">GOÄ-Prüfung</span>
            </span>
          </Link>
        </div>

        <div className="flex flex-1 items-center justify-center">
          {/*
            `max-w-sm` rather than the block's `max-w-xs`: the sign-up form is four fields, a
            confirmation and a provider button, and at 320px its labels and the "mindestens 12
            Zeichen" hint start wrapping onto second lines.
          */}
          <div className="flex w-full max-w-sm flex-col gap-6">
            {children}

            {/*
              The same statement the sidebar carries on every other screen, and it belongs here most
              of all: this is the first page anybody sees, and it is where an expectation about what
              may be put into this system is formed.
            */}
            <p className="text-center text-xs text-balance text-muted-foreground">
              Interne Anwendung. Ausschließlich synthetische Daten — keine
              Patientendaten eingeben.
            </p>
          </div>
        </div>
      </div>

      <div className="relative hidden bg-muted lg:block">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-muted to-muted" />
        <div className="absolute inset-0 flex flex-col justify-end gap-2 p-10">
          <p className="max-w-sm text-lg leading-snug font-medium text-balance">
            GOÄ-Abrechnungen prüfen — nachvollziehbar, mit vollständigem
            Prüfprotokoll hinter jeder Freigabe.
          </p>
          <p className="text-sm text-muted-foreground">
            Interne Anwendung der Praxis.
          </p>
        </div>
      </div>
    </div>
  )
}
