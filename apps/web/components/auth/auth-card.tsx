import Link from "next/link"

import { Card, CardContent, CardDescription, CardHeader } from "@workspace/ui/components/card"

/**
 * The frame both auth screens sit in: the wordmark, one card, and the standing disclaimer.
 *
 * One component rather than two copies, because `/login` and `/signup` are read as a pair — a
 * reader moves between them mid-task — and two cards that drift by a few pixels of padding make
 * that movement feel like leaving the application.
 *
 * The mark is the same `GO` tile the sidebar uses, at the same size and with the same tokens. It is
 * duplicated rather than imported from `app-shell.tsx`, which is a client component holding the
 * whole navigation: pulling that in to reuse eleven characters of markup would ship the sidebar to
 * a screen that must not have one.
 *
 * The title is an `<h1>` carrying `CardTitle`'s classes rather than a `CardTitle`, which renders a
 * `<div>`. On a screen whose entire content is one form, the form's name is the page's name, and a
 * page with no level-1 heading gives a screen-reader user nothing to land on — every other screen in
 * this application has one.
 */
export function AuthCard({
  title,
  description,
  children,
  footer,
}: {
  title: string
  description: string
  children: React.ReactNode
  /** The link to the other screen — "Noch kein Konto?" and its counterpart. */
  footer: React.ReactNode
}) {
  return (
    <div className="w-full max-w-md space-y-6">
      <Link href="/" className="flex items-center justify-center gap-2.5" aria-label="Govatax">
        <span className="bg-primary text-primary-foreground grid size-9 shrink-0 place-items-center rounded-lg font-mono text-xs font-medium">
          GO
        </span>
        <span className="grid text-left leading-tight">
          <span className="text-base font-semibold">Govatax</span>
          <span className="text-muted-foreground text-xs">GOÄ-Prüfung</span>
        </span>
      </Link>

      <Card>
        <CardHeader>
          <h1 className="font-heading text-base font-medium">{title}</h1>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {children}
          <p className="text-muted-foreground text-center text-sm">{footer}</p>
        </CardContent>
      </Card>

      {/*
        The same statement the sidebar carries on every other screen, and it belongs here most of
        all: this is the first page anybody sees, and it is where an expectation about what may be
        put into this system is formed.
      */}
      <p className="text-muted-foreground mx-auto max-w-sm text-center text-xs">
        Interne Anwendung. Ausschließlich synthetische Daten — keine Patientendaten eingeben.
      </p>
    </div>
  )
}
