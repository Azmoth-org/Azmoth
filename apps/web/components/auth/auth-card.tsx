import Link from "next/link"

import { Card, CardContent, CardDescription, CardHeader } from "@workspace/ui/components/card"
import { Separator } from "@workspace/ui/components/separator"

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
  alert,
  children,
  social,
  footer,
}: {
  title: string
  description: string
  /**
   * A failure that happened before this render — the `?error=` an OAuth round-trip came back with.
   * Above the form rather than beside the button that caused it, because by the time it is read the
   * reader has been to Google and back and no longer has that button in view.
   */
  alert?: React.ReactNode
  children: React.ReactNode
  /** The Google button, on deployments that have one. Omitted entirely on those that do not. */
  social?: React.ReactNode
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
          {alert}
          {children}
          {social ? (
            <div className="space-y-6">
              {/*
                The labelled rule, in the one arrangement that survives a long label and a narrow
                phone: the line is absolutely positioned behind the text, and the text carries the
                card's own background so it punches a hole in it. Two <Separator>s flanking a span
                is the other common spelling, and it collapses the moment the label wraps.

                `bg-card` has to stay in step with <Card>'s own background — this is the one place
                in the application where a token is repeated in order to erase what is behind it.
                aria-hidden because the rule is decoration and the label names nothing a
                screen-reader user needs; the button below it already says what it does.
              */}
              <div className="relative" aria-hidden="true">
                <Separator className="absolute inset-x-0 top-1/2" />
                <div className="relative flex justify-center">
                  <span className="bg-card text-muted-foreground px-3 text-xs">
                    Oder fortfahren mit
                  </span>
                </div>
              </div>
              {social}
            </div>
          ) : null}
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
