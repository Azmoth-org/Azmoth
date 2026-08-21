"use client"

import * as React from "react"
import { CheckCircle2Icon, DownloadIcon, XCircleIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@workspace/ui/components/dialog"
import { Input } from "@workspace/ui/components/input"
import { Label } from "@workspace/ui/components/label"
import { Textarea } from "@workspace/ui/components/textarea"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@workspace/ui/components/tooltip"

/**
 * The approval boundary.
 *
 * `approved_by` is required by the engine and required here: an approval nobody signed is not an
 * approval. The dialog says plainly that the record is held in memory and does not survive a
 * restart — a reviewer must not believe they have created a durable, demonstrable approval, because
 * they have not. Durable audit logging is the prerequisite for that, and for export.
 */
export function ApproveDialog({
  disabled,
  pending,
  onApprove,
}: {
  disabled: boolean
  pending: boolean
  onApprove: (approvedBy: string, note: string) => Promise<void>
}) {
  const [open, setOpen] = React.useState(false)
  const [approvedBy, setApprovedBy] = React.useState("")
  const [note, setNote] = React.useState("")

  const canSubmit = approvedBy.trim().length > 0 && !pending

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    await onApprove(approvedBy.trim(), note.trim())
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button disabled={disabled}>
            <CheckCircle2Icon />
            Freigeben
          </Button>
        }
      />
      <DialogContent className="max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Vorschlag freigeben</DialogTitle>
            <DialogDescription>
              Mit der Freigabe übernehmen Sie die ärztliche Verantwortung für diesen
              Abrechnungsvorschlag.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="approved-by">
                Freigegeben von <span className="text-destructive">*</span>
              </Label>
              <Input
                id="approved-by"
                value={approvedBy}
                onChange={(event) => setApprovedBy(event.target.value)}
                placeholder="Name der freigebenden Person"
                autoComplete="off"
                required
              />
              <p className="text-muted-foreground text-xs">
                Pflichtfeld. Die Engine lehnt eine Freigabe ohne Namen ab.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="approval-note">Notiz (optional)</Label>
              <Textarea
                id="approval-note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={3}
              />
            </div>

            <Alert variant="destructive">
              <AlertTitle>Freigabe ist nicht revisionssicher</AlertTitle>
              <AlertDescription>
                Der Vorschlag und diese Freigabe liegen ausschließlich im Arbeitsspeicher der Engine.
                Sie überleben keinen Neustart, werden nicht zwischen Prozessen geteilt und es gibt
                kein Protokoll. Für einen echten Einsatz sind persistente Speicherung und
                revisionssichere Protokollierung Voraussetzung.
              </AlertDescription>
            </Alert>
          </div>

          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost">Abbrechen</Button>} />
            <Button type="submit" disabled={!canSubmit}>
              {pending ? "Wird freigegeben…" : "Freigabe bestätigen"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Rejection. The engine requires both a name and a reason, and a rejection is terminal — a rejected
 * proposal is re-run, never re-decided, so that the record keeps describing what actually happened.
 */
export function RejectDialog({
  disabled,
  pending,
  onReject,
}: {
  disabled: boolean
  pending: boolean
  onReject: (rejectedBy: string, reason: string) => Promise<void>
}) {
  const [open, setOpen] = React.useState(false)
  const [rejectedBy, setRejectedBy] = React.useState("")
  const [reason, setReason] = React.useState("")

  const canSubmit = rejectedBy.trim().length > 0 && reason.trim().length > 0 && !pending

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    await onReject(rejectedBy.trim(), reason.trim())
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant="destructive" disabled={disabled}>
            <XCircleIcon />
            Ablehnen
          </Button>
        }
      />
      <DialogContent className="max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Vorschlag ablehnen</DialogTitle>
            <DialogDescription>
              Eine Ablehnung ist endgültig. Der Vorschlag wird nicht erneut entschieden — führen Sie
              den Fall nach einer Korrektur neu aus.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="rejected-by">
                Abgelehnt von <span className="text-destructive">*</span>
              </Label>
              <Input
                id="rejected-by"
                value={rejectedBy}
                onChange={(event) => setRejectedBy(event.target.value)}
                placeholder="Name der ablehnenden Person"
                autoComplete="off"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="reject-reason">
                Grund <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="reject-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={3}
                placeholder="z. B. Sonographie nicht dokumentiert"
                required
              />
              <p className="text-muted-foreground text-xs">
                Pflichtfeld. Die Engine verlangt Name und Grund.
              </p>
            </div>
          </div>

          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost">Abbrechen</Button>} />
            <Button type="submit" variant="destructive" disabled={!canSubmit}>
              {pending ? "Wird abgelehnt…" : "Ablehnung bestätigen"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Export is deliberately absent, not merely unbuilt.
 *
 * A report carrying a receipt hash and an "approved by" line, produced from a store that dies on
 * restart, would outlive the record of its own approval. The receipt hash proves what the engine
 * computed; it proves nothing about who accepted it. So export waits for durable audit logging.
 */
export function ExportButtonPlaceholder() {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger
          render={
            <span tabIndex={0}>
              <Button variant="outline" disabled>
                <DownloadIcon />
                Exportieren
              </Button>
            </span>
          }
        />
        <TooltipContent className="max-w-xs">
          Der Export setzt eine revisionssichere Protokollierung voraus und ist noch nicht verfügbar.
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
