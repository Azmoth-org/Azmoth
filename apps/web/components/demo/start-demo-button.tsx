"use client"

import { ArrowRightIcon, Loader2Icon, PlayIcon } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Button, buttonVariants } from "@workspace/ui/components/button"
import { cn } from "@workspace/ui/lib/utils"

/**
 * »Mit Beispieldaten testen« — runs the public audit, then opens the report.
 *
 * ## Why this calls the API and then navigates, rather than just linking
 *
 * `/demo/bericht` renders the report server-side, so a plain link would work and would be one
 * request instead of two. It is not what happens here, for two reasons that are both about the
 * visitor rather than about the machine.
 *
 * A prospect clicking this is being shown that an audit *runs*. Navigating to a page that is
 * already complete makes it look like a screenshot; a button that visibly works for a moment and
 * then produces a report makes it look like what it is. The engine memoises the report, so the
 * second call is a serialisation and the honesty costs nothing.
 *
 * The other reason is failure. If the engine is down, a link produces a broken page after the
 * navigation, with the visitor's context already gone. This finds out first and says so *here*,
 * where they still have the explanation of the product in front of them.
 */
export function StartDemoButton() {
  const router = useRouter()
  const [pending, setPending] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  async function run() {
    setPending(true)
    setFailed(null)
    try {
      const response = await fetch("/api/demo/audit", { method: "POST" })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        setFailed(
          typeof body?.message === "string"
            ? body.message
            : "Die Demo-Prüfung konnte nicht gestartet werden. Bitte versuchen Sie es in einem Moment erneut."
        )
        return
      }
      // `refresh` first so the report page renders the run that just happened rather than a
      // cached render of an earlier one.
      router.refresh()
      router.push("/demo/bericht")
    } catch {
      setFailed(
        "Die Demo-Prüfung konnte nicht gestartet werden. Besteht eine Verbindung zum Server?"
      )
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="lg" onClick={() => void run()} disabled={pending}>
          {pending ? (
            <>
              <Loader2Icon className="animate-spin" aria-hidden />
              Prüfung läuft…
            </>
          ) : (
            <>
              <PlayIcon aria-hidden />
              Mit Beispieldaten testen
            </>
          )}
        </Button>
        <Link
          href="/signup"
          className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
        >
          Mit eigenen Daten prüfen (Pilot-Zugang anfordern)
          <ArrowRightIcon aria-hidden />
        </Link>
      </div>

      <p className="text-xs text-muted-foreground">
        Keine Anmeldung, keine E-Mail-Adresse, kein Upload. Die Prüfung läuft
        gegen eine mitgelieferte synthetische Beispielrechnung.
      </p>

      {failed ? (
        <Alert variant="destructive">
          <AlertTitle>Demo nicht verfügbar</AlertTitle>
          <AlertDescription>{failed}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
