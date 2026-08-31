"""The commercial surface: what a practice is on, what it has used, and what it has cost.

    GET  /api/v1/billing/plans      the catalog — every plan a practice may move to
    GET  /api/v1/billing/usage      the open period: tier, invoices used, remaining, overage
    POST /api/v1/billing/upgrade    change plan
    GET  /api/v1/billing/invoices   the closed periods, priced

## Who may call which, and why the two answers differ

`usage`, `plans` and `invoices` are readable **either** with an API key or from a signed-in session,
through the same `resolve_reader` branch `GET /api/v1/settings/usage` already uses. A partner
integrating against the API has to be able to see what they are spending without opening a browser,
and a practice manager has to see it in the web application where there is a session and no key.
Whichever credential is presented decides the organisation; there is no parameter that names one.

`upgrade` is **session only**, and that is a deliberate asymmetry rather than an oversight. It is a
commercial commitment — it changes what a practice will be invoiced — and the right authority for it
is a signed-in human who is a member of the practice, not a bearer token that may be sitting in a
PVS vendor's config file. It is the same boundary `POST /api/v1/settings/api-keys` sits behind, for
a related reason: an API key must not be able to escalate its own entitlements.

The practical consequence is worth being explicit about: a partner whose integration is refused with
`429 QUOTA_EXCEEDED` cannot resolve it from the API. The refusal names the plan and the endpoint, and
somebody at the practice does the upgrade. That is the correct division — the person who pays should
be the person who agrees to pay more.

## There is no path segment naming an organisation, anywhere here

`/billing/usage` and not `/organizations/{id}/billing/usage`, exactly as `/settings/api-keys` has no
id in it. The organisation is whichever one the credential resolves to, so there is no segment a
caller could edit to read — or change — another practice's subscription.

## What this module does not do

No payment. No card, no SEPA mandate, no Stripe, no dunning, no VAT. `POST /billing/upgrade` records
that a practice is on a plan; it does not collect money for it, and `billing_invoices` is a priced
record rather than a Rechnung in the legal sense. That boundary is where it is on purpose — see
`docs/BILLING.md`, which says what a real payment integration would have to add and what it must not
change.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException, Query, status

from app.api.deps import billing
from app.api.identity import RequestActor
from app.api.settings_keys import UsageReader
from app.api.tenancy import RequestOrganization
from app.db.models import as_utc
from app.schemas.billing import (
    BillingInvoice,
    BillingInvoiceList,
    BillingUsage,
    PlanCatalog,
    PlanSummary,
    SubscriptionSummary,
    UpgradeRequest,
    UpgradeResult,
)
from app.services.billing import Entitlement, PeriodUsage
from app.services.billing_plans import (
    Plan,
    SubscriptionTier,
    plan as plan_by_code,
    plan_for_tier,
    selectable_plans,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

#: How many invoices the listing returns by default and at most. Two years of monthly periods is
#: more than any screen shows and is bounded, so a long-lived practice cannot turn the endpoint into
#: an unbounded response.
DEFAULT_INVOICE_LIMIT = 24
MAX_INVOICE_LIMIT = 120


def _plan_summary(found: Plan) -> PlanSummary:
    return PlanSummary(
        code=found.code,
        tier=found.tier.value,
        label=found.label,
        base_fee_cents=found.base_fee_cents,
        monthly_invoice_quota=found.monthly_invoice_quota,
        overage_rate_cents=found.overage_rate_cents,
        allow_overage=found.allow_overage,
    )


def _subscription(entitlement: Entitlement) -> SubscriptionSummary:
    return SubscriptionSummary(
        organization_id=entitlement.organization_id,
        subscription_tier=entitlement.subscription_tier.value,
        plan_code=entitlement.plan_code,
        plan_label=entitlement.plan_label,
        monthly_invoice_quota=entitlement.monthly_invoice_quota,
        overage_rate_cents=entitlement.overage_rate_cents,
        allow_overage=entitlement.allow_overage,
        current_period_start=entitlement.period_start,
        current_period_end=entitlement.period_end,
    )


def _usage(period: PeriodUsage) -> BillingUsage:
    return BillingUsage(
        subscription=_subscription(period.entitlement),
        invoices_processed=period.invoices_processed,
        requests=period.requests,
        remaining=period.remaining,
        overage_invoices=period.overage_invoices,
        overage_cents=period.overage_cents,
        base_fee_cents=period.base_fee_cents,
        projected_total_cents=period.projected_total_cents,
    )


# ------------------------------------------------------------------------------------------
# the catalog
# ------------------------------------------------------------------------------------------


@router.get("/plans", response_model=PlanCatalog, summary="Verfügbare Tarife")
async def read_plans(organization: UsageReader) -> PlanCatalog:
    """Die Tarife, auf die diese Praxis wechseln kann — vom günstigsten zum teuersten.

    Abgelöste Revisionen erscheinen hier **nicht**. Preise werden nie geändert, sondern durch eine
    neue Revision ersetzt; eine Praxis auf einer älteren Revision behält deren Konditionen, aber
    neu wählbar ist nur die aktuelle. Der eigene Tarif steht in `GET /api/v1/billing/usage` und
    kann eine abgelöste Revision sein.

    **Alle Beträge in Euro-Cent als ganze Zahl.** `9900` bedeutet 99,00 €.

    ---

    The plans a practice may move to, cheapest first. Superseded revisions are excluded: prices are
    append-only, so a practice on an older revision keeps its terms but only the current one can be
    newly selected — their own plan is in `GET /api/v1/billing/usage` and may be a superseded code.

    Requires a credential (a key or a session) even though the catalog is not tenant data. That is a
    deliberate choice rather than an oversight: a price list is commercially sensitive before launch,
    and the marketing site is where a public one belongs.
    """
    # `organization` is not used to filter anything — the catalog is the same for everybody. It is
    # in the signature to require *a* credential, and naming it makes that visible rather than
    # hiding the requirement in a bare `Depends`.
    del organization
    return PlanCatalog(plans=[_plan_summary(found) for found in selectable_plans()])


# ------------------------------------------------------------------------------------------
# the open period
# ------------------------------------------------------------------------------------------


@router.get("/usage", response_model=BillingUsage, summary="Kontingent und Verbrauch")
async def read_billing_usage(organization: UsageReader) -> BillingUsage:
    """Tarif, verbrauchte Rechnungen, verbleibendes Kontingent und angefallener Mehrverbrauch.

    **Gezählt werden Rechnungen, nicht Aufrufe.** Ein Bulk-Upload mit 300 Lieferungen ist ein
    API-Aufruf und 300 Rechnungen — `invoices_processed` ist die abrechenbare Einheit,
    `requests` steht nur zur Einordnung daneben.

    Der Zeitraum ist der Abrechnungszeitraum dieser Praxis und **nicht** der Kalendermonat: er ist
    an den Tag gebunden, an dem die Praxis angelegt wurde. `GET /api/v1/settings/usage` beantwortet
    bewusst die andere Frage — Verbrauch im laufenden Kalendermonat — und beide nennen den Zeitraum,
    den sie verwendet haben. Wer beide Zahlen vergleicht, muss auf diese Fenster achten.

    `projected_total_cents` ist keine Prognose, sondern Grundgebühr plus bisher angefallener
    Mehrverbrauch: eine Zahl, die nur steigt und die zwei Leser gleich lesen.

    ---

    The open billing period: which plan, how many invoices audited, how many remain, what overage
    has accrued. Readable with an API key or from a session; the credential decides the practice.

    The window is the practice's own billing period, anchored on the day they were created — not the
    calendar month, which is what `GET /api/v1/settings/usage` reports. Both state their window.

    Reading this also **rolls the period** if the stored one has ended, which writes an invoice for
    each period that closed. There is no scheduler in this service, so the first request of a new
    period is what closes the previous one — see `app.services.billing`.
    """
    # Flush before reading, for the reason `read_usage` gives at length: the meter buffers up to 25
    # rows or 15 seconds, and a practice that has just audited five invoices must not be told they
    # have audited none. "Zero" reads as "metering is broken", and the reader cannot tell that it is
    # not. Safe here because it happens inside a request — no background task, no interleaving.
    from app.api.deps import usage_meter

    await usage_meter().flush()

    return _usage(await billing().period_usage(organization))


# ------------------------------------------------------------------------------------------
# changing plan
# ------------------------------------------------------------------------------------------


@router.post(
    "/upgrade",
    response_model=UpgradeResult,
    status_code=status.HTTP_200_OK,
    summary="Tarif wechseln",
)
async def upgrade_subscription(
    organization: RequestOrganization,
    actor: RequestActor,
    body: UpgradeRequest = Body(...),
) -> UpgradeResult:
    """Wechselt den Tarif dieser Praxis. Nur aus einer angemeldeten Sitzung, nicht mit API-Schlüssel.

    Zieltarif entweder als `tier` (`free`, `starter`, `pro`, `enterprise` — löst auf die aktuell
    wählbare Revision auf) oder als genaue `plan_code`. Genau eine der beiden Angaben ist
    erforderlich.

    **Der Abrechnungszeitraum wird nicht neu gestartet.** Ein Wechsel mitten im Zeitraum erhöht das
    Kontingent und lässt das Fenster unverändert: wer 480 von 500 Rechnungen verbraucht hat und auf
    Pro wechselt, hat sofort 2.020 übrig — nicht ein neues Kontingent und eine Zeitraumgrenze mitten
    im Monat. Eine anteilige Berechnung der Grundgebühr (Proration) ist bewusst nicht implementiert;
    siehe `docs/BILLING.md`.

    **Auch ein Wechsel nach unten ist erlaubt.** Der Aufruf heisst `upgrade`, weil das der Normalfall
    ist; die Engine verweigert keinen Wechsel nach unten. Liegt der bisherige Verbrauch über dem
    neuen Kontingent, gilt ab sofort das neue: bei einem Tarif ohne Mehrverbrauch führt das zu
    `429 QUOTA_EXCEEDED`, bis der Zeitraum wechselt. `changed: false` heisst, die Praxis war bereits
    auf diesem Tarif — ein erfolgreiches No-op und kein Fehler.

    Fehler: `422` wenn weder `tier` noch `plan_code` angegeben ist oder beide, `404` wenn der Tarif
    nicht existiert oder nicht (mehr) wählbar ist, `403` wenn die Anfrage keine Praxis nennt.

    ---

    Change this practice's plan. Session only — not with an API key, because it is a commercial
    commitment and a key must not be able to escalate its own entitlements. See the module docstring.

    Target named by `tier` or by exact `plan_code`; exactly one. The period is not restarted, and a
    downgrade is permitted. Idempotent in the sense that matters: naming the current plan succeeds
    and reports `changed: false`.
    """
    named = [value for value in (body.tier, body.plan_code) if value]
    if len(named) != 1:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "ambiguous_plan",
                "message": (
                    "Geben Sie genau eines von `tier` oder `plan_code` an. Beides gleichzeitig hat "
                    "zwei plausible Lesarten und keine sichere Voreinstellung; keines von beiden "
                    "nennt kein Ziel. — Give exactly one of `tier` or `plan_code`."
                ),
            },
        )

    if body.plan_code:
        target = plan_by_code(body.plan_code)
        if target is None or not target.selectable:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "unknown_plan",
                    "message": (
                        f"Der Tarif {body.plan_code!r} ist unbekannt oder nicht wählbar. "
                        "GET /api/v1/billing/plans nennt die wählbaren Tarife. — Unknown or "
                        "non-selectable plan."
                    ),
                    "requested": body.plan_code,
                    "available": [found.code for found in selectable_plans()],
                },
            )
    else:
        try:
            tier = SubscriptionTier(str(body.tier))
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "unknown_tier",
                    "message": (
                        f"{body.tier!r} ist keiner der Tarife `free`, `starter`, `pro`, "
                        "`enterprise`. — Not one of the four tiers."
                    ),
                    "requested": body.tier,
                    "available": [member.value for member in SubscriptionTier],
                },
            ) from None

        target = plan_for_tier(tier)
        if target is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "no_selectable_plan",
                    "message": (
                        f"Für den Tarif {tier.value!r} gibt es in dieser Installation keinen "
                        "wählbaren Preis. — This deployment has no selectable plan for that tier."
                    ),
                    "requested": tier.value,
                },
            )

    # Read before writing, so the response can say what moved. One extra query on an endpoint
    # nobody calls in a loop, and it is what makes "Starter → Pro" renderable without the client
    # having fetched the state first.
    before = await billing().entitlement(organization)
    after = await billing().assign_plan(organization, target, actor=actor)

    changed = before.plan_code != after.plan_code
    if changed:
        log.info(
            "organisation %s moved from %s to %s by %s",
            organization,
            before.plan_code,
            after.plan_code,
            actor,
        )

    return UpgradeResult(
        subscription=_subscription(after),
        previous_plan_code=before.plan_code,
        previous_tier=before.subscription_tier.value,
        changed=changed,
    )


# ------------------------------------------------------------------------------------------
# the closed periods
# ------------------------------------------------------------------------------------------


@router.get("/invoices", response_model=BillingInvoiceList, summary="Abgerechnete Zeiträume")
async def read_invoices(
    organization: UsageReader,
    limit: int = Query(
        default=DEFAULT_INVOICE_LIMIT,
        ge=1,
        le=MAX_INVOICE_LIMIT,
        description=(
            "Wie viele Zeiträume höchstens, neueste zuerst. — At most this many periods, newest "
            "first."
        ),
    ),
) -> BillingInvoiceList:
    """Die abgeschlossenen Abrechnungszeiträume dieser Praxis, neuester zuerst.

    Ein Eintrag entsteht, wenn ein Zeitraum endet — nicht durch einen Zahlungsvorgang. Er nennt den
    Tarif, unter dem der Zeitraum berechnet wurde, das enthaltene Kontingent, die tatsächlich
    geprüften Rechnungen, den Mehrverbrauch und die Summe. Alle Beträge in Euro-Cent.

    **Ein Zeitraum ohne Verbrauch erhält ebenfalls einen Eintrag**, mit Summe 0. „August: nichts
    fällig" und „August: kein Eintrag" sind verschiedene Aussagen, und nur die erste lässt sich
    abgleichen.

    **Dies ist keine Rechnung im rechtlichen Sinn.** Keine Umsatzsteuer, keine Rechnungsnummer im
    Sinne des § 14 UStG, keine Zahlungsbedingungen — es ist die Grundlage, aus der eine solche
    Rechnung erstellt wird.

    Der laufende, noch nicht abgeschlossene Zeitraum steht in `GET /api/v1/billing/usage` und
    erscheint hier bewusst nicht: ein Betrag, der sich noch ändert, gehört nicht in eine Liste
    abgerechneter Zeiträume.

    ---

    The closed billing periods, newest first — one row per period that ended, with the plan it was
    priced under and every amount in euro cents. A period with no usage still gets a row, with a
    zero total. The open period is not listed; it is in `GET /api/v1/billing/usage`.

    Not a Rechnung in the legal sense: no VAT, no invoice-number series, no payment terms.
    """
    rows = await billing().list_invoices(organization_id=organization, limit=limit)
    invoices = [
        BillingInvoice(
            invoice_id=row.public_id,
            organization_id=row.organization_id,
            # `as_utc` on every timestamp: SQLite hands back exactly the naive value that was
            # written, and a response that dropped the zone would be read as local time by whoever
            # parsed it. Postgres returns aware values and this is a no-op there.
            period_start=as_utc(row.period_start),
            period_end=as_utc(row.period_end),
            plan_code=row.plan_code,
            subscription_tier=row.subscription_tier,
            base_fee_cents=row.base_fee_cents,
            invoices_included=row.invoices_included,
            invoices_processed=row.invoices_processed,
            overage_invoices=row.overage_invoices,
            overage_rate_cents=row.overage_rate_cents,
            overage_fee_cents=row.overage_fee_cents,
            total_cents=row.total_cents,
            currency=row.currency,
            status=row.status,
            issued_at=as_utc(row.issued_at),
        )
        for row in rows
    ]
    return BillingInvoiceList(invoices=invoices, total=len(invoices))
