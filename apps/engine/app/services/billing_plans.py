"""The price list, as an append-only catalog of plans nobody may edit in place.

This module is the *entitlement* half of billing and nothing else: it says what a plan includes,
never what anybody was charged. `app.services.billing` holds the second half — which practice is on
which plan, what they have consumed, and what that adds up to.

## Why the numbers live in code and not in a table

A plan is read on the hot path — every audit asks "is this practice within its quota" — and it
changes a handful of times a year. A table would put a second query in front of every audit to hold
data that is deployed with the service anyway, and it would make the price list something an
operator can change with an `UPDATE`, which is exactly what the append-only rule below exists to
prevent. What *is* in the database is the assignment (`organization_billing`) and the snapshot taken
at the moment of assignment — see `app.db.models.OrganizationBillingRecord`.

## The three rules this catalog is built on

**1. A plan is never modified once it has been assigned; a new one is added instead.** `PLANS` is
keyed by a `plan_code` carrying its own revision — `pilot-2026.08`, `starter-2026.08` — and a change
to a price means a new code, `starter-2026.11`. Practices on the old code stay on it until somebody
deliberately moves them. Editing `starter-2026.08`'s `monthly_invoice_quota` instead would silently
rewrite what every existing customer agreed to, including on invoices already issued.

**2. What was agreed is snapshotted onto the assignment.** `organization_billing` copies
`monthly_invoice_quota`, `overage_rate_cents` and `allow_overage` at the moment a plan is assigned.
So even a mistake — someone edits a plan in place despite rule 1, or a code disappears from a
deployment — cannot change what an existing practice is entitled to. The catalog is where a *new*
assignment gets its numbers, not where an existing one reads them.

**3. Entitlement is asked as a question about a limit, never about a plan name.** Nothing outside
this module branches on `tier == PRO`. The quota check asks for a number and gets one, which is what
makes adding a tier a data change rather than a search through the codebase for comparisons. The
reasoning is Arnon Shimoni's and it is worth reading in full — `data/arnon.dk/data/markdown/
why-you-should-separate-your-billing-from-entitlement.md`, and the SKU-versioning argument behind
rule 1 in `design-your-pricing-and-tools-so-you-can-adapt-it-later.md`.

## ⚠ The euro amounts here are placeholders. The quotas are not.

**The invoice quotas come from `docs/MONETIZATION.md` §3, Model A**, which is this repository's own
worked proposal for how the engine is sold: Starter at 1,000 invoices, Professional at 10,000,
Enterprise at 100,000. Those figures were argued for there and are reproduced here rather than
re-invented, so the price list and the document that justifies it cannot drift.

**Every euro amount is a placeholder.** `MONETIZATION.md` leaves the rates deliberately blank and
says why: *"I have no German market benchmarks for GOÄ audit tooling, and inventing figures in a
document that will be quoted back is exactly the failure `engine-facts.ts` exists to prevent."* The
same applies to code, with the difference that code cannot leave a number blank — a plan needs *a*
`base_fee_cents` to be a plan at all. So the figures below are round, obviously-provisional numbers
whose only job is to let the machinery be built, tested and demonstrated end to end. **Setting the
real ones is a business decision, and this file is where it is made.**

The `data/arnon.dk/` corpus is not a source for them either: it is 61 articles of general
SaaS-billing writing — entitlements, usage metering, pricing architecture — and contains no quotas,
tiers or rates for this product, because it is somebody else's blog. What it *did* supply is the
three rules above, and they are cited where they apply.

What is *not* a placeholder is the shape: cents as integers (never a float and never a decimal
string — see `5-things-i-learned-developing-billing-system.md` on why money is counted in its
smallest subdivision), a monthly quota in whole invoices, and an overage rate per invoice above it.

## The pilot plan, and why every practice starts on it

`DEFAULT_PLAN_CODE` is `pilot-2026.08`: no fee, a generous quota, and overage allowed. A pilot
practice is therefore never refused an audit because of billing, which is the correct behaviour for
a product being evaluated — and the usage is metered anyway, in full, from the first request.

That last part is the whole point and it is the one thing a free pilot usually gets wrong: the
conversation that converts a pilot is "you audited 3,140 invoices last quarter", and it cannot be
had retroactively if nothing was counted. `pricing-ai-proofs-of-concept-free-pilots-will-kill-you.md`
in the same corpus is about precisely this failure. So the plan is free and the meter runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SubscriptionTier(StrEnum):
    """The four tiers, in ascending order of entitlement.

    A tier is a **label**, not a limit. It is what a settings screen prints and what a sales
    conversation names; every decision the engine makes is made from the numbers on `Plan`. Two
    plans may share a tier (`starter-2026.08` and a later `starter-2026.11`) and differ in price,
    which is exactly what rule 1 in the module docstring is for.

    Ordered by `ORDER` below rather than by the enum's own member order, because `StrEnum` compares
    as a string and `"enterprise" < "free"` is alphabetically true and commercially nonsense.
    """

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


#: Rank per tier, for the one comparison that is legitimate: is this an upgrade or a downgrade.
#: Nothing else in the codebase may order tiers, and nothing may branch on a specific one.
ORDER: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 0,
    SubscriptionTier.STARTER: 1,
    SubscriptionTier.PRO: 2,
    SubscriptionTier.ENTERPRISE: 3,
}


@dataclass(frozen=True)
class Plan:
    """One plan, at one revision. Frozen: rule 1 is enforced by the type, not by a convention.

    `frozen=True` means a plan cannot be mutated at runtime even by accident — an attempt raises
    rather than quietly changing what the next practice to sign up is entitled to. Adding a plan is
    an entry in `PLANS`; changing one is a new entry with a new code.
    """

    #: The SKU. `<tier>-<year>.<month>` — the revision is in the code, so `alembic`-style ordering
    #: falls out of a sort and a support conversation can name a price exactly.
    code: str

    tier: SubscriptionTier

    #: What a reader is shown. German, because every user-facing string in this product is.
    label: str

    #: The recurring fee for one billing period, in euro cents. `0` for a free plan.
    base_fee_cents: int

    #: How many invoices the base fee includes per period. `0` would mean "the fee buys nothing",
    #: which no plan here does; a plan with no ceiling sets `allow_overage` and a rate instead.
    monthly_invoice_quota: int

    #: What each invoice above the quota costs, in euro cents. Meaningless unless `allow_overage`.
    overage_rate_cents: int

    #: Whether an audit above the quota is allowed (and charged) or refused with `429`.
    #:
    #: The distinction that matters to a practice on deadline: a hard stop on the 28th of the month
    #: is an outage, and an overage charge is an invoice line. Which of the two is correct is a
    #: commercial decision per plan, which is why it is a field and not a global setting.
    allow_overage: bool

    #: Whether this plan may be selected by a new or upgrading practice. A superseded revision stays
    #: in `PLANS` — the practices on it read their snapshot, and an old invoice still names it — but
    #: cannot be assigned again. This is the "archived price" of rule 1.
    selectable: bool = True

    @property
    def is_metered_only(self) -> bool:
        """True when this plan charges nothing at all. The pilot, and the free tier."""
        return self.base_fee_cents == 0 and (
            not self.allow_overage or self.overage_rate_cents == 0
        )


#: Every plan this deployment knows, by code. **Append only** — see rule 1.
#:
#: ⚠ The amounts are placeholders. See the module docstring.
PLANS: dict[str, Plan] = {
    "pilot-2026.08": Plan(
        code="pilot-2026.08",
        tier=SubscriptionTier.FREE,
        label="Pilotphase",
        base_fee_cents=0,
        # High enough that no pilot practice meets it by accident, low enough that a runaway
        # integration is still visible as a number somebody can look at rather than as unbounded
        # consumption. The rate limiter is what protects the service; this protects the invoice.
        monthly_invoice_quota=10_000,
        overage_rate_cents=0,
        allow_overage=True,
    ),
    "free-2026.08": Plan(
        code="free-2026.08",
        tier=SubscriptionTier.FREE,
        label="Kostenlos",
        base_fee_cents=0,
        monthly_invoice_quota=50,
        overage_rate_cents=0,
        # A free plan that silently ran up charges would be the worst possible surprise, so this is
        # the one plan where the ceiling is hard. `429 QUOTA_EXCEEDED` names the upgrade.
        allow_overage=False,
    ),
    # The three tiers of `MONETIZATION.md` §3 Model A. The quotas are that document's; the euro
    # amounts are placeholders — see the module docstring on which is which and why.
    "starter-2026.08": Plan(
        code="starter-2026.08",
        tier=SubscriptionTier.STARTER,
        label="Starter",
        base_fee_cents=9_900,
        monthly_invoice_quota=1_000,
        overage_rate_cents=25,
        allow_overage=True,
    ),
    "pro-2026.08": Plan(
        code="pro-2026.08",
        tier=SubscriptionTier.PRO,
        # "Professional" in `MONETIZATION.md`; the tier value stays `pro` because that is what the
        # enum, the column and every client switch on. A label is prose and an enum member is a
        # contract, so only one of the two can be the longer word.
        label="Professional",
        base_fee_cents=29_900,
        monthly_invoice_quota=10_000,
        overage_rate_cents=15,
        allow_overage=True,
    ),
    "enterprise-2026.08": Plan(
        code="enterprise-2026.08",
        tier=SubscriptionTier.ENTERPRISE,
        label="Enterprise",
        # `MONETIZATION.md` says "negotiated" and "100,000+" for this tier, which a quota column
        # cannot express. 100,000 is the floor it names; a bespoke agreement gets its own plan code
        # rather than an edit to this one — that is what the append-only rule is for.
        base_fee_cents=99_900,
        monthly_invoice_quota=100_000,
        overage_rate_cents=8,
        allow_overage=True,
    ),
}


#: What a practice with no billing row gets. The pilot, deliberately: an organisation that appears
#: for the first time mid-pilot must be able to audit immediately, and a default that refused would
#: turn "we onboarded a new practice" into an outage.
DEFAULT_PLAN_CODE = "pilot-2026.08"


def plan(code: str) -> Plan | None:
    """The plan with this code, or `None` if this deployment does not know it.

    `None` rather than a raise, because the caller that matters is reading a *stored* code off an
    `organization_billing` row written by a possibly-newer deployment. That is a rollback, not a
    bug, and the row's own snapshot is what the quota check uses — so the honest answer is "I cannot
    describe this plan" and not an exception in front of an audit.
    """
    return PLANS.get(code)


def default_plan() -> Plan:
    """The pilot plan. Raises if it is missing, because that is a broken build and not a state."""
    found = PLANS.get(DEFAULT_PLAN_CODE)
    if found is None:  # pragma: no cover - unreachable unless DEFAULT_PLAN_CODE is edited wrongly
        raise RuntimeError(
            f"DEFAULT_PLAN_CODE names {DEFAULT_PLAN_CODE!r}, which is not in PLANS. Every "
            "organisation without a billing row is assigned this plan, so there is no safe "
            "fallback: fix the catalog."
        )
    return found


def selectable_plans() -> list[Plan]:
    """The plans a practice may move to, cheapest first.

    Sorted by tier rank and then by fee, so the list reads as a ladder. `pilot-*` is included when
    it is selectable — a deployment running a pilot wants to be able to put a practice back on it —
    and a superseded revision is not.
    """
    return sorted(
        (found for found in PLANS.values() if found.selectable),
        key=lambda found: (ORDER[found.tier], found.base_fee_cents),
    )


def plan_for_tier(tier: SubscriptionTier) -> Plan | None:
    """The current selectable plan for one tier — what "upgrade me to Pro" resolves to.

    The *newest* selectable revision of that tier, by code, so a caller naming a tier gets today's
    price rather than whichever revision happens to sort first. A caller who needs a specific
    historical price names the `plan_code` instead; that is what the field is for.
    """
    candidates = [
        found for found in PLANS.values() if found.tier is tier and found.selectable
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda found: found.code)


__all__ = [
    "DEFAULT_PLAN_CODE",
    "ORDER",
    "PLANS",
    "Plan",
    "SubscriptionTier",
    "default_plan",
    "plan",
    "plan_for_tier",
    "selectable_plans",
]
