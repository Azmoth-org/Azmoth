"""Oversized request bodies must be refused at the perimeter, before they are buffered.

The defect these guard. `POST /api/v1/padnext/audit` declares `body: bytes`, so FastAPI reads the
whole body before the handler runs — the reader's own 32 MiB check fired only after the memory was
already committed. On an endpoint needing no authentication, one oversized POST exhausted the process.

The distinction that matters here is WHERE the request dies. A test that only asserts "large request
is rejected" would pass against the old code too, because the in-handler check did reject it. So the
central test below asserts the response comes from the middleware, identified by its error code, and
that the handler was never reached.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

LIMIT = get_settings().max_request_bytes


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_a_body_over_the_limit_is_refused_with_413(client):
    # Content-Length is advertised honestly; the body itself is never sent, because the point is
    # that the perimeter decides on the header alone.
    response = client.post(
        "/api/v1/padnext/audit",
        content=b"",
        headers={"Content-Length": str(LIMIT + 1), "Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413, response.text


def test_the_rejection_comes_from_the_perimeter_not_the_reader(client):
    """The whole point of the fix.

    `app.padnext.reader` also refuses oversized input, with a message about XML bytes. If THAT is what
    answers, the body was already in memory and nothing was actually fixed.
    """
    response = client.post(
        "/api/v1/padnext/audit",
        content=b"",
        headers={"Content-Length": str(LIMIT + 1), "Content-Type": "application/octet-stream"},
    )
    body = response.json()

    assert body["error"] == "request_too_large", body
    assert body["max_bytes"] == LIMIT
    assert "Rejected before reading the body" in body["message"]
    # The reader's wording must NOT appear: its presence would mean the handler ran.
    assert "above the" not in body["message"], "this looks like the in-handler check answering"


def test_the_limit_applies_to_every_endpoint_not_just_padnext(client):
    """The middleware is global on purpose: `code/rules` takes JSON and had the same exposure."""
    response = client.post(
        "/api/v1/code/rules",
        content=b"",
        headers={"Content-Length": str(LIMIT + 1), "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"] == "request_too_large"


def test_a_body_at_the_limit_is_still_accepted(client):
    """Off-by-one in the wrong direction would reject a legitimate delivery."""
    response = client.post(
        "/api/v1/padnext/audit",
        content=b"",
        headers={"Content-Length": str(LIMIT), "Content-Type": "application/octet-stream"},
    )
    # 400 because the body is empty — which proves the middleware let it through to the handler.
    assert response.status_code == 400
    assert "Empty body" in response.json()["detail"]


def test_a_malformed_content_length_is_refused_rather_than_guessed(client):
    response = client.post(
        "/api/v1/padnext/audit",
        content=b"",
        headers={"Content-Length": "not-a-number", "Content-Type": "application/octet-stream"},
    )
    # httpx may normalise this; accept either a 400 from us or a transport-level rejection.
    assert response.status_code in (400, 413, 422), response.text


def test_a_normal_delivery_still_audits(client):
    """The guard must not have broken the feature it protects."""
    from app.config import PADNEXT_EXAMPLES_DIR

    payload = (PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001.padx").read_bytes()
    assert len(payload) < LIMIT

    response = client.post(
        "/api/v1/padnext/audit",
        content=payload,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["positions"]) == 9


def test_the_readers_own_check_is_still_there_as_defence_in_depth(): 
    """A chunked request carries no Content-Length and cannot be pre-screened, so the in-handler
    check must NOT have been removed when the middleware was added."""
    from app.padnext import reader

    assert reader.MAX_XML_BYTES > 0
    source = (reader.__file__)
    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    assert "len(data) > MAX_XML_BYTES" in text, "the backstop check was removed"
