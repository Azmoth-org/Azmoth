"""The quota gate: one function every audit path calls before it audits.

`app.api.ratelimit` protects the *service* — a Soufflé pool from a client in a `while True`. This
protects the *invoice*. They are both `429` and they are otherwise unrelated, which is why they are
separate modules with separate error codes; see `app.errors.QuotaExceeded` on why a client that
cannot tell them apart backs off for three weeks.

## Where it runs, and why two of the four are not dependencies

    POST /api/v1/audit/single     dependency      1 invoice, known before the body is read
    POST /api/v1/audit/bulk       in the handler  N invoices, known only after the ZIP is opened
    POST /api/v1/padnext/audit    in the handler  1 invoice, and only if the caller named a tenant
    POST /api/v1/padnext/batch    in the handler  N invoices, known only after the parts are read

A dependency is the right shape when the count is a constant and the tenant is already resolved:
`/audit/single` is refused before FastAPI reads a 5 MB body, which is the cheapest possible refusal.

The other three cannot be dependencies, and the reason is the same in each case: **the number of
invoices is part of the request body.** A bulk upload of 300 deliveries has to be refused *as a
unit* — a job that audited 180 files and stopped is a job somebody reconciles by hand — so the check
has to happen after `inspect_archive` has said how many there are and before any of them is queued.
That is a handler concern, and pretending otherwise would mean a dependency that reads the body,
which FastAPI would then read again.

## `/padnext/audit` is checked only when the caller says who they are, and that is deliberate

That endpoint is classified `UNSCOPED_BY_DESIGN` in `tests/test_tenancy.py`: it stores nothing, so
there is no row for a tenant to own, and the brief froze its contract. Adding `RequestOrganization`
to it would turn every call without the header into a `403` — including `/demo`, which serves a
visitor who has not signed in.

So the tenant is read **optionally**, exactly as `/padnext/audit.pdf` already reads it. When it is
present — which it is on every call the web tier proxies, because `apps/web/lib/engine.ts` sets it
from the session — the quota applies and the audit is metered against the practice. When it is
absent the audit runs unmetered, as it did before.

That is a real gap and it is worth stating rather than glossing: a caller who can reach the engine
directly and omits the header gets a free audit. It is the *same* gap `app.api.tenancy` documents at
length — the engine authenticates nobody and must not be published to the browser — and it closes
the same way, with a token the engine verifies itself. It is not a new hole: the header being
asserted rather than proven is already what the deployment shape is protecting.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Request

from app.api.apikeys import RequestApiKey
from app.api.tenancy import optional_organization
from app.errors import QuotaExceeded
from app.services.billing import QuotaDecision
from app.services.billing_plans import SubscriptionTier, plan_for_tier

log = logging.getLogger(__name__)

def _next_tier_hint(current: SubscriptionTier) -> str:
    """A German fragment naming the plan above this one, or a fallback when there is none.

    In the refusal message rather than left to the client, because the message is what a practice
    manager reads at 17:40 on a Friday. "Kontingent erschöpft" tells them nothing they can act on;
    "das Kontingent des Tarifs Starter ist erschöpft; Pro umfasst 2.500" tells them what to do.

    A practice already on the top tier is told to get in touch, which is the honest answer: there is
    no self-service step left, and inviting them to upgrade to nothing would be worse than saying so.
    """
    ladder = [
        SubscriptionTier.FREE,
        SubscriptionTier.STARTER,
        SubscriptionTier.PRO,
        SubscriptionTier.ENTERPRISE,
    ]
    try:
        following = ladder[ladder.index(current) + 1]
    except (ValueError, IndexError):
        return "Bitte wenden Sie sich an uns, um das Kontingent zu erhöhen"

    upper = plan_for_tier(following)
    if upper is None:
        return "Bitte wenden Sie sich an uns, um das Kontingent zu erhöhen"
    return (
        f"Der Tarif {upper.label} umfasst {upper.monthly_invoice_quota:,} Rechnungen pro "
        "Abrechnungszeitraum".replace(",", ".")
    )


def refuse_if_over(decision: QuotaDecision) -> QuotaDecision:
    """Raise `429 QUOTA_EXCEEDED` if this request may not run; otherwise hand the decision back.

    Returned rather than swallowed on the allowed path, because the figures go on a **successful**
    response too — `X-Quota-Limit` / `-Remaining` / `-Reset`, so a partner slows down or upgrades
    before being refused. That is the same reasoning `ratelimit.Decision` is built on.

    The message is German first and English second, like every other refusal this API produces, and
    it states four things: what the plan includes, what has been used, what this request asked for,
    and when the period rolls. A `429` whose body is "quota exceeded" costs a support call.
    """
    if decision.allowed:
        return decision

    entitlement = decision.entitlement
    days = max(1, decision.reset_after // 86_400)

    raise QuotaExceeded(
        f"Das Kontingent dieses Abrechnungszeitraums ist erschöpft: {decision.used} von "
        f"{entitlement.monthly_invoice_quota} Rechnungen im Tarif {entitlement.plan_label} "
        f"verbraucht, angefragt wurden {decision.requested} weitere. Der Zeitraum endet in "
        f"{days} Tag(en). {_next_tier_hint(entitlement.subscription_tier)} — "
        f"POST /api/v1/billing/upgrade. — The billing period's invoice quota is exhausted "
        f"({decision.used}/{entitlement.monthly_invoice_quota} on plan "
        f"{entitlement.plan_code}); {decision.requested} more were requested.",
        quota=entitlement.monthly_invoice_quota,
        used=decision.used,
        requested=decision.requested,
        plan_code=entitlement.plan_code,
        subscription_tier=entitlement.subscription_tier.value,
        retry_after=decision.reset_after,
        details={
            "period_end": entitlement.period_end.isoformat(),
            "allow_overage": entitlement.allow_overage,
        },
    )


async def check_and_refuse(organization_id: str, *, requested: int) -> QuotaDecision:
    """Ask whether this practice may audit `requested` more, and refuse if not.

    The one entry point every audit path uses, so the decision and the refusal cannot drift apart
    between four call sites. The store is fetched through `app.api.deps` rather than constructed
    here, so a test that swaps the database swaps it for everything at once.
    """
    from app.api.deps import billing

    return refuse_if_over(await billing().check(organization_id, requested=requested))


async def single_audit_quota(key: RequestApiKey) -> QuotaDecision:
    """The dependency on `POST /api/v1/audit/single`: one invoice, refused before the body is read.

    Declared as a dependency rather than called in the handler because the count is a constant and
    the tenant comes out of the verified key, so nothing about the body is needed to decide. FastAPI
    resolves dependencies before it reads the request body, which means a practice over its quota is
    refused without a 5 MB upload crossing the wire.

    It shares the request's single `require_api_key` resolution — FastAPI caches a dependency per
    request — so this does not cost a second key verification.
    """
    return await check_and_refuse(key.organization_id, requested=1)


#: What `POST /api/v1/audit/single` annotates with. Returns a `QuotaDecision` rather than `None` so
#: the route can put the headers on its own response, exactly like `SingleRateLimit`.
SingleAuditQuota = Annotated[QuotaDecision, Depends(single_audit_quota)]


async def optional_quota(request: Request, *, requested: int) -> QuotaDecision | None:
    """The quota for a caller who *may* have named a practice. `None` when they did not.

    For `/padnext/audit` and `/padnext/batch`'s web-tier siblings, where the tenant is read off the
    header rather than proven by a credential. See the module docstring on why that endpoint reads
    the header optionally and what the consequence is.
    """
    organization_id = optional_organization(request)
    if not organization_id:
        return None
    return await check_and_refuse(organization_id, requested=requested)


def apply(response, decision: QuotaDecision | None) -> None:
    """Put `X-Quota-*` on a successful response, if there was a decision to report.

    A no-op when the caller named no practice, deliberately: headers describing a quota nothing was
    counted against would be worse than no headers. Mirrors `app.api.audit._apply`, which does the
    same for the rate limiter and for the same reason.
    """
    if decision is None:
        return
    for name, value in decision.headers().items():
        response.headers[name] = value


__all__ = [
    "SingleAuditQuota",
    "apply",
    "check_and_refuse",
    "optional_quota",
    "refuse_if_over",
    "single_audit_quota",
]
