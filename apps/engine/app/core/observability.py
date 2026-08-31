"""Structured logs, a request id on every line, and one place a 5xx is recorded.

The problem this solves is not tidiness. Until now the engine logged with `logging.basicConfig` and
a `%(levelname)s %(name)s: %(message)s` format, which is readable by a developer watching a terminal
and close to useless for anything else. A pilot user says "the upload didn't work"; there is no id
to search on, no way to join their failed request to the four log lines it produced, and no record
of the exception beyond a traceback in whatever container is still running. That is the difference
between a support conversation that takes ten minutes and one that cannot be had at all.

Three pieces, and each is stdlib:

``JsonFormatter``
    One JSON object per line: timestamp, level, logger, message, plus whatever the call site
    attached and whatever the request context carries. Machine-readable so `jq`, Loki, CloudWatch
    or a `grep` all work on it, and human-readable enough at a pinch. `LOG_FORMAT=text` keeps the
    old formatter for local work — the default is JSON, because production is where a log is read
    by something other than a person.

``RequestContextMiddleware``
    Takes or mints a request id, puts it in a `ContextVar`, echoes it in `X-Request-ID`, and logs
    one line per request when it finishes. Because it is a `ContextVar` and not a parameter, *every*
    log line emitted anywhere under that request carries the id without a single call site changing
    — including the ones inside the solver and the reader, which know nothing about HTTP.

It also carries one hook that is not about logging at all: the same `finally` that writes the
request line hands the request to `app.services.usage`, because that is the single point every
request passes through with its duration, its status and its resolved tenant all in scope. See
`_meter`.

``record_exception``
    The single seam an error tracker attaches to. It writes an `error_log` row and, if a Sentry-like
    hook is registered, calls it. No `sentry-sdk` dependency: the hook is a function this module
    stores, so `SENTRY_DSN` can be wired up in a deployment without the engine importing anything.

**Why the request id is minted here and not by a proxy.** It takes an inbound `X-Request-ID` when
one is present — a front proxy or the Next.js tier can supply one and the two tiers' logs then join
— and mints one otherwise, because a partner calling the API directly has no proxy in front of them
and their failure is exactly the one that has to be traceable.

**What is deliberately not logged.** No request bodies, no filenames from uploads, no header
values other than the ones named below. This service handles billing data about identifiable
treatment; a log is the easiest place in a system to leak it, and a log that has to be redacted
later is one nobody can share with the person debugging.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

log = logging.getLogger(__name__)

#: The header carrying the id, in and out. The conventional spelling; a proxy that already sets one
#: is honoured rather than overridden.
REQUEST_ID_HEADER = "X-Request-ID"

#: How much of an inbound id is trusted. It reaches a log line and a response header, so it is
#: length-capped and stripped of anything unprintable for the same reason `app.api.identity` does
#: it to a user id — an id with a newline in it forges log entries.
MAX_REQUEST_ID_LENGTH = 64

#: Read-only stand-in for "no request is being handled". Never mutated — `bind` replaces it with a
#: fresh dict rather than writing into it, so nothing can accumulate on the module-level default.
_NO_REQUEST: dict[str, Any] = {}

#: Per-request facts, set by the middleware and read by the formatter.
#:
#: A `ContextVar` rather than a logging filter with thread-local state, because the engine runs
#: async path functions *and* hands blocking work to a threadpool. `contextvars` propagate into
#: `run_in_threadpool` (anyio copies the context), so a line logged from inside a Soufflé call
#: still carries the request that caused it. Thread-locals do not.
#:
#: **It holds one mutable dict per request, and the mutability is load-bearing.** Starlette's
#: `BaseHTTPMiddleware` runs the rest of the app in a child task, which gets a *copy* of the
#: context — so a downstream `_request_context.set(...)` would be invisible to the middleware that
#: has to log the line at the end. Both halves of that matter: a `bind(key_id=…)` in a dependency
#: has to reach the middleware's request line, and the request id has to reach a handler running
#: outside the middleware. A copied context shares the *same dict object*, so mutating it is seen
#: in both directions where rebinding the variable is seen in neither.
_request_context: ContextVar[dict[str, Any]] = ContextVar("request_context", default=_NO_REQUEST)

#: Keys that `LogRecord` defines itself. Anything else a call site passes through `extra=` is
#: application data and is merged into the JSON object.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"asctime", "message", "taskName"}


def current_request_id() -> str:
    """The id of the request being handled, or `""` outside one."""
    return _request_context.get().get("request_id", "")


def bind(**values: Any) -> None:
    """Attach facts to the current request, so every later log line carries them.

    Used where a fact becomes known partway through — the API key after authentication, the job id
    after a batch is created. Deliberately additive and never clearing: a handler that overwrote the
    context would drop the request id set by the middleware.

    **Mutates the dict rather than rebinding the variable**, so the facts reach the middleware's
    request line even though that middleware is running in a parent task with its own copy of the
    context. See `_request_context`. Outside a request it rebinds instead, which is the one case
    where there is no shared dict to write into and nothing upstream to inform.
    """
    usable = {key: value for key, value in values.items() if value is not None}
    if not usable:
        return
    context = _request_context.get()
    if context is _NO_REQUEST:
        _request_context.set(dict(usable))
        return
    context.update(usable)


def record_invoices(count: int) -> None:
    """Declare how many PADnext deliveries the request in flight actually audited.

    The one number on a usage row that a handler has to supply, because it is the only one the
    middleware cannot observe: a status code, a duration and a byte count are properties of the HTTP
    exchange, and "this was 300 invoices" is a property of what the engine did inside it.

    It goes through the request context rather than a return value or a response header, for the same
    reason the tenant does. `_meter` runs in the middleware's `finally` — one place, on the way out,
    with everything in scope — and the alternative is a per-endpoint hook, which is a list somebody
    forgets to add to. The failure mode of forgetting is a customer's usage silently under-counted,
    which is the worst shape a billing bug can have: it looks like nothing is wrong.

    **Additive across calls.** A handler that audits in two stages calls this twice and the row
    carries the sum, because `bind` overwrites and a billable count must not. Zero and negative are
    ignored — there is no such thing as auditing minus one delivery, and a `0` would only overwrite
    a real figure with nothing.
    """
    if count <= 0:
        return
    context = _request_context.get()
    if context is _NO_REQUEST:
        bind(invoices_processed=count)
        return
    context["invoices_processed"] = int(context.get("invoices_processed") or 0) + count


class JsonFormatter(logging.Formatter):
    """One JSON object per line.

    `default=str` on the dump is doing real work: `details` dictionaries in this codebase routinely
    carry `Decimal` and `Path`, and a formatter that raised while formatting an error would lose the
    error *and* the reason it could not be logged.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_request_context.get())
        payload.update(
            {key: value for key, value in record.__dict__.items() if key not in _RESERVED}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """The old format, plus the request id. For a developer watching a terminal.

    Kept rather than dropped because JSON is genuinely worse to read while iterating, and a format
    somebody turns off in frustration is one that is off when it is needed.
    """

    def __init__(self) -> None:
        super().__init__(fmt="%(levelname)s %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        request_id = current_request_id()
        return f"[{request_id[:8]}] {rendered}" if request_id else rendered


def configure_logging(*, debug: bool = False, json_logs: bool = True) -> None:
    """Install the formatter on the root handler. Called once, from `app.main`.

    Replaces the handler rather than adding one: `logging.basicConfig` may already have run (an
    import-time `log.info` anywhere would do it), and a second handler means every line twice.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if json_logs else TextFormatter())
    root.addHandler(handler)

    # Uvicorn installs its own handlers and its access log duplicates what
    # `RequestContextMiddleware` records — with none of the context. Silence the access logger and
    # let the middleware's line be the one record of a request; keep `uvicorn.error`, which is where
    # startup and shutdown problems appear.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


def _sanitise(raw: str | None) -> str:
    if not raw:
        return ""
    cleaned = "".join(character for character in raw if character.isprintable()).strip()
    return cleaned[:MAX_REQUEST_ID_LENGTH]


def route_template(request: Request) -> str:
    """`/api/v1/audit/bulk/{job_id}` — the path with its parameters put back as placeholders.

    The template and not the resolved path, because the question this field answers is "which
    endpoint is slow, or failing", and a resolved path makes every job a distinct value. The job id
    is a field beside it (`bind(job_id=…)`), where it can be searched for on its own.

    **Rebuilt from `url.path` and `path_params` rather than read off `scope["route"]`.** The obvious
    implementation — `request.scope["route"].path` — is wrong here in a way that is easy to miss:
    FastAPI resolves a router included with a prefix to the *inner* route object, whose `.path` is
    relative to that router. Every endpoint in this service is mounted under `/api/v1`, so it
    reported `/health` for `/api/v1/health`, silently collapsing the prefix out of every log line.

    Whole segments only. A segment is templated when it equals a parameter's value exactly, so a
    literal path element that happens to look like an id is left alone.
    """
    path = request.url.path
    params = request.scope.get("path_params") or {}
    if not params:
        return path
    placeholder = {str(value): "{" + name + "}" for name, value in params.items()}
    return "/".join(placeholder.get(segment, segment) for segment in path.split("/"))


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Mint or adopt a request id, expose it, and log one line per completed request.

    The line it logs is the only per-request record the service keeps, so it carries what a support
    question actually needs: which route, which status, how long, and — once
    `app.api.apikeys` has bound them — which API key and which organisation.

    Registered **outermost**, so the id exists before the size limiter can refuse a request: a
    partner whose 60 MB upload was rejected still has an id to quote.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = _sanitise(request.headers.get(REQUEST_ID_HEADER)) or uuid.uuid4().hex
        # A fresh dict per request. Everything downstream writes into *this* object, which is why
        # `bind` mutates rather than rebinds, and why nothing leaks from one request to the next.
        _request_context.set({"request_id": request_id})
        # And on the request itself, because `ServerErrorMiddleware` — which renders an unhandled
        # exception — is installed *outside* every user middleware by Starlette, so it can run
        # after this one has returned. `request.state` survives that; a context variable may not.
        request.state.request_id = request_id

        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            route = route_template(request)
            logging.getLogger("app.request").info(
                "%s %s -> %s",
                request.method,
                route,
                status,
                extra={
                    "http_method": request.method,
                    "http_route": route,
                    "http_status": status,
                    "duration_ms": duration_ms,
                },
            )
            await _meter(request, route=route, status=status, duration_ms=duration_ms)


async def _meter(request: Request, *, route: str, status: int, duration_ms: float) -> None:
    """Hand one finished request to the usage meter, if it can be attributed to a practice.

    Called from the same `finally` that writes the request line, and for the same reason: this is
    the one place every request passes through with its duration, its status and the tenant the
    dependencies resolved all in scope at once. A decorator per endpoint would be a list somebody
    forgets to add to, and the failure would be a customer's usage silently under-counted.

    **No tenant, no row.** An unauthenticated `401`, or a `413` refused at the perimeter before any
    dependency ran, has nobody to attribute usage to — and a usage table with unattributable rows is
    one whose totals nobody can reconcile. Those requests are still in the logs.

    Only `/api/v1/*`. The OpenAPI document, `/docs` and the health probe are not consumption.

    `invoices_processed` is the exception to "the middleware knows everything it needs": it is the
    billable unit, and only the handler knows it. `record_invoices` puts it in the context and this
    reads it out. A request that audited nothing contributes `0`, not a null.

    `bytes_processed` comes from `Content-Length`, which is what the caller declared rather than what
    arrived. The two differ only for a request that was cut off — which the status code already
    records — and reading the real figure would mean counting bytes through the body stream of every
    request to improve a billing input by nothing.

    **Nothing that happens in here may reach the client.** This runs in the middleware's `finally`,
    after the handler has produced an answer, so an exception escaping would turn a successful audit
    into a `500` over a bookkeeping row — and would additionally be recorded as an unhandled engine
    error, which is a lie about what failed. `UsageMeter.record` guards itself as well; this guard
    is the one that holds when the failure is *reaching* the meter rather than inside it, which is
    the case a swallow inside `record` cannot cover.
    """
    try:
        context = _request_context.get()
        organization_id = context.get("organization_id")
        if not organization_id or not route.startswith("/api/v1/"):
            return

        try:
            declared = int(request.headers.get("content-length") or 0)
        except ValueError:
            declared = 0

        from app.api.deps import usage_meter

        await usage_meter().record(
            organization_id=str(organization_id),
            api_key_id=context.get("key_id"),
            endpoint=route,
            status_code=status,
            duration_ms=duration_ms,
            bytes_processed=declared,
            # The billable unit, put here by whichever handler knew it — see `record_invoices`.
            # Absent for every request that audited nothing, which is most of them.
            invoices_processed=int(context.get("invoices_processed") or 0),
        )
    except Exception:  # noqa: BLE001 - see docstring; a caller is never punished for our accounting
        log.exception("could not meter %s %s; the request itself was unaffected", route, status)


# ==============================================================================================
# error tracking
# ==============================================================================================

#: What a deployment registers to forward 5xx exceptions somewhere. `sentry_sdk.capture_exception`
#: is the obvious argument; anything taking `(exception, context)` works.
#:
#: A hook rather than a dependency, so that adding Sentry is a deployment decision and not an import
#: in this repository. `requirements.txt` pins everything for receipt-hash reasons, and a tracker
#: the engine imports is a package whose version has to be justified against that.
_error_hook: Callable[[BaseException, dict[str, Any]], None] | None = None


def set_error_hook(hook: Callable[[BaseException, dict[str, Any]], None] | None) -> None:
    """Register (or clear) the tracker. Called from a deployment's own startup, or from a test."""
    global _error_hook
    _error_hook = hook


async def record_exception(exc: BaseException, *, request: Request | None = None) -> str:
    """Persist one unhandled failure and forward it. Returns the request id to quote at the caller.

    **Never raises.** It runs inside the last-resort exception handler, so an error here would
    replace a legible 500 with a stack trace from the framework — losing both the original failure
    and the record of it. Each half is guarded separately, because a database that is down is
    exactly when the tracker matters most and vice versa.

    What is stored is deliberately thin: the exception type, its message, the route and the request
    id. Not the body, not the headers, not the traceback's local variables. A row that a support
    engineer can act on without any of those is a row that can be read by whoever is on call rather
    than only by someone cleared for patient data.
    """
    # `request.state` first: this can run from `ServerErrorMiddleware`, which Starlette installs
    # outside every user middleware, so the context variable may already belong to nothing.
    from_state = getattr(getattr(request, "state", None), "request_id", "") if request else ""
    request_id = from_state or current_request_id()
    context: dict[str, Any] = {**_request_context.get(), "request_id": request_id}
    if request is not None:
        context.setdefault("http_method", request.method)
        context.setdefault("http_route", route_template(request))

    try:
        from app.services.error_log import ErrorLogStore

        await ErrorLogStore().record(exc, context=context)
    except Exception:  # noqa: BLE001 - see docstring
        log.exception("could not persist the error record for request %s", request_id)

    if _error_hook is not None:
        try:
            _error_hook(exc, context)
        except Exception:  # noqa: BLE001 - see docstring
            log.exception("the registered error hook raised")

    return request_id


__all__ = [
    "MAX_REQUEST_ID_LENGTH",
    "REQUEST_ID_HEADER",
    "JsonFormatter",
    "RequestContextMiddleware",
    "TextFormatter",
    "bind",
    "configure_logging",
    "route_template",
    "current_request_id",
    "record_exception",
    "set_error_hook",
]
