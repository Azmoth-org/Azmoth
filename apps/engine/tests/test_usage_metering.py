"""What each partner consumed, counted — the thing that has to exist before anyone is billed.

`api_keys.last_used_at` answered "is this key alive" and nothing else. These assertions are about
the questions an invoice and a support call actually ask: how many audits did this billing centre
run in August, which endpoint is that vendor hitting, and is their integration failing.

Three properties carry the feature and are tested hardest:

* **A request is counted once, against the right practice.** Miscounting is a silent revenue leak
  in one direction and an angry customer in the other.
* **A request that cannot be attributed writes nothing.** A usage table with unattributable rows is
  one whose totals nobody can reconcile against an invoice.
* **Metering can never break the request it is metering.** It runs after the answer is produced, so
  a bookkeeping failure that turned a successful audit into a `500` would be the worst possible
  trade.
"""

from __future__ import annotations

import io
import zipfile
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.api import deps
from app.api.apikeys import API_KEY_HEADER
from app.api.tenancy import ORGANIZATION_ID_HEADER
from app.config import PADNEXT_EXAMPLES_DIR
from app.db.models import ApiUsageRecord, utcnow
from app.db.session import get_database
from app.services.usage import (
    FLUSH_THRESHOLD,
    MAX_BUFFERED_ROWS,
    UsageMeter,
    UsageStore,
    month_to_date,
)

from tests.conftest import TEST_ORGANIZATION_ID

OTHER_ORGANIZATION_ID = "orgZq4Wm7Bn2Cx9Dv6Fk1Ht3Js5Lp8R"


@pytest.fixture
def delivery() -> bytes:
    return (PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml").read_bytes()


def mint(client, *, organization_id: str = TEST_ORGANIZATION_ID, name: str = "usage") -> str:
    response = client.post(
        "/api/v1/settings/api-keys",
        json={"name": name},
        headers={ORGANIZATION_ID_HEADER: organization_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


async def stored_rows() -> list[ApiUsageRecord]:
    """Everything written so far, flushing the buffer first so a test sees its own writes."""
    await deps.usage_meter().flush()
    async with get_database().session() as session:
        return list((await session.execute(select(ApiUsageRecord))).scalars().all())


# ==========================================================================================
# 1. what gets counted
# ==========================================================================================


async def test_a_partner_call_is_counted_against_the_key_and_the_practice(client, delivery):
    token = mint(client)
    response = client.post("/api/v1/audit/single", content=delivery, headers={API_KEY_HEADER: token})
    assert response.status_code == 200

    rows = [r for r in await stored_rows() if r.endpoint == "/api/v1/audit/single"]
    assert len(rows) == 1, "one request, one row"
    row = rows[0]
    assert row.organization_id == TEST_ORGANIZATION_ID
    assert row.api_key_id, "a partner call names the key that made it"
    assert row.status_code == 200
    assert row.request_count == 1
    assert row.bytes_processed == len(delivery), "the request body, as declared"
    assert row.duration_ms >= 0


async def test_a_web_tier_call_is_counted_with_no_key(client):
    """Both doors are metered, and the row says which one.

    "What is this practice's total load" and "what is this integration costing us" are different
    questions; recording only partner traffic would make the second answerable and the first not.
    """
    assert client.get("/api/v1/proposals").status_code == 200

    rows = [r for r in await stored_rows() if r.endpoint == "/api/v1/proposals"]
    assert len(rows) == 1
    assert rows[0].api_key_id is None, "a session-authenticated call has no key to name"
    assert rows[0].organization_id == TEST_ORGANIZATION_ID


async def test_a_failed_request_is_counted_too(client):
    """An integration producing four hundred 422s a day is the customer most worth noticing."""
    token = mint(client)
    refused = client.post(
        "/api/v1/audit/single", content=b'{"not":"padnext"}', headers={API_KEY_HEADER: token}
    )
    assert refused.status_code == 400

    rows = [r for r in await stored_rows() if r.endpoint == "/api/v1/audit/single"]
    assert len(rows) == 1
    assert rows[0].status_code == 400


async def test_an_unattributable_request_writes_no_row(client, delivery):
    """No tenant, no row. Totals nobody can reconcile are worse than totals that are missing."""
    anonymous = client.post("/api/v1/audit/single", content=delivery)
    assert anonymous.status_code == 401

    assert await stored_rows() == [], "a 401 has nobody to bill"


async def test_endpoints_outside_the_api_are_not_consumption(client):
    """`/openapi.json` and `/docs` are documentation, not usage."""
    assert client.get("/openapi.json").status_code == 200
    assert await stored_rows() == []


async def test_the_endpoint_recorded_is_the_template_not_the_resolved_path(client, delivery):
    """Otherwise a usage breakdown is a list of job ids rather than a list of endpoints."""
    token = mint(client)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("a_padx.xml", delivery)
    job_id = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("u.zip", archive.getvalue(), "application/zip")},
        headers={API_KEY_HEADER: token},
    ).json()["batch_id"]
    client.get(f"/api/v1/audit/bulk/{job_id}", headers={API_KEY_HEADER: token})

    endpoints = {row.endpoint for row in await stored_rows()}
    assert "/api/v1/audit/bulk/{job_id}" in endpoints
    assert not any(job_id in endpoint for endpoint in endpoints)


# ==========================================================================================
# 2. the buffer
# ==========================================================================================


async def test_rows_are_buffered_and_flushed_in_one_batch(database):
    """The trade the module makes: no database round trip per request, a bounded loss window."""
    meter = UsageMeter(database)
    for index in range(FLUSH_THRESHOLD - 1):
        await meter.record(
            organization_id=TEST_ORGANIZATION_ID,
            api_key_id="k",
            endpoint=f"/api/v1/x/{index}",
            status_code=200,
            duration_ms=1,
            bytes_processed=10,
        )

    async with database.session() as session:
        assert (await session.execute(select(ApiUsageRecord))).scalars().all() == []
    assert meter.pending == FLUSH_THRESHOLD - 1

    # The row that reaches the threshold flushes the lot.
    await meter.record(
        organization_id=TEST_ORGANIZATION_ID,
        api_key_id="k",
        endpoint="/api/v1/x/last",
        status_code=200,
        duration_ms=1,
        bytes_processed=10,
    )
    assert meter.pending == 0
    async with database.session() as session:
        rows = (await session.execute(select(ApiUsageRecord))).scalars().all()
    assert len(rows) == FLUSH_THRESHOLD


async def test_a_flush_that_fails_keeps_the_rows_rather_than_losing_them(database, monkeypatch):
    """Losing them silently is the one outcome metering must not have."""
    meter = UsageMeter(database)
    await meter.record(
        organization_id=TEST_ORGANIZATION_ID,
        api_key_id="k",
        endpoint="/api/v1/x",
        status_code=200,
        duration_ms=1,
        bytes_processed=1,
    )
    assert meter.pending == 1

    class Broken:
        def session(self):
            raise RuntimeError("the database is gone")

    monkeypatch.setattr(meter, "_database", Broken())
    assert await meter.flush() == 0, "nothing landed"
    assert meter.pending == 1, "and nothing was lost either"

    monkeypatch.undo()
    monkeypatch.setattr(meter, "_database", database)
    assert await meter.flush() == 1


async def test_the_buffer_drops_rather_than_growing_without_bound(database, monkeypatch):
    """Reachable only if the database has been refusing writes for a long time.

    Growing until the process dies loses the rows anyway *and* takes the audit service with it, so
    dropping is the better of two bad outcomes — logged, never silent.
    """
    meter = UsageMeter(database)
    meter._buffer = [object()] * MAX_BUFFERED_ROWS  # type: ignore[list-item]

    await meter.record(
        organization_id=TEST_ORGANIZATION_ID,
        api_key_id="k",
        endpoint="/api/v1/x",
        status_code=200,
        duration_ms=1,
        bytes_processed=1,
    )
    assert meter.pending == MAX_BUFFERED_ROWS, "the row was dropped, not appended"


async def test_metering_never_breaks_the_request_it_is_metering(client, delivery, monkeypatch):
    """It runs after the answer exists. A bookkeeping failure must not turn a 200 into a 500."""
    token = mint(client)

    async def explode(*args, **kwargs):
        raise RuntimeError("the meter is broken")

    monkeypatch.setattr(deps.usage_meter(), "record", explode)
    response = client.post("/api/v1/audit/single", content=delivery, headers={API_KEY_HEADER: token})
    assert response.status_code == 200, "the audit still answered"


# ==========================================================================================
# 3. reading it back
# ==========================================================================================


async def test_the_summary_totals_what_the_practice_used(client, delivery):
    token = mint(client)
    for _ in range(3):
        client.post("/api/v1/audit/single", content=delivery, headers={API_KEY_HEADER: token})
    client.post("/api/v1/audit/single", content=b"%PDF-1.7", headers={API_KEY_HEADER: token})
    await deps.usage_meter().flush()

    summary = client.get("/api/v1/settings/usage").json()

    assert summary["organization_id"] == TEST_ORGANIZATION_ID
    assert summary["total_requests"] >= 4
    assert summary["failed_requests"] == 1, "the rejected PDF"
    assert summary["total_bytes_processed"] >= 3 * len(delivery)
    assert summary["period_start"] <= summary["period_end"]

    audits = [e for e in summary["by_endpoint"] if e["endpoint"] == "/api/v1/audit/single"]
    assert audits and audits[0]["requests"] == 4
    assert audits[0]["failed_requests"] == 1
    assert audits[0]["average_duration_ms"] >= 0


async def test_reading_the_summary_flushes_first_so_it_is_never_wrongly_zero(client, delivery):
    """The bug this closes was found by using the product, not by reading the code.

    Mint a key, make three calls, open the usage screen: the buffer holds up to 25 rows or 15
    seconds of traffic and a quiet integration reaches neither, so the screen said **zero**. "You
    have made no requests" is the one answer a usage report must never give wrongly — it reads as
    "metering is broken" and the reader has no way to tell that it is not.

    Note there is no explicit flush in this test, deliberately. That is the whole assertion.
    """
    token = mint(client)
    for _ in range(3):
        client.post("/api/v1/audit/single", content=delivery, headers={API_KEY_HEADER: token})

    assert deps.usage_meter().pending > 0, (
        "the fixture must leave rows buffered, or this test proves nothing"
    )

    before = deps.usage_meter().pending
    summary = client.get("/api/v1/settings/usage").json()

    assert summary["total_requests"] >= 3, "the buffered audits are in the answer"
    # Exactly one row is left, and it is the usage read itself: the endpoint flushes inside the
    # handler, and the middleware meters the request afterwards. That ordering is why a caller sees
    # everything up to and excluding their own read, which is the only honest thing it could show.
    assert deps.usage_meter().pending == 1 < before


async def test_the_summary_separates_the_integrations_from_each_other(client, delivery):
    """`by_key` is what makes "which of our two integrations is doing this" answerable."""
    first, second = mint(client, name="a"), mint(client, name="b")
    client.post("/api/v1/audit/single", content=delivery, headers={API_KEY_HEADER: first})
    for _ in range(2):
        client.post("/api/v1/audit/single", content=delivery, headers={API_KEY_HEADER: second})
    await deps.usage_meter().flush()

    by_key = {row["key_id"]: row for row in client.get("/api/v1/settings/usage").json()["by_key"]}

    from app.services.api_keys import split_token

    assert by_key[split_token(first)]["requests"] == 1
    assert by_key[split_token(second)]["requests"] == 2
    # The web tier's own calls — minting those two keys — are the null row.
    assert None in by_key


async def test_one_practice_cannot_read_anothers_usage(client, delivery):
    """The tenancy boundary, on the endpoint whose whole content is money."""
    ours = mint(client)
    client.post("/api/v1/audit/single", content=delivery, headers={API_KEY_HEADER: ours})
    await deps.usage_meter().flush()

    theirs = client.get(
        "/api/v1/settings/usage", headers={ORGANIZATION_ID_HEADER: OTHER_ORGANIZATION_ID}
    ).json()

    assert theirs["organization_id"] == OTHER_ORGANIZATION_ID
    assert theirs["total_requests"] == 0
    assert theirs["by_key"] == []


async def test_a_partner_can_read_their_own_usage_with_their_key(client, delivery):
    """The reason the endpoint takes either credential: a partner has no browser session."""
    token = mint(client, organization_id=OTHER_ORGANIZATION_ID)
    client.post("/api/v1/audit/single", content=delivery, headers={API_KEY_HEADER: token})
    await deps.usage_meter().flush()

    # The organisation header names a *different* practice, and must not win: the credential that
    # can actually be verified decides.
    summary = client.get(
        "/api/v1/settings/usage",
        headers={API_KEY_HEADER: token, ORGANIZATION_ID_HEADER: TEST_ORGANIZATION_ID},
    ).json()

    assert summary["organization_id"] == OTHER_ORGANIZATION_ID
    assert summary["total_requests"] >= 1


async def test_a_wrong_key_is_refused_rather_than_falling_back_to_the_header(client):
    """The branch must not be usable as a bypass.

    If a bad key fell through to the header, an attacker who could reach the engine directly would
    present garbage plus any organisation id and read that practice's spend.
    """
    from app.services.api_keys import KEY_PREFIX

    response = client.get(
        "/api/v1/settings/usage",
        headers={API_KEY_HEADER: f"{KEY_PREFIX}aaaaaaaaaaaa_" + "b" * 48},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "API_KEY_INVALID"


async def test_an_explicit_window_is_honoured_and_reported(client, delivery, database):
    """A usage figure whose period the reader has to guess is one two people compute differently."""
    store = UsageStore(database)
    now = utcnow()
    async with database.session() as session:
        session.add_all(
            [
                ApiUsageRecord(
                    api_key_id="k",
                    organization_id=TEST_ORGANIZATION_ID,
                    endpoint="/api/v1/audit/single",
                    request_count=1,
                    bytes_processed=100,
                    duration_ms=5,
                    status_code=200,
                    timestamp=now - timedelta(days=offset),
                )
                for offset in (0, 1, 40)
            ]
        )

    recent = await store.summarise(
        organization_id=TEST_ORGANIZATION_ID, since=now - timedelta(days=7), until=now
    )
    assert recent["total_requests"] == 2, "the 40-day-old row is outside the window"

    everything = await store.summarise(
        organization_id=TEST_ORGANIZATION_ID, since=now - timedelta(days=90), until=now
    )
    assert everything["total_requests"] == 3


def test_the_default_window_is_the_calendar_month_in_utc():
    """UTC and not local time: a month boundary that moved twice a year would make one set of rows
    produce two different invoices."""
    from datetime import datetime, timezone

    start, end = month_to_date(datetime(2026, 8, 30, 14, 5, tzinfo=timezone.utc))
    assert start == datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 30, 14, 5, tzinfo=timezone.utc)
