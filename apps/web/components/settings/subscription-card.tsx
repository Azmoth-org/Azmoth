"use client"

import * as React from "react"
import { CreditCardIcon, Loader2Icon, TrendingUpIcon } from "lucide-react"

import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"
import { Progress } from "@workspace/ui/components/progress"
import { Skeleton } from "@workspace/ui/components/skeleton"

import {
  fetchPlans,
  upgradePlan,
  type BillingUsage,
  type PlanCatalog,
  type ReviewError,
} from "@/lib/settings/client"

/**
 * `99,00 €` from `9900`. The only place in this component that turns cents into money.
 *
 * The API carries integer cents and never a decimal, so the division happens once, at the point of
 * display, and its result is never stored or compared. `Intl.NumberFormat` rather than
 * `toFixed(2) + " €"` because German writes `1.234,50 €` and the separator convention is not
 * something to reimplement per component.
 */
function euro(cents: number): string {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(cents / 100)
}

/** `2.500` — grouped, so a five-digit quota is readable at a glance. */
function count(value: number): string {
  return value.toLocaleString("de-DE")
}

/** `31. August 2026` — the date a practice's period rolls over. */
function day(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleDateString("de-DE", { dateStyle: "long" })
}

/** What a tier is called on screen. The engine sends the machine value; this is the German. */
const TIER_LABEL: Record<string, string> = {
  free: "Kostenlos",
  starter: "Starter",
  pro: "Pro",
  enterprise: "Enterprise",
}

/**
 * The usage meter, and the way to a bigger plan.
 *
 * ## Why the bar is capped at 100% and the overage is a separate line
 *
 * A progress bar that went to 140% is not a progress bar, and one that silently clamped would tell a
 * practice they are "full" whether they are at 100 or at 300. So the bar saturates and the overage
 * gets its own row with its own euro figure — which is the number somebody actually wants when they
 * are over: not "how full", but "what is this costing".
 *
 * ## Why the period is always printed
 *
 * This is the figure a practice checks an invoice against, and the window is **not** the calendar
 * month: it is anchored on the day the practice was created. The card beneath this one
 * (`UsageSummaryCard`) reports the calendar month on purpose, so the two numbers can legitimately
 * differ — and the only thing that makes that legible rather than alarming is that both say which
 * window they used.
 *
 * ## Why the upgrade sends a plan code and not a tier
 *
 * The reader has just been shown a list of plans with prices on them. Sending the code of the one
 * they clicked means they get the plan they were shown; sending a tier would let the engine resolve
 * it to whatever revision is current, which could be a different price from the one on screen.
 *
 * ## What this component does not do
 *
 * It does not take a payment. There is no card field and no mandate, because the engine's
 * `POST /billing/upgrade` records a plan and does not collect money for it — see `docs/BILLING.md`.
 * The dialog says so, rather than implying a charge that will not happen.
 */
export function SubscriptionCard({
  billing,
  loading,
  onUpgraded,
  onError,
}: {
  billing: BillingUsage | null
  loading: boolean
  /** Called after a successful plan change, so the parent can reload the figures. */
  onUpgraded: () => void
  onError: (error: ReviewError) => void
}) {
  const [open, setOpen] = React.useState(false)
  const [catalog, setCatalog] = React.useState<PlanCatalog | null>(null)
  const [choosing, setChoosing] = React.useState<string | null>(null)

  // Fetched when the dialog opens rather than with the card. A price list is not what the reader
  // came to this screen for, and one request per visit for a list most visits never open is a
  // request per visit wasted.
  React.useEffect(() => {
    if (!open || catalog) return
    const controller = new AbortController()
    void fetchPlans(controller.signal).then((result) => {
      if (controller.signal.aborted) return
      if (result.kind === "plans") setCatalog(result.catalog)
      else onError(result.error)
    })
    return () => controller.abort()
  }, [open, catalog, onError])

  async function choose(planCode: string) {
    setChoosing(planCode)
    const result = await upgradePlan(planCode)
    setChoosing(null)

    if (result.kind === "error") {
      onError(result.error)
      return
    }
    setOpen(false)
    onUpgraded()
  }

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CreditCardIcon className="size-4" />
            Tarif und Kontingent
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (!billing) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CreditCardIcon className="size-4" />
            Tarif und Kontingent
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Der Tarif konnte nicht geladen werden. Die Prüfung selbst ist davon nicht
            betroffen — das Kontingent wird serverseitig geprüft, unabhängig von dieser
            Anzeige.
          </p>
        </CardContent>
      </Card>
    )
  }

  const { subscription } = billing
  const quota = subscription.monthly_invoice_quota
  const used = billing.invoices_processed
  // Saturated on purpose — see the component docstring. `quota` of 0 would divide by zero; no
  // seeded plan has one, but a bespoke plan could, and a `NaN` width is a broken bar.
  const percent = quota > 0 ? Math.min(100, Math.round((used / quota) * 100)) : 0
  const over = billing.overage_invoices > 0

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2">
              <CreditCardIcon className="size-4" />
              Tarif und Kontingent
            </CardTitle>
            <CardDescription>
              Abrechnungszeitraum bis {day(subscription.current_period_end)}. Gezählt
              werden geprüfte Rechnungen, nicht API-Aufrufe.
            </CardDescription>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Badge variant="secondary">
              {TIER_LABEL[subscription.subscription_tier] ?? subscription.plan_label}
            </Badge>
            <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
              <TrendingUpIcon />
              Tarif ändern
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-baseline justify-between gap-4">
              <p className="text-sm">
                <span className="text-display-md tabular-nums">{count(used)}</span>
                <span className="text-muted-foreground">
                  {" "}
                  von {count(quota)} Rechnungen verbraucht
                </span>
              </p>
              <p className="shrink-0 text-sm tabular-nums text-muted-foreground">
                {percent} %
              </p>
            </div>

            <Progress value={percent} aria-label="Verbrauchtes Kontingent" />

            <p className="text-xs text-muted-foreground">
              {over
                ? `Kontingent ausgeschöpft. ${count(billing.overage_invoices)} Rechnungen über dem Kontingent.`
                : `${count(billing.remaining)} Rechnungen verbleiben in diesem Zeitraum.`}
            </p>
          </div>

          <dl className="grid grid-cols-2 gap-4 border-t pt-4 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">Grundgebühr</dt>
              <dd className="text-sm tabular-nums">
                {euro(billing.base_fee_cents)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Mehrverbrauch</dt>
              <dd className="text-sm tabular-nums">
                {over ? euro(billing.overage_cents) : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">
                Bisher in diesem Zeitraum
              </dt>
              <dd className="text-sm tabular-nums">
                {euro(billing.projected_total_cents)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">API-Aufrufe</dt>
              <dd className="text-sm tabular-nums">{count(billing.requests)}</dd>
            </div>
          </dl>

          {/*
            The pilot's one honest sentence. Every tier is priced at zero during the pilot and the
            usage is metered in full anyway, which is the arrangement that makes a later
            conversation about volume possible at all. Saying so here is better than a screen that
            shows euro amounts a practice is not being charged.
          */}
          {billing.projected_total_cents === 0 ? (
            <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              In der Pilotphase fallen keine Kosten an. Der Verbrauch wird vollständig
              erfasst, damit später eine belastbare Grundlage für die Abrechnung
              vorliegt.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Tarif ändern</DialogTitle>
            <DialogDescription>
              Der Abrechnungszeitraum wird dabei nicht neu gestartet: das Kontingent
              ändert sich sofort, der bisherige Verbrauch bleibt erhalten. Es wird keine
              Zahlung ausgelöst.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            {catalog === null ? (
              <Skeleton className="h-40 w-full" />
            ) : (
              // `plans` is optional in the generated contract (Pydantic's `default_factory`
              // publishes it as not-required), so it is defaulted rather than asserted.
              (catalog.plans ?? []).map((entry) => {
                const current = entry.code === subscription.plan_code
                return (
                  <div
                    key={entry.code}
                    className="flex items-center justify-between gap-4 rounded-md border px-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">
                        {entry.label}
                        {current ? (
                          <Badge variant="outline" className="ml-2">
                            Aktuell
                          </Badge>
                        ) : null}
                      </p>
                      <p className="text-xs tabular-nums text-muted-foreground">
                        {euro(entry.base_fee_cents)} / Zeitraum ·{" "}
                        {count(entry.monthly_invoice_quota)} Rechnungen
                        {entry.allow_overage
                          ? ` · danach ${euro(entry.overage_rate_cents)} je Rechnung`
                          : " · danach keine weiteren Prüfungen"}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant={current ? "ghost" : "default"}
                      disabled={current || choosing !== null}
                      onClick={() => void choose(entry.code)}
                    >
                      {choosing === entry.code ? (
                        <Loader2Icon className="animate-spin" />
                      ) : null}
                      {current ? "Gewählt" : "Wählen"}
                    </Button>
                  </div>
                )
              })
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Schliessen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
