"""The public demo, and the four properties that make it safe to publish.

`/api/v1/demo/*` is the only surface in this service reachable without any credential. Three of the
assertions below are about what it *cannot* do, and they are the reason the endpoint may exist at
all — a public route in a system whose compliance document opens with "not cleared to process real
patient data" earns its place by being provably unable to receive any.

* **It accepts no input.** A body, a query string and a form post all produce the same report as an
  empty request. There is no way to make it audit a caller's document, so it is not a processor of
  anybody's data — it serves one committed synthetic file.
* **It bills nobody.** No tenant reaches the request context, so `_meter` writes no
  `api_usage_logs` row. Asserted directly against the table rather than trusted, because "it
  happens not to be metered today" and "it cannot be metered" are different claims.
* **It refuses non-synthetic data even where the deployment allows it.** `PADNEXT_ALLOW_REAL_DATA`
  exists for a private deployment with a lawful basis; it must not reach a public endpoint.
* **It is the real engine.** The report carries the same verdicts and the same `receipt_hash` as
  `POST /api/v1/padnext/audit` on the same bytes — the demo shows the product, not a fixture of
  what the product would say.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api import deps
from app.config import PADNEXT_EXAMPLES_DIR
from app.db.models import ApiUsageRecord
from app.db.session import get_database
from app.services import demo as demo_service
from app.services.demo import (
    DEMO_DELIVERY_FILENAME,
    DemoUnavailable,
    assert_synthetic,
    demo_delivery_path,
)

from tests.conftest import TEST_ORGANIZATION_ID


@pytest.fixture
def anonymous_client():
    """A client with **no** headers at all — no organisation, no user, no API key.

    Deliberately not the shared `client` fixture, which sets `X-Organization-ID` on every request
    and would therefore hide the two properties this module exists to pin: that the demo needs no
    tenant, and that having no tenant is what keeps it out of the usage table.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    deps.reset()
    demo_service.reset_demo_cache()
    with TestClient(app) as test_client:
        if not deps.pipeline().souffle.available():
            pytest.skip("Soufflé is not available")
        yield test_client
    demo_service.reset_demo_cache()
    deps.reset()


# ==================================================================================================
# it works, and it is the real engine
# ==================================================================================================


def test_demo_audit_needs_no_credential(anonymous_client):
    """No API key, no session, no organisation header — and a complete report."""
    response = anonymous_client.post("/api/v1/demo/audit")

    assert response.status_code == 200
    report = response.json()
    assert len(report["positions"]) == 9
    assert report["findings"], "the bundled delivery has nine deliberate errors"


def test_demo_report_reconciles_and_splits_three_ways(anonymous_client):
    """The three buckets, and the identity that makes them trustworthy."""
    report = anonymous_client.post("/api/v1/demo/audit").json()

    from decimal import Decimal

    claimed = Decimal(report["claimed_total_eur"])
    bucketed = (
        Decimal(report["confirmed_fine_eur"])
        + Decimal(report["confirmed_wrong_eur"])
        + Decimal(report["unconfirmed_eur"])
    )
    assert bucketed == claimed
    # The amber bucket is the largest, which is the honest state of coverage and the single most
    # important thing the demo has to show rather than hide.
    assert Decimal(report["unconfirmed_eur"]) > Decimal(report["confirmed_wrong_eur"])
    assert 0.0 < report["coverage_ratio"] < 1.0


def test_demo_matches_the_authenticated_audit_of_the_same_file(anonymous_client):
    """The demo is the product. Same bytes through the tenant-scoped path, same receipt hash.

    This is what stops the public demo drifting into a marketing artefact: if someone changes the
    audit and only the authenticated path moves, this fails.
    """
    demo = anonymous_client.post("/api/v1/demo/audit").json()

    payload = (PADNEXT_EXAMPLES_DIR / DEMO_DELIVERY_FILENAME).read_bytes()
    direct = anonymous_client.post(
        "/api/v1/padnext/audit",
        content=payload,
        headers={
            "Content-Type": "application/xml",
            "x-padnext-filename": DEMO_DELIVERY_FILENAME,
        },
    )
    assert direct.status_code == 200

    assert demo["receipt_hash"] == direct.json()["receipt_hash"]
    assert demo["claimed_total_eur"] == direct.json()["claimed_total_eur"]


def test_demo_is_deterministic_across_calls(anonymous_client):
    """Twice, byte for byte. The memo must not be able to serve a different answer than a fresh run."""
    first = anonymous_client.post("/api/v1/demo/audit").json()
    demo_service.reset_demo_cache()
    second = anonymous_client.post("/api/v1/demo/audit").json()

    assert first["receipt_hash"] == second["receipt_hash"]
    assert first["positions"] == second["positions"]


# ==================================================================================================
# it accepts no input — the property that makes it publishable
# ==================================================================================================


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"content": b"<xml>anything</xml>"}, id="raw-body"),
        pytest.param({"json": {"file": "something"}}, id="json-body"),
        pytest.param({"data": {"file": "something"}}, id="form-body"),
    ],
)
def test_demo_ignores_anything_a_caller_sends(anonymous_client, kwargs):
    """A body of any shape changes nothing. This endpoint cannot be turned into an upload.

    The legal claim in `app/api/demo.py` rests on exactly this: there is no request that makes the
    public endpoint process a visitor's document. If a body ever started to matter, the endpoint
    would become a medical-data processor open to the internet, and this test is what fails first.
    """
    baseline = anonymous_client.post("/api/v1/demo/audit").json()
    response = anonymous_client.post("/api/v1/demo/audit", **kwargs)

    assert response.status_code == 200
    assert response.json()["receipt_hash"] == baseline["receipt_hash"]
    assert response.json()["source_name"] == DEMO_DELIVERY_FILENAME


def test_demo_has_no_query_or_path_parameters():
    """The route takes no parameters at all — checked on the signature, not on behaviour."""
    import inspect

    from app.api.demo import demo_audit, demo_pdf

    assert inspect.signature(demo_audit).parameters == {}
    assert inspect.signature(demo_pdf).parameters == {}


# ==================================================================================================
# it bills nobody
# ==================================================================================================


async def test_demo_writes_no_usage_row(anonymous_client):
    """A demo visitor cannot appear in `api_usage_logs` — not as a free row, as no row.

    The constraint the product brief states as "must not be a billable event". It holds because
    `_meter` needs an `organization_id` and the demo has no tenant, which is a stronger property
    than a flag: there is nothing to remember to filter out when an invoice is built.
    """
    for _ in range(3):
        assert anonymous_client.post("/api/v1/demo/audit").status_code == 200
    anonymous_client.post("/api/v1/demo/report.pdf")

    # Force the buffer out, so this cannot pass merely because nothing has flushed yet.
    await deps.usage_meter().flush()

    database = get_database()
    async with database.session() as session:
        rows = (await session.execute(select(ApiUsageRecord))).scalars().all()

    assert rows == [], f"the public demo must never be metered; found {len(rows)} row(s)"


async def test_a_tenant_scoped_request_still_is_metered(client):
    """The other half of the pair: metering works, it is only the demo that has nobody to bill.

    A tenant-scoped endpoint, because that is what `_meter` keys on — it records a row when the
    request context carries an `organization_id`, which `app.api.tenancy` binds. Note that
    `/padnext/audit` would *not* do here: it requires no organisation (it stores nothing), so
    nothing binds one and it is unmetered for the same structural reason the demo is.
    """
    response = client.get("/api/v1/proposals")
    assert response.status_code == 200

    await deps.usage_meter().flush()

    database = get_database()
    async with database.session() as session:
        rows = (await session.execute(select(ApiUsageRecord))).scalars().all()

    assert [row.organization_id for row in rows] == [TEST_ORGANIZATION_ID]


# ==================================================================================================
# it refuses non-synthetic data whatever the deployment allows
# ==================================================================================================


def test_assert_synthetic_refuses_real_data_regardless_of_the_override(monkeypatch):
    """`PADNEXT_ALLOW_REAL_DATA` must not reach the public endpoint.

    That switch exists so a *private* deployment with a lawful basis can process real deliveries
    deliberately. A deployment making that choice for its own authenticated users has not thereby
    decided to serve one to the open internet, so the demo guard is separate from the audit guard
    and is not switchable.
    """
    monkeypatch.setenv("PADNEXT_ALLOW_REAL_DATA", "1")

    class _RealDelivery:
        echtdaten = True

    with pytest.raises(DemoUnavailable):
        assert_synthetic(_RealDelivery())


def test_the_bundled_demo_delivery_is_synthetic():
    """The fixture the public endpoint serves says, in its own bytes, that it is test data."""
    from app.padnext import read_delivery

    path = demo_delivery_path()
    assert path.is_file(), f"the demo delivery is missing at {path}"

    delivery, _ = read_delivery(path.read_bytes(), source_name=DEMO_DELIVERY_FILENAME)
    assert delivery.echtdaten is not True
    assert_synthetic(delivery)


def test_missing_fixture_is_a_503_not_a_500(anonymous_client, monkeypatch):
    """A deployment fault answers 503 and keeps the rest of the service up."""
    monkeypatch.setattr(
        demo_service, "demo_delivery_path", lambda settings=None: __import__("pathlib").Path("/nonexistent/x.xml")
    )
    demo_service.reset_demo_cache()

    response = anonymous_client.post("/api/v1/demo/audit")

    assert response.status_code == 503
    assert response.json()["error_code"] == "DEMO_UNAVAILABLE"
    # Everything else still answers.
    assert anonymous_client.get("/api/v1/health").status_code == 200


# ==================================================================================================
# the PDF
# ==================================================================================================


def test_demo_pdf_renders_and_is_deterministic(anonymous_client):
    first = anonymous_client.post("/api/v1/demo/report.pdf")
    second = anonymous_client.post("/api/v1/demo/report.pdf")

    assert first.status_code == 200
    assert first.headers["content-type"] == "application/pdf"
    assert first.content.startswith(b"%PDF-1.4")
    assert "azmoth_demo_pruefbericht.pdf" in first.headers["content-disposition"]
    assert first.content == second.content


def test_demo_pdf_says_it_is_synthetic_inside_the_document(anonymous_client):
    """The demo note is rendered into the PDF, so a forwarded copy still says what it is."""
    from app.api.demo import DEMO_PDF_NOTE

    content = anonymous_client.post("/api/v1/demo/report.pdf").content

    # The canvas writes cp1252, and the note reaches the content stream as drawn text.
    assert DEMO_PDF_NOTE.split(" —")[0].encode("cp1252") in content


def test_single_report_pdf_never_merges_the_three_buckets(anonymous_client):
    """The refusal that matters most in print: no "Risiko" total on a document that outlives us."""
    content = anonymous_client.post("/api/v1/demo/report.pdf").content

    assert "Nicht beurteilbar".encode("cp1252") in content
    assert "Risiko".encode("cp1252") in content  # only inside the sentence refusing to compute one
    assert "Gesamtrisiko".encode("cp1252") not in content
