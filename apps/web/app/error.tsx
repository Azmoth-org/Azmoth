"use client"

import { AlertOctagonIcon, RotateCwIcon } from "lucide-react"
import * as React from "react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"

/**
 * The outer boundary. Without it an unhandled render error showed the Next.js default error page —
 * an English stack trace on a German compliance tool, with no way back.
 *
 * It is deliberately **not** where engine failures land. Those are values, not exceptions:
 * `lib/engine.ts` resolves every transport failure into a described error and each screen renders it
 * as a panel with the engine's own reason. So anything arriving here is a genuine defect in this
 * app, and the copy says so rather than blaming the network.
 *
 * `digest` is included because it is the only handle that ties what the reader saw to the line in
 * the server log — the message itself is redacted in production builds.
 *
 * It stays at the root rather than moving into `(app)` with the screens, so that a render error on
 * `/login` gets this page too — a German explanation and a way back — instead of the Next.js
 * default. The cost is that it no longer inherits the shell's `<main>`, which is why it now brings
 * its own page frame; the alert itself is self-contained and reads correctly without a sidebar.
 *
 * ## Two kinds of failure, because they need two different buttons
 *
 * A DOM-reconciliation failure is not the same event as a defect in a component, and offering the
 * same recovery for both is what made this boundary unhelpful in front of the one that actually
 * happens.
 *
 * `reset()` re-runs the render into the DOM that is already on the page. That is the right move for
 * an ordinary exception — a null dereference in a card, a bad cast — where the tree is intact and
 * the second attempt has a real chance. It is exactly the wrong move when the tree itself is what
 * broke: React has lost track of which nodes it owns, so re-rendering into that document either
 * throws again immediately or paints something subtly wrong. The only recovery there is a fresh
 * document, which is a reload.
 *
 * `isDomReconciliationError` below decides which the reader is looking at, and the copy and the
 * primary button follow from it. Both buttons are always present — the classification is a
 * heuristic over an error message, and a reader who gets the wrong one must still have the other.
 */

/**
 * Whether this is React losing its grip on the DOM rather than a component throwing.
 *
 * The signatures, and why each is here:
 *
 * * **`NotFoundError` / `insertBefore` / `removeChild`** — the DOM exception itself. React holds a
 *   reference to a sibling node and asks the parent to insert before it; the node is no longer that
 *   parent's child, so the call throws. Something outside React moved it.
 * * **"Hydration failed" / "did not match"** — the development build's own wording for the same
 *   family, one step earlier: the markup React found is not the markup it rendered.
 * * **Minified React errors 418, 421, 422, 423, 425** — the production build's numbers for the
 *   hydration set. Production ships no message text at all, so without these numbers this
 *   classification would work only in development, which is precisely where the problem does not
 *   need explaining.
 *
 * Matched against `message` and `name` together: a `DOMException` carries the useful half of its
 * identity in `name`, and the wrappers React puts around a caught error carry it in `message`.
 */
function isDomReconciliationError(error: Error): boolean {
  const haystack = `${error.name} ${error.message}`
  return /NotFoundError|insertBefore|removeChild|appendChild|Hydration failed|hydrating|did not match|Minified React error #(418|421|422|423|425)\b/i.test(
    haystack
  )
}

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const hydration = isDomReconciliationError(error)

  React.useEffect(() => {
    // Server-side render errors are already logged by Next; a client-side one is not, and a defect
    // nobody can see is one nobody fixes.
    //
    // The classification is logged with it. "The upload screen crashed" and "the upload screen
    // crashed because something rewrote the DOM under it" send an engineer to two different files,
    // and by the time the report reaches them the console is gone — so the distinction has to be in
    // the line, not in the reader's memory of what the page looked like.
    console.error(
      hydration
        ? "Darstellungsfehler (DOM/Hydration) in der Oberfläche:"
        : "Unbehandelter Fehler in der Oberfläche:",
      {
        name: error.name,
        message: error.message,
        digest: error.digest,
        kind: hydration ? "dom-reconciliation" : "render",
      },
      error
    )
  }, [error, hydration])

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <Alert variant="destructive">
        <AlertOctagonIcon />
        <AlertTitle>
          {hydration
            ? "Ansicht konnte nicht geladen werden"
            : "Diese Ansicht konnte nicht dargestellt werden"}
        </AlertTitle>
        <AlertDescription className="space-y-3">
          {hydration ? (
            <>
              <p>
                Ansicht konnte nicht geladen werden. Bitte laden Sie die Seite
                neu.
              </p>
              <p>
                Die Darstellung ist unterbrochen worden, nicht die Prüfung. Es
                wurde nichts freigegeben, abgelehnt oder exportiert — Ihre
                hochgeladene Datei und das Prüfergebnis sind davon nicht
                betroffen.
              </p>
              {/*
                Named because it is the one cause a reader can actually remove, and because the
                symptom points nowhere near it: a page rewritten by a translator or a page-modifying
                extension breaks in the renderer, not in the thing that rewrote it. Every screen here
                is German already, so the browser's own translation is pure cost.
              */}
              <p className="text-xs">
                Tritt das wiederholt auf, deaktivieren Sie bitte die
                automatische Übersetzung des Browsers sowie Erweiterungen, die
                Seiteninhalte verändern — diese Anwendung ist durchgängig auf
                Deutsch.
              </p>
            </>
          ) : (
            <p>
              Das ist ein Fehler in der Oberfläche, nicht ein Befund zu einer
              Rechnung. Es wurde nichts freigegeben, abgelehnt oder exportiert —
              Statuswechsel finden ausschließlich in der Engine statt und werden
              dort protokolliert.
            </p>
          )}

          {error.digest ? (
            <p className="text-xs">
              Kennung für das Server-Log:{" "}
              <span className="font-mono">{error.digest}</span>
            </p>
          ) : null}

          {/*
            Order follows the diagnosis: the button that can actually work comes first. Both are
            always rendered — `isDomReconciliationError` reads an error message, which is a
            heuristic, and a reader handed the wrong primary must still have the other one.
          */}
          <div className="flex flex-wrap gap-2">
            {hydration ? (
              <>
                <Button size="sm" onClick={() => window.location.reload()}>
                  <RotateCwIcon aria-hidden />
                  Seite neu laden
                </Button>
                <Button variant="outline" size="sm" onClick={reset}>
                  Erneut versuchen
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" size="sm" onClick={reset}>
                  Erneut versuchen
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => window.location.reload()}
                >
                  <RotateCwIcon aria-hidden />
                  Seite neu laden
                </Button>
              </>
            )}
          </div>
        </AlertDescription>
      </Alert>
    </main>
  )
}
