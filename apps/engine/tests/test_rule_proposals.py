"""`POST /api/v1/rules/proposals` — a pilot's report that a Ziffer has no rule at all.

Deliberately the simplest write in the API: one row in, a confirmation out, nothing merged into the
running engine. What is worth testing is exactly what `app.db.models.RuleProposalRecord` and
`app.api.rules.propose_rule` promise: the write is scoped to the caller's organisation, validated at
the boundary rather than trusted, rate-limited per organisation rather than left open, and durable —
still there under a direct query, not just in the response that echoed it back.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.identity import USER_ID_HEADER
from app.api.tenancy import ORGANIZATION_ID_HEADER
from app.config import get_settings
from app.db.models import RuleProposalRecord
from app.db.session import get_database
from app.main import app

from tests.conftest import TEST_ORGANIZATION_ID, TEST_SESSION_AUTHORIZATION_HEADER


def _client(*, organization: str | None) -> TestClient:
    """A client wired to the already-running app, with `X-Organization-ID` under this test's
    control rather than the shared fixture's default — the same shape as
    `tests/test_rules_review_auth.py::_client` for the Authorization header.
    """
    headers = {"Authorization": TEST_SESSION_AUTHORIZATION_HEADER}
    if organization is not None:
        headers[ORGANIZATION_ID_HEADER] = organization
    return TestClient(app, headers=headers)


async def stored_rows(organization_id: str | None = None) -> list[RuleProposalRecord]:
    """Every `rule_proposals` row, optionally filtered — read directly, not through the API.

    There is no `GET` endpoint in front of this table (see the module docstring of
    `app.schemas.rule_proposals`), so a direct query is the only way to assert what was actually
    persisted rather than only what the response echoed.
    """
    async with get_database().session() as session:
        statement = select(RuleProposalRecord)
        if organization_id is not None:
            statement = statement.where(RuleProposalRecord.organization_id == organization_id)
        rows = list((await session.execute(statement)).scalars().all())
        for row in rows:
            _ = (row.id, row.ziffer, row.context, row.receipt_hash, row.organization_id, row.created_by)
        return rows


def _payload(**overrides) -> dict:
    payload = {"ziffer": "34", "context": "Die Leistung wird nicht als unconfirmed markiert."}
    payload.update(overrides)
    return payload


# ==============================================================================================
# the happy path, and what actually lands in the row
# ==============================================================================================


async def test_a_report_is_stored_and_confirmed(client):
    response = client.post("/api/v1/rules/proposals", json=_payload(receipt_hash="a" * 64))
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["ziffer"] == "34"
    assert body["context"] == "Die Leistung wird nicht als unconfirmed markiert."
    assert body["receipt_hash"] == "a" * 64
    assert body["id"]
    assert body["created_at"]

    rows = await stored_rows(TEST_ORGANIZATION_ID)
    assert len(rows) == 1
    row = rows[0]
    assert row.ziffer == "34"
    assert row.organization_id == TEST_ORGANIZATION_ID
    assert row.receipt_hash == "a" * 64


async def test_receipt_hash_is_optional(client):
    response = client.post("/api/v1/rules/proposals", json=_payload())
    assert response.status_code == 201, response.text
    assert response.json()["receipt_hash"] is None

    rows = await stored_rows(TEST_ORGANIZATION_ID)
    assert rows[-1].receipt_hash is None


async def test_a_blank_receipt_hash_is_treated_as_absent(client):
    response = client.post("/api/v1/rules/proposals", json=_payload(receipt_hash="   "))
    assert response.status_code == 201, response.text
    assert response.json()["receipt_hash"] is None


async def test_the_actor_the_web_tier_forwards_is_recorded(client):
    response = client.post(
        "/api/v1/rules/proposals", json=_payload(), headers={USER_ID_HEADER: "user-abc123"}
    )
    assert response.status_code == 201, response.text

    rows = await stored_rows(TEST_ORGANIZATION_ID)
    assert rows[-1].created_by == "user-abc123"


async def test_a_call_with_no_user_id_header_is_recorded_as_anonymous(client):
    response = client.post("/api/v1/rules/proposals", json=_payload())
    assert response.status_code == 201, response.text

    rows = await stored_rows(TEST_ORGANIZATION_ID)
    assert rows[-1].created_by == "anonymous"


# ==============================================================================================
# validation at the boundary
# ==============================================================================================


def test_a_missing_ziffer_is_refused(client):
    payload = _payload()
    del payload["ziffer"]
    response = client.post("/api/v1/rules/proposals", json=payload)
    assert response.status_code == 422


def test_an_empty_context_is_refused(client):
    response = client.post("/api/v1/rules/proposals", json=_payload(context=""))
    assert response.status_code == 422


def test_a_context_over_the_limit_is_refused(client):
    response = client.post("/api/v1/rules/proposals", json=_payload(context="x" * 501))
    assert response.status_code == 422


def test_a_context_at_the_limit_is_accepted(client):
    response = client.post("/api/v1/rules/proposals", json=_payload(context="x" * 500))
    assert response.status_code == 201, response.text


def test_an_unexpected_field_is_refused(client):
    """`extra="forbid"` on `RuleProposalRequest` — a typo'd field must not be silently dropped."""
    response = client.post("/api/v1/rules/proposals", json=_payload(recipet_hash="typo"))
    assert response.status_code == 422


# ==============================================================================================
# tenancy
# ==============================================================================================


def test_a_request_without_an_organisation_is_refused():
    response = _client(organization=None).post("/api/v1/rules/proposals", json=_payload())
    assert response.status_code == 403
    assert response.json()["error_code"] == "ORGANIZATION_REQUIRED"


async def test_two_organisations_reports_do_not_mix(client):
    other_org = "orgOtherPracticeXXXXXXXXXXXXXXXX"

    assert client.post("/api/v1/rules/proposals", json=_payload(ziffer="1")).status_code == 201
    other_response = _client(organization=other_org).post(
        "/api/v1/rules/proposals", json=_payload(ziffer="2")
    )
    assert other_response.status_code == 201

    mine = await stored_rows(TEST_ORGANIZATION_ID)
    theirs = await stored_rows(other_org)

    assert [row.ziffer for row in mine] == ["1"]
    assert [row.ziffer for row in theirs] == ["2"]


# ==============================================================================================
# the rate limit
# ==============================================================================================


@pytest.fixture
def tight_rule_proposal_limit(monkeypatch):
    """Two reports an hour, so a test can actually reach the ceiling — same shape as
    `tests/test_partner_api.py::tight_limits`.
    """
    monkeypatch.setenv("RATE_LIMIT_RULE_PROPOSALS_PER_HOUR", "2")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def test_the_limit_refuses_the_third_report_in_an_hour(client, tight_rule_proposal_limit):
    for _ in range(2):
        allowed = client.post("/api/v1/rules/proposals", json=_payload())
        assert allowed.status_code == 201, allowed.text
        assert allowed.headers["X-RateLimit-Limit"] == "2"

    refused = client.post("/api/v1/rules/proposals", json=_payload())
    assert refused.status_code == 429, refused.text
    body = refused.json()
    assert body["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert body["details"]["limit"] == 2
    assert body["details"]["bucket"] == "rule_proposal"
    assert refused.headers["Retry-After"] == str(body["retry_after"])


def test_the_limit_is_per_organisation_not_shared(client, tight_rule_proposal_limit):
    """A second practice's requests are not spent out of the first one's budget."""
    for _ in range(2):
        assert client.post("/api/v1/rules/proposals", json=_payload()).status_code == 201

    other = _client(organization="orgAnotherPracticeYYYYYYYYYYYYYY")
    assert other.post("/api/v1/rules/proposals", json=_payload()).status_code == 201


def test_the_limit_can_be_switched_off(client, tight_rule_proposal_limit, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    try:
        for _ in range(3):
            assert client.post("/api/v1/rules/proposals", json=_payload()).status_code == 201
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
