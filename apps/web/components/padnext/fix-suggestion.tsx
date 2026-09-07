"use client"

import { CheckIcon, CopyIcon } from "lucide-react"
import { useState } from "react"

import { Button } from "@workspace/ui/components/button"

/**
 * The command that fixes one problem, in a block a reader can copy.
 *
 * ## Why a copy button and not just a `<pre>`
 *
 * The command is `python3 scripts/anonymize_padnext.py lieferung.padx -o anonymisiert.padx`, and
 * the person reading it has just had an upload refused. Every character they retype is a chance to
 * produce a second error that is about their typing rather than about their export — and the most
 * likely one, a mistyped filename, comes back as a message about a file not existing, which sends
 * them looking in the wrong place entirely.
 *
 * ## Why it degrades instead of failing
 *
 * `navigator.clipboard` is unavailable over plain HTTP and in some embedded browsers. When the
 * write throws, the text stays selectable and the button simply does not confirm — it must never
 * show "Kopiert" for something that was not copied, because the reader will paste whatever was in
 * their clipboard before and debug the result.
 */
export function FixSuggestion({
  command,
  label = "Befehl",
}: {
  command: string
  label?: string
}) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      // Deliberately silent, and deliberately not optimistic — see the note above.
      setCopied(false)
    }
  }

  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="flex items-start gap-2 rounded-md border bg-muted/50 p-2">
        <code className="min-w-0 flex-1 overflow-x-auto font-mono text-xs whitespace-pre-wrap break-all">
          $ {command}
        </code>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 shrink-0"
          onClick={() => void copy()}
          aria-label={copied ? "Befehl kopiert" : "Befehl kopieren"}
        >
          {copied ? (
            <CheckIcon className="size-3.5 text-emerald-600" aria-hidden />
          ) : (
            <CopyIcon className="size-3.5" aria-hidden />
          )}
        </Button>
      </div>
    </div>
  )
}
