"""The one boundary `app.api.session_auth` enforces: `POST /api/v1/rules/{rule_id}/review`.

Every other test in the suite goes through the `client` fixture, which carries a valid session
token on every request by default (see `tests/conftest.py`) so this boundary does not interfere
with tests that are not about it — the same reason `TEST_ORGANIZATION_ID` is on every request and
`tests/test_tenancy.py` is where the tenancy boundary itself is tested.

This file is the one that is about it. It builds its own clients — with the header missing, using
the wrong scheme, malformed, expired, claiming the wrong issuer or audience, or signed by a key the
engine's JWKS does not name — and asserts each is refused before the review is ever recorded, then
asserts the one legitimate shape is accepted. The signing is real Ed25519 (see
`tests/conftest.py::mint_session_token`), so a forged or mis-keyed token is rejected by an actual
signature check, not by a stub standing in for one.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.tenancy import ORGANIZATION_ID_HEADER
from app.main import app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.conftest import TEST_ORGANIZATION_ID, mint_session_token


def _client(*, authorization: str | None) -> TestClient:
    """A client wired to the same running app the `client` fixture already started — an ad-hoc
    `TestClient` needs no lifespan of its own once one is active, and every test here takes
    `client` as a parameter to keep that lifespan open for its duration.

    `authorization=None` omits the header entirely, which is the "no token at all" case; every
    other case passes an explicit string, including a deliberately wrong one.
    """
    headers = {ORGANIZATION_ID_HEADER: TEST_ORGANIZATION_ID}
    if authorization is not None:
        headers["Authorization"] = authorization
    return TestClient(app, headers=headers)


def _a_rule_id(client: TestClient) -> str:
    body = client.get("/api/v1/rules/review-queue", params={"limit": 1}).json()
    return body["rules"][0]["rule_id"]


def review(client: TestClient, rule_id: str, **body) -> object:
    payload = {"status": "PENDING", "reviewed_by": "", "review_notes": ""}
    payload.update(body)
    return client.post(f"/api/v1/rules/{rule_id}/review", json=payload)


def test_no_authorization_header_is_refused(client):
    """The vulnerability this closes: no credential at all used to reach the review logic."""
    rule_id = _a_rule_id(client)

    response = review(_client(authorization=None), rule_id)

    assert response.status_code == 401
    assert response.json()["error_code"] == "SESSION_TOKEN_REQUIRED"


def test_a_non_bearer_scheme_is_refused(client):
    rule_id = _a_rule_id(client)
    token = mint_session_token()

    response = review(_client(authorization=f"Token {token}"), rule_id)

    assert response.status_code == 401
    assert response.json()["error_code"] == "SESSION_TOKEN_REQUIRED"


def test_a_malformed_token_is_refused(client):
    rule_id = _a_rule_id(client)

    response = review(_client(authorization="Bearer not-a-jwt-at-all"), rule_id)

    assert response.status_code == 401
    assert response.json()["error_code"] == "SESSION_TOKEN_INVALID"


def test_an_expired_token_is_refused(client):
    rule_id = _a_rule_id(client)
    token = mint_session_token(expires_in_seconds=-10)

    response = review(_client(authorization=f"Bearer {token}"), rule_id)

    assert response.status_code == 401
    assert response.json()["error_code"] == "SESSION_TOKEN_INVALID"


def test_the_wrong_issuer_is_refused(client):
    """Not this pair of services — a token minted for something else must not work here."""
    rule_id = _a_rule_id(client)
    token = mint_session_token(issuer="not-azmoth-web")

    response = review(_client(authorization=f"Bearer {token}"), rule_id)

    assert response.status_code == 401
    assert response.json()["error_code"] == "SESSION_TOKEN_INVALID"


def test_the_wrong_audience_is_refused(client):
    rule_id = _a_rule_id(client)
    token = mint_session_token(audience="not-azmoth-engine")

    response = review(_client(authorization=f"Bearer {token}"), rule_id)

    assert response.status_code == 401
    assert response.json()["error_code"] == "SESSION_TOKEN_INVALID"


def test_a_token_naming_an_unknown_signing_key_is_refused(client):
    """A `kid` the engine's JWKS has never heard of — the forger picked an id, not a real key."""
    rule_id = _a_rule_id(client)
    rogue_key = Ed25519PrivateKey.generate()
    token = mint_session_token(signing_key=rogue_key, kid="a-key-the-engine-never-saw")

    response = review(_client(authorization=f"Bearer {token}"), rule_id)

    assert response.status_code == 401
    assert response.json()["error_code"] == "SESSION_TOKEN_INVALID"


def test_a_token_signed_by_the_wrong_key_under_a_known_kid_is_refused(client):
    """The direct forgery check: a real, known `kid`, signed by a key that is not the one that
    `kid` names in the JWKS. If this passed, the signature check would not be checking anything."""
    rule_id = _a_rule_id(client)
    rogue_key = Ed25519PrivateKey.generate()
    token = mint_session_token(signing_key=rogue_key)  # kid defaults to the real, known one

    response = review(_client(authorization=f"Bearer {token}"), rule_id)

    assert response.status_code == 401
    assert response.json()["error_code"] == "SESSION_TOKEN_INVALID"


def test_none_of_the_refused_attempts_recorded_a_review(client):
    """The refusals above must have refused before touching the database, not merely answered 401
    on top of a review that was recorded anyway."""
    rule_id = _a_rule_id(client)

    review(_client(authorization=None), rule_id, status="VERIFIED", reviewed_by="Forger")

    queue = client.get("/api/v1/rules/review-queue", params={"limit": 1000}).json()
    still_pending = next(r for r in queue["rules"] if r["rule_id"] == rule_id)
    assert still_pending["review_status"] is None


def test_a_validly_signed_current_token_is_accepted(client):
    """The one legitimate shape: right signature, right issuer, right audience, not expired —
    exactly what `apps/web/lib/engine.ts` attaches on every proxied call."""
    rule_id = _a_rule_id(client)
    token = mint_session_token()

    response = review(
        _client(authorization=f"Bearer {token}"),
        rule_id,
        status="VERIFIED",
        reviewed_by="Frau Dr. Prüfer",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rule"]["rule_id"] == rule_id
    assert body["rule"]["review_status"] == "VERIFIED"
