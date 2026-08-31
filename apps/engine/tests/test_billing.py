"""Quotas, plans and priced periods — the machinery that lets this API be sold.

What this file protects is a small number of properties that are cheap to break and expensive to
discover in production:

* **the billable unit is invoices, not requests.** One bulk upload of three deliveries is one API
  call and three invoices, and a change that quietly went back to counting calls would under-bill
  every archive customer by two orders of magnitude while every test about status codes still passed.
* **a quota that says "no" actually says no**, on both audit paths, with a code a client can tell
  apart from a rate limit.
* **a plan a practice is already on cannot be changed under them.** The numbers are snapshotted onto
  their row, so an edit to the catalog — which the append-only rule forbids but cannot prevent —
  leaves an existing entitlement alone.
* **a period is closed exactly once.** Double-charging a customer is the failure that matters here,
  and the property is enforced by a unique index rather than by a check somebody could remove.
* **the screen and the refusal agree.** `GET /billing/usage` and the `429` at the ceiling are the
  same `SUM`, so a practice cannot be told "47 of 50" and then refused at 48.

**The overage rate on the seeded plans is deliberately not asserted against a euro figure.** Those
numbers are placeholders and the module that holds them says so at length; a test that pinned
`starter` at 99,00 € would fail the day somebody sets the real price, which is the opposite of
useful. What is asserted is the *arithmetic* — that `overage_invoices * rate` is what lands on the
invoice — with plans this file builds itself.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from app.api.apikeys import API_KEY_HEADER
from app.api.tenancy import ORGANIZATION_ID_HEADER
from app.config import PADNEXT_EXAMPLES_DIR
from app.db.models import BillingInvoiceRecord, OrganizationBillingRecord
from app.services.billing import BillingStore, _add_one_month, calendar_period, is_upgrade
from app.services.billing_plans import (
    DEFAULT_PLAN_CODE,
    PLANS,
    Plan,
    SubscriptionTier,
    default_plan,
    plan_for_tier,
    selectable_plans,
)

from tests.conftest import TEST_ORGANIZATION_ID

NINE_ERROR_XML = PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml"

OTHER_ORGANIZATION_ID = "orgZq4Wm7Bn2Cx9Dv6Fk1Ht3Js5Lp8R"


@pytest.fixture
def delivery() -> bytes:
    return NINE_ERROR_XML.read_bytes()


def mint(client, *, organization_id: str = TEST_ORGANIZATION_ID) -> str:
    response = client.post(
        "/api/v1/settings/api-keys",
        json={"name": "Kontingent-Test"},
        headers={ORGANIZATION_ID_HEADER: organization_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def auth(token: str) -> dict[str, str]:
    return {API_KEY_HEADER: token}


def zip_of(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture
def unscoped_client():
    """A client that sends no organisation header at all.

    Built here rather than by clearing a header on the shared `client`, for the reason
    `test_tenancy.py`'s copy gives: "the fixture sets it and this test unsets it" is a thing that
    silently stops working when the fixture changes.
    """
    from fastapi.testclient import TestClient

    from app.api import deps
    from app.main import app

    deps.reset()
    with TestClient(app) as test_client:
        yield test_client
    deps.reset()


def tight_plan(quota: int, *, allow_overage: bool, rate: int = 0) -> Plan:
    """A plan built for one assertion, with numbers this file chose.

    Not one of the seeded plans, deliberately. Those carry placeholder pricing that a business
    decision will replace, and a test that depended on their figures would fail on the day the real
    prices are set — which would make the suite an obstacle to the change rather than a check on it.
    """
    return Plan(
        code=f"test-quota-{quota}-{'over' if allow_overage else 'hard'}",
        tier=SubscriptionTier.STARTER,
        label="Testtarif",
        base_fee_cents=1_000,
        monthly_invoice_quota=quota,
        overage_rate_cents=rate,
        allow_overage=allow_overage,
    )


async def put_on(store: BillingStore, organization_id: str, found: Plan) -> None:
    await store.assign_plan(organization_id, found, actor="tests")


def move_to(client, monkeypatch, found: Plan) -> None:
    """Register a test plan in the catalog and move the practice onto it, over HTTP.

    Through `POST /api/v1/billing/upgrade` rather than by reaching into the store, so the plan a
    quota test is refused against is one that arrived the way a customer's would. The catalog entry
    is `monkeypatch`ed, so it disappears with the test and cannot leak into the seeded price list —
    which is also why these plans carry numbers this file chose rather than the placeholders in
    `billing_plans`.
    """
    monkeypatch.setitem(PLANS, found.code, found)
    moved = client.post("/api/v1/billing/upgrade", json={"plan_code": found.code})
    assert moved.status_code == 200, moved.text
    assert moved.json()["subscription"]["monthly_invoice_quota"] == found.monthly_invoice_quota


# ==========================================================================================
# 1. the catalog, and the rules it is built on
# ==========================================================================================


def test_the_default_plan_exists_and_is_free():
    """Every practice starts here, so a broken default is an outage on somebody's first audit."""
    found = default_plan()
    assert found.code == DEFAULT_PLAN_CODE
    assert found.base_fee_cents == 0
    # The pilot must not be able to refuse an audit: a practice evaluating the product being told
    # "quota exceeded" is the one outcome the pilot plan exists to prevent.
    assert found.allow_overage is True


def test_every_plan_code_carries_its_tier_and_a_revision():
    """The SKU convention, asserted rather than trusted.

    `<tier>-<year>.<month>` is what makes "move everyone off starter-2026.08" a query and what lets a
    support conversation name a price exactly. A code that stopped following it would not break
    anything today and would make the price list unreadable in a year.
    """
    for code, found in PLANS.items():
        assert code == found.code, f"{code!r} is keyed under a different code than it carries"
        tier, _, revision = code.partition("-")
        assert revision, f"{code!r} has no revision suffix"
        # `pilot` is the one code whose prefix is not a tier — it is a free-tier plan with its own
        # name, because "the pilot" is what people call it and `free-2026.08` is a different plan
        # with a different quota.
        assert tier in {member.value for member in SubscriptionTier} | {"pilot"}, code


def test_the_free_tier_is_the_one_plan_that_refuses_rather_than_charging():
    """A free plan that silently ran up charges is the worst possible surprise."""
    free = PLANS["free-2026.08"]
    assert free.allow_overage is False
    assert free.overage_rate_cents == 0

    for found in PLANS.values():
        if found.base_fee_cents > 0:
            # A paid plan being hard-stopped mid-month is an outage the customer paid to avoid.
            assert found.allow_overage is True, found.code


def test_plans_are_offered_cheapest_first_and_supersession_is_respected():
    ladder = selectable_plans()
    assert ladder, "no plan is selectable, so nobody could ever upgrade"
    fees = [found.base_fee_cents for found in ladder]
    assert fees == sorted(fees), "the ladder is not ordered by price"

    assert all(found.selectable for found in ladder)


def test_a_tier_resolves_to_todays_revision_of_it():
    for member in SubscriptionTier:
        found = plan_for_tier(member)
        if found is None:
            continue
        assert found.tier is member
        assert found.selectable


def test_tier_order_is_commercial_and_not_alphabetical():
    """`"enterprise" < "free"` is alphabetically true and commercially nonsense."""
    assert is_upgrade(SubscriptionTier.FREE, SubscriptionTier.ENTERPRISE)
    assert not is_upgrade(SubscriptionTier.ENTERPRISE, SubscriptionTier.FREE)
    assert not is_upgrade(SubscriptionTier.PRO, SubscriptionTier.PRO)


# ==========================================================================================
# 2. period arithmetic
# ==========================================================================================


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        ("2026-01-31", "2026-02-28"),
        ("2028-01-31", "2028-02-29"),
        ("2026-01-15", "2026-02-15"),
        ("2026-12-31", "2027-01-31"),
        ("2026-08-31", "2026-09-30"),
    ],
)
def test_a_period_is_one_calendar_month_with_the_day_clamped(start, expected):
    """31 January + 1 month is 28 February, not 3 March.

    The wrong answer is not merely surprising: a period that started on the 31st and overflowed into
    March would make the *following* period start on the 3rd, and the practice's billing day would
    walk forward a few days every year.
    """
    moment = datetime.fromisoformat(f"{start}T09:30:00+00:00")
    assert _add_one_month(moment).date().isoformat() == expected
    # The time of day is part of the anchor and must not drift.
    assert _add_one_month(moment).timetz() == moment.timetz()


def test_the_calendar_month_helper_is_half_open_and_starts_at_midnight():
    start, end = calendar_period(datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc))
    assert start == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 9, 1, tzinfo=timezone.utc)


# ==========================================================================================
# 3. the entitlement
# ==========================================================================================


async def test_a_practice_with_no_row_is_put_on_the_pilot_plan(database):
    """The first audit must not fail because nobody set up billing."""
    store = BillingStore(database)
    entitlement = await store.entitlement(TEST_ORGANIZATION_ID)

    assert entitlement.plan_code == DEFAULT_PLAN_CODE
    assert entitlement.subscription_tier is SubscriptionTier.FREE
    assert entitlement.period_end > entitlement.period_start
    # And it was persisted, not merely returned: a quota check against an imaginary entitlement
    # would have nothing to snapshot and nothing for an invoice to name.
    again = await store.entitlement(TEST_ORGANIZATION_ID)
    assert again.period_start == entitlement.period_start


async def test_two_practices_get_separate_entitlements(database):
    store = BillingStore(database)
    await put_on(store, TEST_ORGANIZATION_ID, tight_plan(5, allow_overage=False))

    mine = await store.entitlement(TEST_ORGANIZATION_ID)
    theirs = await store.entitlement(OTHER_ORGANIZATION_ID)

    assert mine.monthly_invoice_quota == 5
    assert theirs.plan_code == DEFAULT_PLAN_CODE


async def test_the_plans_numbers_are_snapshotted_so_a_catalog_edit_cannot_reach_an_existing_practice(
    database, monkeypatch
):
    """Rule 2 of `billing_plans`, and the reason the duplication is not redundancy.

    The append-only rule says a plan is never edited in place. A rule is a convention; this is the
    guarantee behind it. A practice's quota is what was agreed when they were put on the plan, and
    an edit to the catalog — by mistake, by a rollback, by a plan disappearing — must not change it.
    """
    store = BillingStore(database)
    original = tight_plan(500, allow_overage=True, rate=25)
    monkeypatch.setitem(PLANS, original.code, original)
    await put_on(store, TEST_ORGANIZATION_ID, original)

    # Somebody edits the plan in place despite the rule.
    monkeypatch.setitem(
        PLANS, original.code, tight_plan(500, allow_overage=False, rate=9_999)
    )

    entitlement = await store.entitlement(TEST_ORGANIZATION_ID)
    assert entitlement.overage_rate_cents == 25, "the row's snapshot was not used"
    assert entitlement.allow_overage is True


async def test_a_plan_code_this_deployment_does_not_know_still_yields_an_entitlement(database):
    """A rollback is a state, not a bug.

    A row may name a plan from a newer deployment. The quota comes from the row, so the practice
    keeps working; only the human-readable label falls back.
    """
    store = BillingStore(database)
    async with database.session() as session:
        session.add(
            OrganizationBillingRecord(
                organization_id=TEST_ORGANIZATION_ID,
                subscription_tier="pro",
                plan_code="pro-2099.01",
                monthly_invoice_quota=42,
                overage_rate_cents=7,
                allow_overage=True,
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
            )
        )

    entitlement = await store.entitlement(TEST_ORGANIZATION_ID)
    assert entitlement.monthly_invoice_quota == 42
    assert entitlement.plan_label == "pro", "an unknown plan should fall back to its tier"


# ==========================================================================================
# 4. the quota decision
# ==========================================================================================


async def test_within_the_quota_nothing_is_owed_beyond_the_base_fee(database):
    store = BillingStore(database)
    await put_on(store, TEST_ORGANIZATION_ID, tight_plan(10, allow_overage=True, rate=25))

    decision = await store.check(TEST_ORGANIZATION_ID, requested=3)
    assert decision.allowed
    assert decision.overage_invoices == 0
    assert decision.overage_cents == 0
    assert decision.remaining == 10


async def test_over_the_quota_with_overage_allowed_is_charged_not_refused(database):
    """The distinction a paying customer cares about: an invoice line, not an outage."""
    store = BillingStore(database)
    await put_on(store, TEST_ORGANIZATION_ID, tight_plan(2, allow_overage=True, rate=25))

    decision = await store.check(TEST_ORGANIZATION_ID, requested=5)
    assert decision.allowed
    assert decision.overage_invoices == 3
    assert decision.overage_cents == 75


async def test_over_the_quota_without_overage_is_refused(database):
    store = BillingStore(database)
    await put_on(store, TEST_ORGANIZATION_ID, tight_plan(2, allow_overage=False))

    assert (await store.check(TEST_ORGANIZATION_ID, requested=2)).allowed
    assert not (await store.check(TEST_ORGANIZATION_ID, requested=3)).allowed


async def test_the_reset_is_the_end_of_the_period_and_never_zero(database):
    """A `Retry-After: 0` invites an immediate retry that would be refused again."""
    store = BillingStore(database)
    decision = await store.check(TEST_ORGANIZATION_ID, requested=1)
    assert decision.reset_after >= 1
    # A monthly period, so the honest answer is days rather than seconds. Asserted loosely: the
    # point is that it is not a rate limiter's number.
    assert decision.reset_after > 3600


# ==========================================================================================
# 5. the billable unit, over HTTP
# ==========================================================================================


def test_one_single_audit_counts_one_invoice(client, delivery):
    token = mint(client)
    assert client.post(
        "/api/v1/audit/single", content=delivery, headers=auth(token)
    ).status_code == 200

    usage = client.get("/api/v1/billing/usage", headers=auth(token))
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["invoices_processed"] == 1
    assert body["requests"] >= 1


def test_a_bulk_upload_of_three_counts_three_invoices_and_one_request(client, delivery):
    """The property this whole column exists for.

    A price per *request* would charge this the same as a single audit — the same work, priced two
    orders of magnitude apart depending on how the partner chose to batch it. `requests` is reported
    beside it for context, which is what makes the two numbers legible next to each other.
    """
    token = mint(client)
    archive = zip_of({f"d{index}_padx.xml": delivery for index in range(3)})

    accepted = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("three.zip", archive, "application/zip")},
        headers=auth(token),
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["file_count"] == 3

    body = client.get("/api/v1/billing/usage", headers=auth(token)).json()
    assert body["invoices_processed"] == 3


def test_a_web_tier_audit_is_counted_against_the_practice_that_proxied_it(client, delivery):
    """`/padnext/audit` names no tenant of its own, but the web tier's call does."""
    assert client.post(
        "/api/v1/padnext/audit",
        content=delivery,
        headers={"content-type": "application/xml"},
    ).status_code == 200

    body = client.get("/api/v1/billing/usage").json()
    assert body["invoices_processed"] == 1


def test_an_audit_with_no_practice_named_is_not_counted_against_anybody(
    unscoped_client, delivery
):
    """`/demo`'s visitor. There is nobody to attribute it to, so nothing is written."""
    answered = unscoped_client.post(
        "/api/v1/padnext/audit",
        content=delivery,
        headers={"content-type": "application/xml"},
    )
    assert answered.status_code == 200, answered.text
    # And the endpoint still answers without a tenant, which is the frozen half of its contract.


def test_a_refused_audit_is_not_counted(client):
    """A body that is not PADnext caused no audit, so it is not a billable invoice.

    `422 PADNEXT_UNREADABLE` rather than a `400`: the bytes arrived, they are simply not a delivery
    this reader handles. Either way the practice did not get an audit and is not charged for one —
    which is why `record_invoices` is called *after* the audit rather than beside the quota check.
    """
    refused = client.post(
        "/api/v1/padnext/audit",
        content=b'{"not": "padnext"}',
        headers={"content-type": "application/xml"},
    )
    assert refused.status_code == 422
    assert refused.json()["error_code"] == "PADNEXT_UNREADABLE"

    assert client.get("/api/v1/billing/usage").json()["invoices_processed"] == 0


def test_a_status_poll_is_a_request_and_not_an_invoice(client, delivery):
    token = mint(client)
    archive = zip_of({"one_padx.xml": delivery})
    batch = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("one.zip", archive, "application/zip")},
        headers=auth(token),
    ).json()

    for _ in range(3):
        client.get(f"/api/v1/audit/bulk/{batch['batch_id']}", headers=auth(token))

    body = client.get("/api/v1/billing/usage", headers=auth(token)).json()
    assert body["invoices_processed"] == 1, "a poll was counted as an audit"
    assert body["requests"] >= 4


# ==========================================================================================
# 6. the refusal, over HTTP
# ==========================================================================================


def test_the_partner_audit_is_refused_with_quota_exceeded_once_the_ceiling_is_reached(
    client, delivery, monkeypatch
):
    """Mint → audit to the ceiling → refused, with a code a client can act on."""
    token = mint(client)
    move_to(client, monkeypatch, tight_plan(1, allow_overage=False))

    first = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    assert first.status_code == 200, first.text

    refused = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    assert refused.status_code == 429, refused.text
    body = refused.json()
    assert body["error_code"] == "QUOTA_EXCEEDED"
    # Not the rate limiter's code. A client that could not tell them apart would back off for weeks.
    assert body["error_code"] != "RATE_LIMIT_EXCEEDED"
    assert body["details"]["quota"] == 1
    assert body["details"]["used"] >= 1
    assert refused.headers["Retry-After"] == str(body["retry_after"])
    # And the message names the way out, in German. A `429` whose body is "quota exceeded" costs a
    # support call.
    assert "billing/upgrade" in body["message"]
    assert "Kontingent" in body["message"]


def test_a_bulk_archive_is_refused_as_a_unit_rather_than_part_way_through(
    client, delivery, monkeypatch
):
    """A job that audited 180 of 300 files is a job somebody reconciles by hand."""
    token = mint(client)
    move_to(client, monkeypatch, tight_plan(2, allow_overage=False))

    archive = zip_of({f"d{index}_padx.xml": delivery for index in range(5)})
    refused = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("five.zip", archive, "application/zip")},
        headers=auth(token),
    )
    assert refused.status_code == 429, refused.text
    assert refused.json()["error_code"] == "QUOTA_EXCEEDED"
    assert refused.json()["details"]["requested"] == 5

    # And no job was created, so there is no orphaned archive and nothing to reconcile.
    listing = client.get("/api/v1/audit/bulk", headers=auth(token)).json()
    assert all(job["file_count"] != 5 for job in listing["jobs"])


def test_the_web_tier_audit_is_refused_by_the_same_ceiling(client, delivery, monkeypatch):
    """Both doors, one quota. A practice cannot get past the ceiling by switching endpoints."""
    move_to(client, monkeypatch, tight_plan(1, allow_overage=False))

    headers = {"content-type": "application/xml"}
    assert (
        client.post("/api/v1/padnext/audit", content=delivery, headers=headers).status_code == 200
    )
    refused = client.post("/api/v1/padnext/audit", content=delivery, headers=headers)
    assert refused.status_code == 429, refused.text
    assert refused.json()["error_code"] == "QUOTA_EXCEEDED"


def test_a_plan_with_overage_is_charged_rather_than_refused(client, delivery, monkeypatch):
    """The paying customer's path: an invoice line, not an outage on the 28th."""
    token = mint(client)
    move_to(client, monkeypatch, tight_plan(1, allow_overage=True, rate=25))

    for _ in range(3):
        answered = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
        assert answered.status_code == 200, answered.text

    body = client.get("/api/v1/billing/usage", headers=auth(token)).json()
    assert body["invoices_processed"] == 3
    assert body["overage_invoices"] == 2
    assert body["overage_cents"] == 50
    assert body["projected_total_cents"] == body["base_fee_cents"] + 50


def test_the_quota_headers_are_published_on_a_successful_audit_too(client, delivery):
    """So a partner slows down or upgrades *before* being refused."""
    token = mint(client)
    answered = client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    assert answered.status_code == 200
    assert "X-Quota-Limit" in answered.headers
    assert "X-Quota-Remaining" in answered.headers
    assert "X-Quota-Reset" in answered.headers


def test_the_screen_and_the_refusal_are_computed_from_the_same_number(
    client, delivery, monkeypatch
):
    """A practice must never be told "1 of 2 used" and then refused at 2."""
    token = mint(client)
    move_to(client, monkeypatch, tight_plan(2, allow_overage=False))

    client.post("/api/v1/audit/single", content=delivery, headers=auth(token))
    body = client.get("/api/v1/billing/usage", headers=auth(token)).json()

    used = body["invoices_processed"]
    remaining = body["remaining"]
    assert used + remaining == body["subscription"]["monthly_invoice_quota"]

    # Audit exactly `remaining` more; the next one must be the refusal.
    for _ in range(remaining):
        assert (
            client.post(
                "/api/v1/audit/single", content=delivery, headers=auth(token)
            ).status_code
            == 200
        )
    assert (
        client.post("/api/v1/audit/single", content=delivery, headers=auth(token)).status_code
        == 429
    )


# ==========================================================================================
# 7. the endpoints
# ==========================================================================================


def test_usage_is_readable_with_a_key_and_with_a_session(client, delivery):
    token = mint(client)
    client.post("/api/v1/audit/single", content=delivery, headers=auth(token))

    by_key = client.get("/api/v1/billing/usage", headers=auth(token))
    by_session = client.get("/api/v1/billing/usage")

    assert by_key.status_code == 200
    assert by_session.status_code == 200
    assert (
        by_key.json()["invoices_processed"] == by_session.json()["invoices_processed"]
    )


def test_usage_reads_the_calling_practice_and_there_is_no_parameter_that_names_one(
    client, delivery
):
    token = mint(client)
    client.post("/api/v1/audit/single", content=delivery, headers=auth(token))

    theirs = client.get(
        "/api/v1/billing/usage", headers={ORGANIZATION_ID_HEADER: OTHER_ORGANIZATION_ID}
    )
    assert theirs.status_code == 200
    assert theirs.json()["invoices_processed"] == 0, "one practice read another's consumption"
    assert theirs.json()["subscription"]["organization_id"] == OTHER_ORGANIZATION_ID


def test_a_wrong_key_is_a_401_and_never_a_fall_through_to_the_header(client):
    refused = client.get(
        "/api/v1/billing/usage",
        headers={API_KEY_HEADER: "azm_live_" + "0" * 12 + "_" + "0" * 48},
    )
    assert refused.status_code == 401
    assert refused.json()["error_code"] == "API_KEY_INVALID"


def test_the_plan_catalog_lists_the_selectable_plans(client):
    listed = client.get("/api/v1/billing/plans")
    assert listed.status_code == 200, listed.text
    codes = [entry["code"] for entry in listed.json()["plans"]]
    assert codes == [found.code for found in selectable_plans()]
    # Every amount is an integer count of cents. A float here would be a contract bug.
    for entry in listed.json()["plans"]:
        assert isinstance(entry["base_fee_cents"], int)
        assert isinstance(entry["overage_rate_cents"], int)


def test_an_upgrade_changes_the_plan_and_reports_what_it_was(client):
    upgraded = client.post("/api/v1/billing/upgrade", json={"tier": "pro"})
    assert upgraded.status_code == 200, upgraded.text
    body = upgraded.json()

    assert body["changed"] is True
    assert body["previous_plan_code"] == DEFAULT_PLAN_CODE
    assert body["subscription"]["subscription_tier"] == "pro"
    assert body["subscription"]["monthly_invoice_quota"] == PLANS[
        "pro-2026.08"
    ].monthly_invoice_quota


def test_upgrading_to_the_current_plan_is_a_successful_no_op(client):
    client.post("/api/v1/billing/upgrade", json={"tier": "pro"})
    again = client.post("/api/v1/billing/upgrade", json={"tier": "pro"})

    assert again.status_code == 200
    assert again.json()["changed"] is False


def test_an_upgrade_does_not_restart_the_billing_period(client, delivery):
    """480 of 500 used and moving to Pro leaves 2,020 — not a fresh quota and a mid-month boundary."""
    before = client.get("/api/v1/billing/usage").json()["subscription"]
    client.post("/api/v1/audit/single", content=delivery, headers=auth(mint(client)))

    client.post("/api/v1/billing/upgrade", json={"tier": "pro"})
    after = client.get("/api/v1/billing/usage").json()

    assert after["subscription"]["current_period_start"] == before["current_period_start"]
    assert after["invoices_processed"] == 1, "the consumed count was reset by an upgrade"


def test_an_upgrade_naming_both_a_tier_and_a_code_is_refused_rather_than_guessed(client):
    refused = client.post(
        "/api/v1/billing/upgrade", json={"tier": "pro", "plan_code": "starter-2026.08"}
    )
    assert refused.status_code == 422
    # `HTTPException(detail={...})` is rendered into the envelope's `error` field by
    # `app.api.errors`; `details` carries the whole detail dict beside it.
    assert refused.json()["error"] == "ambiguous_plan"


def test_an_upgrade_naming_neither_is_refused(client):
    assert client.post("/api/v1/billing/upgrade", json={}).status_code == 422


def test_an_unknown_tier_and_an_unknown_code_are_both_404_with_the_alternatives(client):
    unknown_tier = client.post("/api/v1/billing/upgrade", json={"tier": "platinum"})
    assert unknown_tier.status_code == 404
    assert unknown_tier.json()["error"] == "unknown_tier"
    assert "free" in unknown_tier.json()["detail"]["available"]

    unknown_code = client.post("/api/v1/billing/upgrade", json={"plan_code": "pro-1999.01"})
    assert unknown_code.status_code == 404
    assert unknown_code.json()["error"] == "unknown_plan"
    assert unknown_code.json()["detail"]["available"]


def test_upgrading_needs_a_session_and_not_a_key(client):
    """A commercial commitment. A bearer token in a vendor's config must not escalate its own plan."""
    token = mint(client)
    refused = client.post(
        "/api/v1/billing/upgrade",
        json={"tier": "pro"},
        headers={**auth(token), ORGANIZATION_ID_HEADER: ""},
    )
    assert refused.status_code == 403
    assert refused.json()["error_code"] == "ORGANIZATION_REQUIRED"


def test_the_invoice_listing_is_empty_before_any_period_has_closed(client):
    listed = client.get("/api/v1/billing/invoices")
    assert listed.status_code == 200
    assert listed.json() == {"invoices": [], "total": 0}


# ==========================================================================================
# 8. closing a period
# ==========================================================================================


async def test_a_period_that_ended_is_closed_priced_and_advanced(database):
    store = BillingStore(database)
    await put_on(store, TEST_ORGANIZATION_ID, tight_plan(10, allow_overage=True, rate=25))

    # Push the stored period into the past, which is what the clock would have done.
    async with database.session() as session:
        record = await BillingStore._load(session, TEST_ORGANIZATION_ID)
        record.current_period_start = datetime(2026, 6, 1, tzinfo=timezone.utc)
        record.current_period_end = datetime(2026, 7, 1, tzinfo=timezone.utc)

    rolled = await store.entitlement(
        TEST_ORGANIZATION_ID, now=datetime(2026, 7, 2, tzinfo=timezone.utc)
    )
    assert rolled.period_start == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert rolled.period_end == datetime(2026, 8, 1, tzinfo=timezone.utc)

    invoices = await store.list_invoices(organization_id=TEST_ORGANIZATION_ID)
    assert len(invoices) == 1
    assert invoices[0].period_start.replace(tzinfo=timezone.utc) == datetime(
        2026, 6, 1, tzinfo=timezone.utc
    )
    # Nothing was audited in that period, and it still gets a row: "June: nothing owed" and
    # "June: no record" are different statements and only the first can be reconciled against.
    assert invoices[0].invoices_processed == 0
    assert invoices[0].total_cents == invoices[0].base_fee_cents


async def test_periods_abut_exactly_so_no_usage_falls_between_two_of_them(database):
    store = BillingStore(database)
    async with database.session() as session:
        session.add(
            OrganizationBillingRecord(
                organization_id=TEST_ORGANIZATION_ID,
                subscription_tier="free",
                plan_code=DEFAULT_PLAN_CODE,
                monthly_invoice_quota=10,
                overage_rate_cents=0,
                allow_overage=True,
                current_period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
                current_period_end=datetime(2026, 2, 1, tzinfo=timezone.utc),
            )
        )

    await store.entitlement(TEST_ORGANIZATION_ID, now=datetime(2026, 4, 15, tzinfo=timezone.utc))
    invoices = await store.list_invoices(organization_id=TEST_ORGANIZATION_ID)

    windows = sorted(
        (
            invoice.period_start.replace(tzinfo=timezone.utc),
            invoice.period_end.replace(tzinfo=timezone.utc),
        )
        for invoice in invoices
    )
    assert len(windows) == 3, "three months elapsed, so three periods should have closed"
    for (_, ended), (starts, _) in zip(windows, windows[1:]):
        assert ended == starts, "a gap or an overlap between two billing periods"


async def test_closing_the_same_period_twice_produces_one_invoice(database):
    """The unique index *is* the idempotency. Double-charging is the failure that matters."""
    store = BillingStore(database)
    entitlement = await store.entitlement(TEST_ORGANIZATION_ID)

    first = await store.close_period(entitlement)
    second = await store.close_period(entitlement)

    assert first is not None
    assert second is None, "a second close wrote a duplicate invoice"
    assert len(await store.list_invoices(organization_id=TEST_ORGANIZATION_ID)) == 1


async def test_the_overage_line_is_the_count_times_the_rate(database):
    """The arithmetic, with numbers this test chose — see the module docstring."""
    store = BillingStore(database)
    await put_on(store, TEST_ORGANIZATION_ID, tight_plan(2, allow_overage=True, rate=25))
    entitlement = await store.entitlement(TEST_ORGANIZATION_ID)

    async with database.session() as session:
        from app.db.models import ApiUsageRecord

        session.add(
            ApiUsageRecord(
                organization_id=TEST_ORGANIZATION_ID,
                endpoint="/api/v1/audit/bulk",
                request_count=1,
                bytes_processed=0,
                duration_ms=1,
                invoices_processed=7,
                status_code=202,
                timestamp=entitlement.period_start + timedelta(seconds=1),
            )
        )

    invoice = await store.close_period(entitlement)
    assert invoice is not None
    assert invoice.invoices_processed == 7
    assert invoice.invoices_included == 2
    assert invoice.overage_invoices == 5
    assert invoice.overage_fee_cents == 5 * 25
    assert invoice.total_cents == invoice.base_fee_cents + invoice.overage_fee_cents
    # Integers throughout. A float would be exact for 25 and not for 15, which is precisely the
    # kind of bug that only appears once a real rate is set.
    assert isinstance(invoice.total_cents, int)


async def test_an_invoice_names_the_plan_it_was_priced_under_even_after_a_change(database):
    store = BillingStore(database)
    await put_on(store, TEST_ORGANIZATION_ID, tight_plan(5, allow_overage=True, rate=10))
    entitlement = await store.entitlement(TEST_ORGANIZATION_ID)
    invoice = await store.close_period(entitlement)
    assert invoice is not None
    priced_under = invoice.plan_code

    await put_on(store, TEST_ORGANIZATION_ID, tight_plan(500, allow_overage=True, rate=1))

    listed = await store.list_invoices(organization_id=TEST_ORGANIZATION_ID)
    assert listed[0].plan_code == priced_under, "a plan change rewrote an issued invoice"


async def test_one_practices_invoices_are_not_another_practices(database):
    store = BillingStore(database)
    mine = await store.entitlement(TEST_ORGANIZATION_ID)
    await store.close_period(mine)

    assert await store.list_invoices(organization_id=OTHER_ORGANIZATION_ID) == []


async def test_the_invoice_row_carries_a_currency_and_a_public_handle(database):
    store = BillingStore(database)
    invoice = await store.close_period(await store.entitlement(TEST_ORGANIZATION_ID))
    assert invoice is not None
    assert invoice.currency == "EUR"
    assert invoice.public_id.startswith("inv_")
    assert invoice.status == "ISSUED"
    assert isinstance(invoice, BillingInvoiceRecord)
