"""`GET /health` — the root liveness probe and its database check.

The endpoint's whole value is that it is *not* the same thing as `/api/v1/health`, so most of what
is asserted here is about the boundary between them: that this one answers without probing a solver,
that it reports the database rather than the catalog, and that a database it cannot reach produces a
`503` rather than a cheerful `200` with a sad field in the body.
"""

from __future__ import annotations

import asyncio

import pytest

from app.api.liveness import DB_PROBE_TIMEOUT_S, probe_database
from app.config import Settings
from app.db.session import Database, get_database, set_database


def test_health_is_ok_when_the_database_answers(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert body["database"]["detail"] == ""


def test_health_names_the_service_so_a_misaimed_monitor_notices():
    """`service` is what distinguishes this from the web tier's `/api/health`.

    Both answer `{"status": "ok", ...}` on a path called health, so a monitor pointed at the wrong
    container reports green either way unless something in the body says which process replied.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as unscoped:
        assert unscoped.get("/health").json()["service"] == "engine"


def test_health_needs_no_organisation_header():
    """A healthcheck that required a tenant would report every container unhealthy forever.

    The `client` fixture sets `X-Organization-ID` on every request, which would hide a regression
    here — so this one builds a client that sends nothing.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as unscoped:
        assert unscoped.get("/health").status_code == 200


def test_health_is_not_under_the_api_prefix(client):
    """Infrastructure calls `/health`; there is no versioned alias, and adding one would be a
    second path to keep in step with the first."""
    assert client.get("/api/v1/health").status_code == 200  # the diagnostic, still there
    assert client.get("/health").status_code == 200


def test_the_two_health_endpoints_report_different_things(client):
    """The split is the design. If these ever return the same shape, one of them is redundant."""
    liveness = client.get("/health").json()
    diagnostic = client.get("/api/v1/health").json()

    # The cheap one says nothing about solvers — that is what makes it cheap.
    assert "solvers" not in liveness
    assert "catalog_version" not in liveness
    # And the diagnostic says nothing about the database, so a Neon blip cannot degrade the field
    # the compose healthcheck and the dashboard's System Health card both read.
    assert "database" not in diagnostic
    assert diagnostic["status"] == "ok"


def test_an_unreachable_database_is_503_with_the_reason(client):
    """The status code carries the verdict, because that is what a monitor branches on.

    Swapping the process-wide `Database` for one pointed at a closed port is the honest way to
    simulate this: it exercises the real driver, the real timeout path and the real exception
    rendering, rather than a mock that would agree with whatever this test asserted.
    """
    healthy = get_database()
    set_database(Database(Settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/nothing")))
    try:
        response = client.get("/health")
    finally:
        set_database(healthy)

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"]["status"] == "failed"
    assert body["database"]["detail"], "a 503 that does not say why is a 503 nobody can act on"


def test_the_failure_detail_never_carries_the_password(client):
    """`database.url` is published so an operator can see *which* database did not answer.

    That is only acceptable because `Database.url` renders the password as `***`. A regression here
    would leak a production credential into whatever an uptime monitor logs, which is the sort of
    thing that is discovered years later in a log aggregator.
    """
    healthy = get_database()
    secret = "hunter2correcthorse"
    set_database(
        Database(Settings(database_url=f"postgresql+asyncpg://u:{secret}@127.0.0.1:1/nothing"))
    )
    try:
        body = client.get("/health").json()
    finally:
        set_database(healthy)

    assert secret not in str(body)
    assert "***" in body["database"]["url"]


def test_the_probe_reports_rather_than_raises():
    """`probe_database` must never raise: an exception here would be rendered as a 500 with an
    `INTERNAL_ERROR` envelope, telling a monitor the engine is broken when the database is."""
    healthy = get_database()
    set_database(Database(Settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/nothing")))
    try:
        result = asyncio.run(probe_database())
    finally:
        set_database(healthy)

    assert result.status == "failed"
    assert result.latency_ms >= 0


def test_the_probe_timeout_stays_under_a_monitor_interval():
    """A probe that can block for longer than the poll interval piles up connections instead of
    reporting a slow database. Caddy is configured with `health_interval 10s`."""
    assert 0 < DB_PROBE_TIMEOUT_S < 10


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_neither_health_endpoint_is_metered(client, path):
    """Usage metering covers `/api/v1/*` consumption, and a liveness poll is not consumption.

    Asserted because `/health` is polled every few seconds forever: if it ever started producing
    usage rows, a practice's invoice would be dominated by the uptime monitor.
    """
    from app.api.deps import usage_meter

    before = usage_meter().pending
    client.get(path)
    assert usage_meter().pending == before
