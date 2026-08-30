"""The floor under a support conversation: an id, a structured line, and a recorded crash.

None of this changes an answer the engine gives. What it changes is whether "the upload didn't
work" is a question anyone can act on. Before it, a pilot user's failure left a traceback in
whatever container log had not yet rotated, with no id to search on and no way to tell whether it
had happened to anyone else — survivable while we are the only caller, and not survivable the day
somebody is paying.

So the assertions here are about *evidence* rather than about behaviour:

* every response carries an id, including the ones that failed before a route was reached;
* an id supplied by a proxy is adopted rather than replaced, so two tiers' logs join;
* a log line emitted anywhere under a request carries that request's id — including from inside the
  threadpool, which is where every solve actually runs;
* a partner request's lines name the key and the practice;
* an unhandled 500 leaves a row somebody can be asked about, and hands the caller the id to quote.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api import deps
from app.api.apikeys import API_KEY_HEADER
from app.api.tenancy import ORGANIZATION_ID_HEADER
from app.core.observability import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    bind,
    current_request_id,
    set_error_hook,
)
from app.db.models import ErrorLogRecord
from app.db.session import get_database

from tests.conftest import TEST_ORGANIZATION_ID


@pytest.fixture
def logs(caplog):
    """Capture at INFO across the whole app, which is where the request line is emitted.

    `caplog.set_level` is doing more than it looks: pytest's logging plugin resets the root
    logger's level between tests, so an INFO record is dropped before any handler sees it unless a
    test says otherwise. A test that reads log output without this passes alone and silently
    asserts nothing in a full run.
    """
    caplog.set_level(logging.INFO)
    return caplog


def _request_lines(caplog) -> list:
    return [r for r in caplog.records if r.name == "app.request"]


# ==========================================================================================
# 1. the request id
# ==========================================================================================


def test_every_response_carries_a_request_id(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]
    assert len(response.headers[REQUEST_ID_HEADER]) == 32, "a uuid4 hex, when we mint it"


def test_an_id_supplied_by_a_proxy_is_adopted_rather_than_replaced(client):
    """What makes the web tier's logs and the engine's logs joinable on one value.

    If the engine minted a fresh id per hop, tracing a user's action from the browser through the
    Next.js proxy into the engine would need three separate searches and a guess about timing.
    """
    supplied = "trace-from-the-proxy-0001"
    response = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: supplied})
    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_a_hostile_request_id_cannot_forge_a_log_line(client):
    """It reaches a log line and a response header, so it is stripped and capped like every other
    header value this service echoes (`app.api.identity`, `app.api.tenancy`)."""
    response = client.get(
        "/api/v1/health", headers={REQUEST_ID_HEADER: "abc\r\nlevel=CRITICAL fake" + "x" * 500}
    )
    echoed = response.headers[REQUEST_ID_HEADER]
    assert "\n" not in echoed and "\r" not in echoed
    assert len(echoed) <= 64


def test_a_request_refused_at_the_perimeter_still_has_an_id(client):
    """The middleware is registered outermost precisely for this.

    A partner whose oversized upload was rejected has nothing else to quote — and an oversized
    upload is one of the likeliest things to go wrong in a first integration.
    """
    response = client.post(
        "/api/v1/padnext/audit",
        content=b"",
        headers={"Content-Length": str(64 * 1024 * 1024), "Content-Type": "application/xml"},
    )
    assert response.status_code == 413
    assert response.headers[REQUEST_ID_HEADER]


def test_the_id_is_cleared_between_requests(client):
    first = client.get("/api/v1/health").headers[REQUEST_ID_HEADER]
    second = client.get("/api/v1/health").headers[REQUEST_ID_HEADER]
    assert first != second
    assert current_request_id() == "", "nothing leaks out of the request that set it"


# ==========================================================================================
# 2. structured logging
# ==========================================================================================


def test_the_formatter_emits_one_json_object_per_line():
    record = logging.LogRecord(
        "app.test", logging.INFO, __file__, 1, "audited %s files", ("3",), None
    )
    record.duration_ms = 12.5
    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "audited 3 files"
    assert payload["duration_ms"] == 12.5
    assert payload["ts"].endswith("+00:00"), "UTC, and explicitly so"


def test_the_formatter_never_raises_on_a_value_it_cannot_serialise():
    """An error response that fails to log is worse than the error. `details` in this codebase
    routinely carries `Decimal` and `Path` straight off a domain object."""
    from decimal import Decimal
    from pathlib import Path

    record = logging.LogRecord("app.test", logging.ERROR, __file__, 1, "boom", (), None)
    record.amount = Decimal("12.34")
    record.path = Path("/srv/data")
    payload = json.loads(JsonFormatter().format(record))
    assert payload["amount"] == "12.34"
    assert payload["path"] == "/srv/data"


def test_a_request_logs_one_line_with_the_route_status_and_duration(client, logs):
    client.get("/api/v1/health")
    lines = _request_lines(logs)

    assert len(lines) == 1, "one record per request, not one per handler"
    line = lines[0]
    assert line.http_method == "GET"
    assert line.http_route == "/api/v1/health"
    assert line.http_status == 200
    assert line.duration_ms >= 0


def test_the_logged_route_is_the_template_not_the_resolved_path(client, token_and_job, logs):
    """`/audit/bulk/{job_id}`, never `/audit/bulk/batch_9f1c…`.

    A resolved path makes every job a distinct log key, which defeats the one question this field
    answers — which endpoint is slow, or failing. The job id is a field beside it.
    """
    token, job_id = token_and_job
    logs.clear()
    client.get(f"/api/v1/audit/bulk/{job_id}", headers={API_KEY_HEADER: token})

    line = _request_lines(logs)[-1]
    assert line.http_route == "/api/v1/audit/bulk/{job_id}"
    assert job_id not in line.http_route


def test_a_partner_request_names_the_key_and_the_practice(client, token_and_job):
    """What turns "an upload failed at 14:32" into "this customer's upload failed".

    Asserted by capturing what the formatter is handed mid-request, because the context is cleared
    when the request ends — which is itself the behaviour that stops one request's identity leaking
    into the next one's log lines.
    """
    from app.core.observability import _request_context

    token, job_id = token_and_job
    captured: list[dict] = []

    class Spy(logging.Handler):
        def emit(self, record):
            if record.name == "app.request":
                captured.append(dict(_request_context.get()))

    # Attached to `app.request` itself, with its own level set, rather than to the root logger.
    # pytest's logging plugin resets the root level between tests, so a root handler silently
    # receives nothing in a full run while passing when the file is run alone — which is exactly
    # the shape of a test that stops testing anything without ever going red.
    spy = Spy()
    emitter = logging.getLogger("app.request")
    previous = emitter.level
    emitter.addHandler(spy)
    emitter.setLevel(logging.INFO)
    try:
        client.get(f"/api/v1/audit/bulk/{job_id}", headers={API_KEY_HEADER: token})
    finally:
        emitter.removeHandler(spy)
        emitter.setLevel(previous)

    assert captured, "the request line was never emitted"
    context = captured[-1]
    assert context["organization_id"] == TEST_ORGANIZATION_ID
    assert context["key_id"], "the API key that made the call is named"
    assert context["job_id"] == job_id
    assert context["request_id"]


def test_the_context_reaches_a_line_logged_from_the_threadpool(client):
    """The reason this is a `ContextVar` and not a thread-local.

    Every solve and every audit is handed to `run_in_threadpool`, so if the context did not
    propagate there, the lines from the code that actually does the work — the reader, the
    Datalog run — would be the only ones with no request id on them. Those are the lines somebody
    debugging a failed audit most needs.
    """
    from app.main import app

    seen: dict[str, str] = {}
    probe = APIRouter()

    @probe.get("/_probe/threadpool")
    async def _probe() -> dict:
        def inside() -> str:
            return current_request_id()

        seen["threadpool"] = await run_in_threadpool(inside)
        seen["loop"] = current_request_id()
        return {"ok": True}

    app.include_router(probe)
    try:
        response = client.get("/_probe/threadpool")
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/_probe/threadpool"]

    assert response.status_code == 200
    assert seen["threadpool"], "a line logged inside the threadpool would carry no request id"
    assert seen["threadpool"] == seen["loop"] == response.headers[REQUEST_ID_HEADER]


def test_bind_adds_to_the_context_and_never_replaces_it(client):
    """A handler that overwrote the context would drop the request id the middleware set."""
    from app.main import app

    captured: dict = {}
    probe = APIRouter()

    @probe.get("/_probe/bind")
    async def _probe() -> dict:
        bind(organization_id="org-x")
        bind(job_id="batch_1")
        from app.core.observability import _request_context

        captured.update(_request_context.get())
        return {"ok": True}

    app.include_router(probe)
    try:
        client.get("/_probe/bind")
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/_probe/bind"]

    assert captured["organization_id"] == "org-x"
    assert captured["job_id"] == "batch_1"
    assert captured["request_id"], "the middleware's id survived two binds"


# ==========================================================================================
# 3. error tracking
# ==========================================================================================


@pytest.fixture
def exploding_client():
    """A client over a route that raises something nobody named.

    `raise_server_exceptions=False` is the whole point of this being its own fixture rather than the
    shared `client`. `TestClient` re-raises a server exception by default, which is right for a
    suite asserting on behaviour and useless here: what is being tested is the *response* an
    unhandled error produces and the row it leaves, and neither exists if the exception escapes to
    the test instead of reaching the handler.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    probe = APIRouter()

    @probe.get("/_probe/boom")
    async def _boom() -> dict:
        raise ZeroDivisionError("the engine divided by a Ziffer")

    app.include_router(probe)
    deps.reset()
    try:
        with TestClient(
            app,
            headers={ORGANIZATION_ID_HEADER: TEST_ORGANIZATION_ID},
            raise_server_exceptions=False,
        ) as test_client:
            yield test_client
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", "") != "/_probe/boom"
        ]
        deps.reset()


async def test_an_unhandled_error_is_recorded_and_the_caller_is_given_the_id(exploding_client):
    response = exploding_client.get("/_probe/boom", headers={"X-Request-ID": "req-boom-1"})

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "INTERNAL_ERROR"
    # In the body, not only the header: a support conversation starts with a screenshot, and a
    # header is invisible in one.
    assert body["details"]["request_id"] == "req-boom-1"
    assert "req-boom-1" in body["message"]
    assert body["details"]["exception"] == "ZeroDivisionError"

    async with get_database().session() as session:
        rows = (await session.execute(select(ErrorLogRecord))).scalars().all()

    assert len(rows) == 1
    row = rows[0]
    assert row.request_id == "req-boom-1"
    assert row.exception_type == "ZeroDivisionError"
    assert "divided by a Ziffer" in row.message
    assert row.http_route == "/_probe/boom"
    assert row.http_method == "GET"


async def test_the_response_never_carries_the_traceback(exploding_client):
    """An unhandled error is by definition one whose contents nobody has vetted for what they leak."""
    body = exploding_client.get("/_probe/boom").text
    assert "Traceback" not in body
    assert "_probe" not in body.replace('"/_probe/boom"', "")


async def test_a_handled_failure_is_not_recorded(client):
    """The table is a triage queue. Filling it with 422s would bury the rows that mean something."""
    refused = client.post("/api/v1/padnext/audit", content=b"<not-padnext/>")
    assert refused.status_code == 422

    async with get_database().session() as session:
        rows = (await session.execute(select(ErrorLogRecord))).scalars().all()
    assert rows == [], "only unanticipated failures are recorded"


async def test_the_registered_hook_receives_the_exception_and_its_context(exploding_client):
    """The seam a real tracker plugs into, without this repository importing one."""
    seen: list = []
    set_error_hook(lambda exc, context: seen.append((type(exc).__name__, context)))
    try:
        exploding_client.get("/_probe/boom", headers={"X-Request-ID": "req-hook-1"})
    finally:
        set_error_hook(None)

    assert len(seen) == 1
    name, context = seen[0]
    assert name == "ZeroDivisionError"
    assert context["request_id"] == "req-hook-1"
    assert context["http_route"] == "/_probe/boom"


async def test_a_raising_hook_does_not_replace_the_error_response(exploding_client):
    """It runs while the service is already failing; a second exception would lose the first."""

    def broken(exc, context):
        raise RuntimeError("the tracker is also down")

    set_error_hook(broken)
    try:
        response = exploding_client.get("/_probe/boom")
    finally:
        set_error_hook(None)

    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_ERROR"


# ==========================================================================================
# fixtures
# ==========================================================================================


@pytest.fixture
def delivery_bytes() -> bytes:
    from app.config import PADNEXT_EXAMPLES_DIR

    return (PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml").read_bytes()


@pytest.fixture
def token_and_job(client, delivery_bytes) -> tuple[str, str]:
    """A minted key and one completed bulk job, for the logging assertions."""
    import io
    import zipfile

    token = client.post(
        "/api/v1/settings/api-keys",
        json={"name": "observability"},
        headers={ORGANIZATION_ID_HEADER: TEST_ORGANIZATION_ID},
    ).json()["token"]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a_padx.xml", delivery_bytes)

    accepted = client.post(
        "/api/v1/audit/bulk",
        files={"file": ("upload.zip", buffer.getvalue(), "application/zip")},
        headers={API_KEY_HEADER: token},
    )
    assert accepted.status_code == 202, accepted.text
    return token, accepted.json()["batch_id"]
