"use client"

import * as React from "react"
import { CheckCircle2Icon, DownloadIcon, XCircleIcon } from "lucide-react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@workspace/ui/components/alert"
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@workspace/ui/components/tooltip"

import type { Proposal } from "@/lib/review/types"

/**
 * The approval boundary.
 *
 * `approved_by` is required by the engine and required here: an approval nobody signed is not an
 * approval.
 *
 * The dialog used to carry a destructive alert saying the record lived only in the engine's memory
 * and would not survive a restart. That warning is gone because the statement is no longer true:
 * the engine persists the proposal and the approval to Postgres and writes an append-only audit
 * event in the same transaction, so an approval made here is a durable record of who took
 * responsibility and when. Leaving the warning in place would now be the misleading option — a
 * reviewer who does not trust the record will re-approve, and two approvals of one proposal is
 * exactly what the status lifecycle exists to prevent.
 *
 * What the dialog still does NOT claim is that the approver's identity was *verified*. There is a
 * login in front of this screen now, and the session's user id travels to the engine and lands in
 * the audit row — but `approved_by` is a separate fact: a name this dialog asks for and the engine
 * stores as a string, with nothing requiring it to match the account that is signed in. That is
 * deliberate rather than an oversight (a locum signing on a colleague's open workstation is a real
 * thing, and the log records both facts), and it is why the copy below still says the name is
 * recorded, not proven.
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
      {/*
        `size="lg"` and the default (blue) variant. Approve and reject were two solid fills of equal
        weight welded into one group, which made an irreversible approval look like a fifty-fifty
        choice between two buttons. It is not: approving is what a reviewer does to almost every
        proposal, rejecting is the exception. The size and the fill say which is the path.
      */}
      <DialogTrigger
        render={
          <Button size="lg" disabled={disabled}>
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
              Mit der Freigabe übernehmen Sie die ärztliche Verantwortung für
              diesen Abrechnungsvorschlag.
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
              <p className="text-xs text-muted-foreground">
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

            <Alert>
              <AlertTitle>Die Freigabe wird dauerhaft protokolliert</AlertTitle>
              <AlertDescription>
                Vorschlag und Freigabe werden dauerhaft gespeichert und im
                Protokoll festgehalten — mit Name, Zeitpunkt und Receipt-Hash.
                Die Freigabe ist endgültig: sie kann nicht zurückgenommen
                werden. Der Name wird protokolliert, aber technisch nicht
                überprüft; eine Authentifizierung ist noch nicht eingerichtet.
              </AlertDescription>
            </Alert>
          </div>

          <DialogFooter>
            <DialogClose
              render={
                <Button type="button" variant="ghost">
                  Abbrechen
                </Button>
              }
            />
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

  const canSubmit =
    rejectedBy.trim().length > 0 && reason.trim().length > 0 && !pending

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
          <Button
            variant="outline"
            size="lg"
            disabled={disabled}
            className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
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
              Eine Ablehnung ist endgültig. Der Vorschlag wird nicht erneut
              entschieden — führen Sie den Fall nach einer Korrektur neu aus.
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
              <p className="text-xs text-muted-foreground">
                Pflichtfeld. Die Engine verlangt Name und Grund.
              </p>
            </div>
          </div>

          <DialogFooter>
            <DialogClose
              render={
                <Button type="button" variant="ghost">
                  Abbrechen
                </Button>
              }
            />
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
 * Export. Enabled only on an `APPROVED` proposal, and it asks who is taking the file.
 *
 * This button was disabled for two releases and the reasons are worth keeping, because they are
 * the reasons it may be enabled now. The first was that a report carrying a receipt hash and an
 * "approved by" line, produced from a store that died on restart, would outlive the record of its
 * own approval. The second was that the endpoint had not been exercised against the database. Both
 * are gone: the proposal, the approval and the export are all rows in Postgres, and the export
 * document is assembled inside the transaction that writes the `EXPORTED` audit event.
 *
 * `exported_by` is required for the same reason `approved_by` is — the export is a thing a person
 * did, and the log has to be able to say who. The copy below says the name is *recorded*, not
 * verified: reaching this screen needs a session, but the typed name is a separate fact from the
 * account that is signed in and nothing requires the two to match. See `ApproveDialog` above.
 *
 * The export is also **once**. `EXPORTED` is terminal, so a second attempt is refused with a 409,
 * and the dialog says so before the user commits rather than after.
 */
export function ExportDialog({
  status,
  pending,
  onExport,
}: {
  status: Proposal["status"]
  pending: boolean
  onExport: (exportedBy: string, note: string) => Promise<void>
}) {
  const [open, setOpen] = React.useState(false)
  const [exportedBy, setExportedBy] = React.useState("")
  const [note, setNote] = React.useState("")

  const approved = status === "APPROVED"
  const alreadyExported = status === "EXPORTED"
  const canSubmit = exportedBy.trim().length > 0 && !pending

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    await onExport(exportedBy.trim(), note.trim())
    setOpen(false)
  }

  // A disabled control that does not explain itself reads as broken, so the reason is always
  // attached — and the reason differs by status, which is the useful part.
  const hint = approved
    ? null
    : alreadyExported
      ? "Dieser Vorschlag wurde bereits exportiert. Ein Export ist endgültig und nur einmal möglich."
      : "Export ist erst nach der Freigabe möglich. Ein Entwurf, den niemand freigegeben hat, ist kein Dokument."

  const button = (
    <Button variant="ghost" size="sm" disabled={!approved || pending}>
      <DownloadIcon />
      Exportieren
    </Button>
  )

  if (!approved) {
    // The `span` is what lets a *disabled* button still explain itself: a disabled control fires no
    // pointer or focus events, so the tooltip would never open if it wrapped the button directly.
    // It is deliberately absent from the enabled branch below — `DialogTrigger` needs a real
    // `<button>` to keep native button semantics, and giving it a span breaks both forms and
    // accessibility.
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger render={<span tabIndex={0}>{button}</span>} />
          <TooltipContent className="max-w-xs">{hint}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={button} />
      <DialogContent className="max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Vorschlag exportieren</DialogTitle>
            <DialogDescription>
              Der Export enthält den vollständigen Abrechnungsvorschlag mit
              Receipt-Hash, Katalog- und Regelversionen, allen Beweisketten und
              dem Freigabeprotokoll.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="exported-by">
                Exportiert von <span className="text-destructive">*</span>
              </Label>
              <Input
                id="exported-by"
                value={exportedBy}
                onChange={(event) => setExportedBy(event.target.value)}
                placeholder="Name oder Zielsystem, z. B. PVS-Anbindung"
                autoComplete="off"
                required
              />
              <p className="text-xs text-muted-foreground">
                Pflichtfeld. Die Engine lehnt einen Export ohne Namen ab.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="export-note">Notiz (optional)</Label>
              <Textarea
                id="export-note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={2}
                placeholder="z. B. Ticket-Nummer oder Empfänger"
              />
            </div>

            <Alert>
              <AlertTitle>
                Der Export ist endgültig und wird protokolliert
              </AlertTitle>
              <AlertDescription>
                Der Vorschlag wechselt dauerhaft in den Status{" "}
                <strong>Exportiert</strong> und kann danach nicht erneut
                exportiert werden. Name, Zeitpunkt und Notiz werden im Protokoll
                festgehalten — der Name wird protokolliert, aber technisch nicht
                überprüft.
              </AlertDescription>
            </Alert>
          </div>

          <DialogFooter>
            <DialogClose
              render={
                <Button type="button" variant="ghost">
                  Abbrechen
                </Button>
              }
            />
            <Button type="submit" disabled={!canSubmit}>
              {pending ? "Wird exportiert…" : "Export herunterladen"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
