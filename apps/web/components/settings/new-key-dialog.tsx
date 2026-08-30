"use client"

import * as React from "react"
import { CheckIcon, CopyIcon, KeyRoundIcon, TriangleAlertIcon } from "lucide-react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"
import { Input } from "@workspace/ui/components/input"
import { Label } from "@workspace/ui/components/label"

import type { ApiKeyIssued } from "@/lib/settings/client"

/**
 * Mint a key, then show it exactly once.
 *
 * ## The one-shot display is the whole design of this component
 *
 * The engine stores a SHA-256 hash and nothing else, so the token in `issued.token` is the only
 * copy that will ever exist. Everything here follows from that:
 *
 * * the dialog cannot be dismissed by clicking outside it or pressing Escape while a key is shown —
 *   a stray click would destroy a credential the user has not saved yet;
 * * closing it requires the explicit button, whose label says what is about to happen;
 * * the token is never written to `localStorage`, a URL or a log. It lives in React state for the
 *   life of this dialog and is dropped when it unmounts;
 * * the warning sits *above* the value rather than below it, because a reader who has already
 *   copied and closed has not read anything below.
 *
 * `disablePointerDismissal` is Base UI's prop for the first of those; the `onOpenChange` guard below
 * is the second and is the authoritative one, because it does not depend on which primitive library
 * this dialog is built on. Escape is handled by the guard too — Base UI routes it through
 * `onOpenChange` rather than through a separate handler.
 *
 * ## Why the copy button falls back
 *
 * `navigator.clipboard` is unavailable on an insecure origin, which is exactly where a first
 * self-hosted pilot runs (`http://` on a LAN). A copy button that silently did nothing there would
 * lose the key. So a failure selects the field instead and says to copy manually — the token stays
 * visible and selectable in a read-only input for the same reason.
 */
export function NewKeyDialog({
  open,
  onOpenChange,
  onMint,
  issued,
  minting,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onMint: (name: string) => void
  /** The minted key, or null while the form is still showing. */
  issued: ApiKeyIssued | null
  minting: boolean
}) {
  const [name, setName] = React.useState("")
  const [copied, setCopied] = React.useState(false)
  const [copyFailed, setCopyFailed] = React.useState(false)
  const tokenRef = React.useRef<HTMLInputElement>(null)

  // Reset when the dialog opens, never when it closes: clearing on close would blank the token
  // while the closing animation is still running.
  React.useEffect(() => {
    if (open) {
      setName("")
      setCopied(false)
      setCopyFailed(false)
    }
  }, [open])

  async function copy() {
    if (!issued) return
    try {
      await navigator.clipboard.writeText(issued.token)
      setCopied(true)
      setCopyFailed(false)
    } catch {
      // No clipboard API — an insecure origin, or a browser that refuses without a gesture it
      // recognises. Select the text so the reader can copy it themselves rather than lose it.
      setCopyFailed(true)
      tokenRef.current?.select()
    }
  }

  return (
    <Dialog
      open={open}
      disablePointerDismissal={issued !== null}
      onOpenChange={(next) => {
        // While a key is on screen the only way out is the button below. A stray click or an
        // Escape keypress would destroy a credential the reader has not saved yet, and it cannot
        // be reissued.
        if (!next && issued) return
        onOpenChange(next)
      }}
    >
      <DialogContent className="sm:max-w-lg" showCloseButton={!issued}>
        {issued ? (
          <>
            <DialogHeader>
              <DialogTitle>API-Schlüssel erstellt</DialogTitle>
              <DialogDescription>
                Kopieren Sie den Schlüssel jetzt in den Secret-Store Ihrer
                Anwendung.
              </DialogDescription>
            </DialogHeader>

            <Alert variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>Dieser Schlüssel wird nur einmal angezeigt</AlertTitle>
              <AlertDescription>
                Gespeichert wird ausschliesslich sein SHA-256-Hash. Er kann
                danach von niemandem erneut angezeigt werden — auch nicht von
                uns. Geht er verloren, erzeugen Sie einen neuen und widerrufen
                den alten.
              </AlertDescription>
            </Alert>

            <div className="space-y-2">
              <Label htmlFor="minted-token">Schlüssel</Label>
              <div className="flex gap-2">
                <Input
                  id="minted-token"
                  ref={tokenRef}
                  readOnly
                  value={issued.token}
                  className="font-mono text-xs"
                  onFocus={(event) => event.currentTarget.select()}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={copy}
                  aria-label="Schlüssel in die Zwischenablage kopieren"
                >
                  {copied ? <CheckIcon /> : <CopyIcon />}
                  {copied ? "Kopiert" : "Kopieren"}
                </Button>
              </div>
              {copyFailed ? (
                <p className="text-xs text-muted-foreground">
                  Die Zwischenablage ist in diesem Browser nicht verfügbar (das
                  ist bei einer <span className="font-mono">http://</span>
                  -Adresse normal). Der Schlüssel ist markiert — kopieren Sie
                  ihn mit Strg+C.
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Senden Sie ihn im Header{" "}
                  <span className="font-mono">X-API-Key</span> an{" "}
                  <span className="font-mono">/api/v1/audit/*</span>. Er
                  bestimmt zugleich, welche Praxis die Anfrage sieht.
                </p>
              )}
            </div>

            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>
                Ich habe den Schlüssel gespeichert
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              onMint(name)
            }}
          >
            <DialogHeader>
              <DialogTitle>Neuen API-Schlüssel erstellen</DialogTitle>
              <DialogDescription>
                Der Schlüssel handelt für die aktuell ausgewählte Praxis und
                sieht ausschliesslich deren Daten.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-2 py-4">
              <Label htmlFor="key-name">Bezeichnung</Label>
              <Input
                id="key-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="z. B. PVS-Export nächtlich"
                maxLength={128}
                autoFocus
              />
              <p className="text-xs text-muted-foreground">
                Frei wählbar, und der einzige Anhaltspunkt, um später zu
                erkennen, wozu ein Schlüssel gehört — das Geheimnis selbst ist
                danach nicht mehr einsehbar.
              </p>
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={minting}
              >
                Abbrechen
              </Button>
              <Button type="submit" disabled={minting}>
                <KeyRoundIcon />
                {minting ? "Wird erstellt…" : "Schlüssel erstellen"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
