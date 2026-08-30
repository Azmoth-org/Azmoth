"use client"

import * as React from "react"
import { KeyRoundIcon, Loader2Icon, ShieldOffIcon } from "lucide-react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@workspace/ui/components/alert-dialog"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"
import { Skeleton } from "@workspace/ui/components/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

import { ErrorPanel } from "@/components/review/error-panel"
import { NewKeyDialog } from "@/components/settings/new-key-dialog"
import { UsageSummaryCard } from "@/components/settings/usage-summary-card"
import {
  fetchApiKeys,
  fetchUsage,
  mintApiKey,
  revokeApiKey,
  type ApiKeyIssued,
  type ApiKeyList,
  type ReviewError,
  type UsageSummary,
} from "@/lib/settings/client"

/** `2026-08-30, 14:05` — the format the rest of the application uses for a stored timestamp. */
function stamp(value: string | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

/**
 * The API key screen: list, mint, revoke — and what the keys have consumed.
 *
 * ## Why revoked keys stay in the table
 *
 * They are shown with the date they stopped working rather than filtered out. "This key was revoked
 * on the 3rd" and "this key never existed" are different answers to the question somebody is
 * actually asking when an integration stopped working this morning, and a list that hid the first
 * would send them looking for a bug in their own code.
 *
 * ## Why the list reloads after a mint rather than appending
 *
 * The mint response has everything needed to append a row, and appending would still be wrong: the
 * server is the only thing that knows the full state, and a client that maintains its own copy
 * drifts the first time two tabs are open. One extra request on an action a practice takes a
 * handful of times ever is not worth a second source of truth.
 */
export function ApiKeyManager() {
  const [keys, setKeys] = React.useState<ApiKeyList | null>(null)
  const [usage, setUsage] = React.useState<UsageSummary | null>(null)
  const [error, setError] = React.useState<ReviewError | null>(null)
  const [loading, setLoading] = React.useState(true)

  const [dialogOpen, setDialogOpen] = React.useState(false)
  const [issued, setIssued] = React.useState<ApiKeyIssued | null>(null)
  const [minting, setMinting] = React.useState(false)

  const [revoking, setRevoking] = React.useState<string | null>(null)
  const [pendingRevoke, setPendingRevoke] = React.useState<string | null>(null)

  const load = React.useCallback(async (signal?: AbortSignal) => {
    const [keyResult, usageResult] = await Promise.all([
      fetchApiKeys(signal),
      fetchUsage(signal),
    ])
    if (signal?.aborted) return

    if (keyResult.kind === "error") setError(keyResult.error)
    else {
      setKeys(keyResult.keys)
      setError(null)
    }

    // A usage failure does not blank the screen. The keys are what the reader came for; the
    // consumption card is context, and losing it must not cost them the table.
    if (usageResult.kind === "usage") setUsage(usageResult.usage)

    setLoading(false)
  }, [])

  React.useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  async function mint(name: string) {
    setMinting(true)
    const result = await mintApiKey(name)
    setMinting(false)

    if (result.kind === "error") {
      setError(result.error)
      setDialogOpen(false)
      return
    }
    setError(null)
    setIssued(result.key)
    void load()
  }

  async function revoke(keyId: string) {
    setRevoking(keyId)
    const result = await revokeApiKey(keyId)
    setRevoking(null)
    setPendingRevoke(null)

    if (result.kind === "error") {
      setError(result.error)
      return
    }
    setError(null)
    void load()
  }

  const rows = keys?.keys ?? []
  const active = rows.filter((key) => !key.revoked_at)

  return (
    <div className="space-y-6">
      {error ? <ErrorPanel error={error} /> : null}

      <UsageSummaryCard usage={usage} loading={loading} />

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
          <div className="space-y-1.5">
            <CardTitle>API-Schlüssel</CardTitle>
            <CardDescription>
              {active.length === 0
                ? "Noch kein aktiver Schlüssel. Ein Schlüssel wird für die Anbindung eines PVS oder eines Rechnungszentrums an die Schnittstelle benötigt."
                : `${active.length} aktive${active.length === 1 ? "r" : ""} Schlüssel für diese Praxis.`}
            </CardDescription>
          </div>
          <Button
            onClick={() => {
              setIssued(null)
              setDialogOpen(true)
            }}
          >
            <KeyRoundIcon />
            Neuer Schlüssel
          </Button>
        </CardHeader>

        <CardContent>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Für diese Praxis wurde noch kein API-Schlüssel erstellt.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Bezeichnung</TableHead>
                  <TableHead>Kennung</TableHead>
                  <TableHead>Erstellt</TableHead>
                  <TableHead>Zuletzt verwendet</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Aktion</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((key) => {
                  const revoked = Boolean(key.revoked_at)
                  return (
                    <TableRow key={key.key_id} className={revoked ? "opacity-60" : undefined}>
                      <TableCell className="font-medium">
                        {key.name || "Ohne Bezeichnung"}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {key.key_id}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {stamp(key.created_at)}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {stamp(key.last_used_at)}
                      </TableCell>
                      <TableCell>
                        {revoked ? (
                          <Badge variant="outline">
                            Widerrufen {stamp(key.revoked_at)}
                          </Badge>
                        ) : (
                          <Badge variant="secondary">Aktiv</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {revoked ? null : (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={revoking === key.key_id}
                            onClick={() => setPendingRevoke(key.key_id)}
                          >
                            {revoking === key.key_id ? (
                              <Loader2Icon className="animate-spin" />
                            ) : (
                              <ShieldOffIcon />
                            )}
                            Widerrufen
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}

          <p className="mt-4 text-xs text-muted-foreground">
            <span className="font-mono">last_used_at</span> ist auf etwa eine
            Minute genau — die Spalte wird bewusst nicht bei jeder Anfrage
            geschrieben. Widerrufene Schlüssel bleiben in dieser Liste, damit
            „am 3. widerrufen“ von „hat es nie gegeben“ unterscheidbar bleibt.
          </p>
        </CardContent>
      </Card>

      <NewKeyDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open)
          if (!open) setIssued(null)
        }}
        onMint={(name) => void mint(name)}
        issued={issued}
        minting={minting}
      />

      <AlertDialog
        open={pendingRevoke !== null}
        onOpenChange={(open) => {
          if (!open) setPendingRevoke(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Schlüssel widerrufen?</AlertDialogTitle>
            <AlertDialogDescription>
              Jede Anfrage mit diesem Schlüssel wird ab sofort abgelehnt. Eine
              Anwendung, die ihn noch verwendet, erhält{" "}
              <span className="font-mono">401 API_KEY_INVALID</span> — prüfen
              Sie vorher, welche Integration daran hängt. Der Vorgang lässt sich
              nicht rückgängig machen; ein Ersatz muss neu erstellt werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingRevoke) void revoke(pendingRevoke)
              }}
            >
              Endgültig widerrufen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
