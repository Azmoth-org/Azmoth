import Link from "next/link"

import { Card, CardContent } from "@workspace/ui/components/card"

/**
 * The frame both auth screens sit in: the wordmark, one card, and the standing disclaimer.
 *
 * One component rather than two copies, because `/login` and `/signup` are read as a pair — a reader
 * moves between them mid-task — and two cards that drift by a few pixels of padding make that
 * movement feel like leaving the application.
 *
 * ## It is a frame now, and nothing else
 *
 * It used to own the title, the description, the labelled rule above the provider button and the
 * footer link, handing each in as a prop. All four moved into the form: `@workspace/ui`'s auth
 * templates arrange them as one `FieldGroup`, and splitting a single visual sequence across two
 * components meant the spacing between the heading and the first field was set in a different file
 * from the spacing between the fields. What is left here is the part that genuinely wraps the form.
 *
 * The mark is the same `AZ` tile the sidebar uses, at the same size and with the same tokens. It is
 * duplicated rather than imported from `app-shell.tsx`, which is a client component holding the whole
 * navigation: pulling that in to reuse eleven characters of markup would ship the sidebar to a screen
 * that must not have one.
 */
export function AuthCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full max-w-md space-y-6">
      <Link
        href="/"
        className="flex items-center justify-center gap-2.5"
        aria-label="Azmoth"
      >
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary font-mono text-xs font-medium text-primary-foreground">
          AZ
        </span>
        <span className="grid text-left leading-tight">
          <span className="text-base font-semibold">Azmoth</span>
          <span className="text-xs text-muted-foreground">GOÄ-Prüfung</span>
        </span>
      </Link>

      <Card>
        <CardContent className="pt-6">{children}</CardContent>
      </Card>

      {/*
        The same statement the sidebar carries on every other screen, and it belongs here most of
        all: this is the first page anybody sees, and it is where an expectation about what may be
        put into this system is formed.
      */}
      <p className="mx-auto max-w-sm text-center text-xs text-muted-foreground">
        Interne Anwendung. Ausschließlich synthetische Daten — keine
        Patientendaten eingeben.
      </p>
    </div>
  )
}
