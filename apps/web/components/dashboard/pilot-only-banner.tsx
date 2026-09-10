"use client"

import { SparklesIcon, XIcon } from "lucide-react"
import * as React from "react"

import { Button } from "@workspace/ui/components/button"

/** `localStorage` key. Per browser, not per organisation — see the note below on why that is fine. */
const DISMISSED_KEY = "azmoth.pilotOnlyBannerDismissed"

/**
 * "Pilotbetrieb: ausschließlich synthetische Testdaten." — next to the first-run cards, dismissible.
 *
 * This is deliberately a second, narrower statement than `SyntheticDataBanner`, which stays
 * standing on every screen and is not dismissible: that one carries the compliance and liability
 * language (no access control, no § 203 workflow, a draft rather than an invoice) that has to
 * survive every load. This one is a first-run nudge — "this is the pilot, use test data" — so it is
 * allowed to go away once a reader has taken it in, the same way any onboarding tip would.
 *
 * `localStorage`, not a server-stored preference: the fact being remembered is "this browser has
 * seen the notice", not an organisation-wide setting, and it costs no round-trip and no migration
 * to check. Read only after mount — `useState(false)` first, then the effect flips it — so server
 * and client render the same thing on the first paint and React does not warn about a hydration
 * mismatch for a value `localStorage` cannot supply during SSR.
 */
export function PilotOnlyBanner() {
  const [dismissed, setDismissed] = React.useState(false)

  React.useEffect(() => {
    try {
      if (window.localStorage.getItem(DISMISSED_KEY) === "1") {
        setDismissed(true)
      }
    } catch {
      // Private browsing, cleared site data, or storage disabled outright — the banner just stays
      // visible every time, which is the safe direction to fail in.
    }
  }, [])

  function dismiss() {
    setDismissed(true)
    try {
      window.localStorage.setItem(DISMISSED_KEY, "1")
    } catch {
      // Nothing to recover — the banner reappears next load, which is a worse first run than a
      // thrown error, not a broken one.
    }
  }

  if (dismissed) return null

  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2.5 text-sm">
      <SparklesIcon
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-primary"
      />
      <p className="min-w-0 flex-1">
        <strong className="font-medium">Pilotbetrieb:</strong> ausschließlich
        synthetische Testdaten. Keine Echtdaten hochladen.
      </p>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={dismiss}
        aria-label="Hinweis schließen"
      >
        <XIcon aria-hidden />
      </Button>
    </div>
  )
}
