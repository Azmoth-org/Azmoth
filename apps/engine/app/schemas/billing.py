"""The wire shapes for subscriptions, quota consumption and priced periods.

Two conventions run through all of these, and both are worth stating once here rather than in every
field description.

**Every euro amount is an integer count of cents**, named `*_cents`, and there is no field anywhere
that carries a formatted amount. `9900` and not `99.00`, not `"99,00 €"`. A JSON number that looks
like money invites a client to parse it as a float, and the sum of a few thousand overage lines is
exactly where that stops being harmless. Formatting `1.234,50 €` is the presenting tier's job, and
`apps/web` does it with `Intl.NumberFormat`.

**Every window is stated, never implied**, and every one of them is half-open: `period_start`
inclusive, `period_end` exclusive. That is what makes consecutive periods partition the timeline
instead of overlapping at the instant they touch. `GET /api/v1/settings/usage` uses an *inclusive*
end because it answers a different question — "what have we used so far", where the end is now — and
says so in its own schema. Two endpoints, two windows, both explicit.

The quota figures a reader sees here are the same `SUM(invoices_processed)` the refusal at 101 is
computed from, so a screen saying "47 of 50" and a `429` cannot disagree.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlanSummary(BaseModel):
    """One plan a practice could be on, as the catalog describes it.

    Read-only and derived from `app.services.billing_plans`, which is append-only: a plan a practice
    is already on keeps its numbers even after a newer revision supersedes it. `code` carries the
    revision (`starter-2026.08`) so a client can name a price exactly rather than by tier.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        description=(
            "Die Tarif-SKU mit Revision, z. B. `starter-2026.08`. Preise werden nie geändert, "
            "sondern durch eine neue Revision ersetzt. — The plan SKU including its revision; "
            "prices are superseded, never edited."
        )
    )
    tier: str = Field(description="`free`, `starter`, `pro` oder `enterprise`.")
    label: str = Field(description="Anzeigename für die Oberfläche. — Display name.")
    base_fee_cents: int = Field(
        description=(
            "Grundgebühr je Abrechnungszeitraum in Euro-Cent. — Recurring fee per period, in "
            "euro cents."
        )
    )
    monthly_invoice_quota: int = Field(
        description=(
            "Wie viele Rechnungen die Grundgebühr je Zeitraum umfasst. — How many invoices the "
            "base fee includes per period."
        )
    )
    overage_rate_cents: int = Field(
        description=(
            "Preis je zusätzlicher Rechnung über dem Kontingent, in Euro-Cent. Ohne Bedeutung, "
            "wenn `allow_overage` false ist. — Price per invoice above the quota."
        )
    )
    allow_overage: bool = Field(
        description=(
            "Ob eine Prüfung über dem Kontingent erlaubt (und berechnet) wird oder mit "
            "`429 QUOTA_EXCEEDED` abgelehnt wird. — Whether going over is charged or refused."
        )
    )


class SubscriptionSummary(BaseModel):
    """What one practice is entitled to, and which period that entitlement is for.

    **These numbers come from the practice's own row, not from the plan catalog.** They were copied
    onto it when the plan was assigned, so a later change to the catalog cannot retroactively alter
    what was agreed — see `app.db.models.OrganizationBillingRecord`. `plan_code` says what they were
    taken from; it is not where they are read from now.
    """

    model_config = ConfigDict(extra="forbid")

    organization_id: str
    subscription_tier: str = Field(description="`free`, `starter`, `pro` oder `enterprise`.")
    plan_code: str
    plan_label: str
    monthly_invoice_quota: int
    overage_rate_cents: int
    allow_overage: bool
    current_period_start: datetime = Field(
        description=(
            "Beginn des laufenden Abrechnungszeitraums, einschliesslich, UTC. Der Zeitraum ist an "
            "den Tag gebunden, an dem die Praxis angelegt wurde — nicht an den Monatsersten. — "
            "Inclusive start of the open period, anchored on the practice's own billing day."
        )
    )
    current_period_end: datetime = Field(
        description=(
            "Ende des laufenden Zeitraums, ausschliesslich, UTC. — Exclusive end of the open "
            "period."
        )
    )


class BillingUsage(BaseModel):
    """What the open period has consumed, and what it would cost if nothing more happened.

    `projected_total_cents` is deliberately **not** a forecast. It is the base fee plus the overage
    accrued so far, so it only ever goes up and two readers see the same number. Extrapolating from
    four days of a month would produce a figure that changed every time somebody looked at it, on a
    screen whose entire purpose is checking an invoice against.
    """

    model_config = ConfigDict(extra="forbid")

    subscription: SubscriptionSummary

    invoices_processed: int = Field(
        description=(
            "Geprüfte Rechnungen im laufenden Zeitraum. **Die abrechenbare Einheit** — nicht die "
            "Anzahl der API-Aufrufe: ein Bulk-Upload mit 300 Lieferungen ist ein Aufruf und 300 "
            "Rechnungen. — Invoices audited in the open period; the billable unit."
        )
    )
    requests: int = Field(
        description=(
            "Zurechenbare API-Aufrufe im selben Zeitraum, einschliesslich der fehlgeschlagenen. "
            "Nur zur Einordnung — berechnet wird nach Rechnungen. — Attributable API calls, for "
            "context only."
        )
    )
    remaining: int = Field(
        description=(
            "Verbleibendes Kontingent, mindestens 0. — Remaining quota, floored at zero."
        )
    )
    overage_invoices: int = Field(
        description="Rechnungen über dem Kontingent. — Invoices above the quota."
    )
    overage_cents: int = Field(
        description="Bisher angefallene Mehrverbrauchskosten. — Overage accrued so far, in cents."
    )
    base_fee_cents: int
    projected_total_cents: int = Field(
        description=(
            "Grundgebühr plus bisheriger Mehrverbrauch. Keine Prognose — siehe die Beschreibung "
            "dieses Modells. — Base fee plus overage so far. Not a forecast."
        )
    )


class BillingInvoice(BaseModel):
    """One closed period, priced. Every amount stored rather than derived on read.

    Derived totals would mean an issued figure could change when a helper's rounding changed, which
    is the one thing an amount somebody has been told must not do.
    """

    model_config = ConfigDict(extra="forbid")

    invoice_id: str = Field(description="`inv_<hex>` — opaque public handle.")
    organization_id: str
    period_start: datetime
    period_end: datetime
    plan_code: str = Field(
        description=(
            "Der Tarif, unter dem dieser Zeitraum berechnet wurde — gespeichert, nicht "
            "nachgeschlagen. Er kann inzwischen abgelöst sein. — The plan this period was priced "
            "under, stored rather than looked up; it may since have been superseded."
        )
    )
    subscription_tier: str

    base_fee_cents: int
    invoices_included: int = Field(
        description="Das Kontingent, das die Grundgebühr umfasste. — The quota the base fee bought."
    )
    invoices_processed: int
    overage_invoices: int
    overage_rate_cents: int
    overage_fee_cents: int
    total_cents: int = Field(
        description="`base_fee_cents + overage_fee_cents`. — The sum, stored."
    )
    currency: str = Field(description="ISO 4217, derzeit immer `EUR`. — Currently always `EUR`.")
    status: str = Field(
        description=(
            "`ISSUED` für einen abgeschlossenen Zeitraum, `VOID` wenn durch eine Korrektur "
            "ersetzt. Ein Betrag wird nie an Ort und Stelle korrigiert. — `ISSUED`, or `VOID` when "
            "superseded by a correction. An amount is never edited in place."
        )
    )
    issued_at: datetime


class BillingInvoiceList(BaseModel):
    """This practice's invoices, newest period first."""

    model_config = ConfigDict(extra="forbid")

    invoices: list[BillingInvoice] = Field(default_factory=list)
    total: int = Field(description="Wie viele zurückgegeben wurden. — How many were returned.")


class UpgradeRequest(BaseModel):
    """A plan change, named either by tier or by exact plan code.

    Two ways to say it, because they answer different needs. `tier` is what a settings screen sends
    — "put us on Pro" — and resolves to today's selectable revision of that tier. `plan_code` names
    one exactly, which is what an operator moving a practice onto a specific historical or bespoke
    price needs.

    Exactly one must be given. Both, or neither, is a `422` rather than a precedence rule nobody
    would remember: a request that specified a tier *and* a mismatched code has two plausible
    readings and no safe default.

    Nothing here names an organisation. The practice is whichever one the session is active in, for
    the same reason `ApiKeyRequest` carries no tenant: a body field naming one would be an endpoint
    for changing somebody else's subscription.
    """

    model_config = ConfigDict(extra="forbid")

    tier: str | None = Field(
        default=None,
        description=(
            "Zieltarif: `free`, `starter`, `pro` oder `enterprise`. Löst auf die aktuell "
            "wählbare Revision dieses Tarifs auf. — Target tier; resolves to today's selectable "
            "revision."
        ),
    )
    plan_code: str | None = Field(
        default=None,
        description=(
            "Genaue Tarif-SKU, z. B. `pro-2026.08`. Alternative zu `tier`, wenn eine bestimmte "
            "Revision gemeint ist. — An exact plan SKU, as an alternative to `tier`."
        ),
    )


class UpgradeResult(BaseModel):
    """The subscription after the change, plus what it was before.

    `previous_*` is here so a client can render "Starter → Pro" without having read the state first,
    and so a log or an audit trail built on the response can say what actually moved. A response
    that only carried the new state would make "was this a no-op" unanswerable.
    """

    model_config = ConfigDict(extra="forbid")

    subscription: SubscriptionSummary
    previous_plan_code: str
    previous_tier: str
    changed: bool = Field(
        description=(
            "False, wenn die Praxis bereits auf diesem Tarif war. Der Aufruf ist dann ein "
            "erfolgreiches No-op und kein Fehler. — False when the practice was already on this "
            "plan; the call is a successful no-op, not an error."
        )
    )


class PlanCatalog(BaseModel):
    """Every plan a practice may move to, cheapest first."""

    model_config = ConfigDict(extra="forbid")

    plans: list[PlanSummary] = Field(default_factory=list)


__all__ = [
    "BillingInvoice",
    "BillingInvoiceList",
    "BillingUsage",
    "PlanCatalog",
    "PlanSummary",
    "SubscriptionSummary",
    "UpgradeRequest",
    "UpgradeResult",
]
