"""One place where an exception becomes an HTTP response.

Registered on the app in `app.main`. Four handlers, and between them every non-2xx body this
service produces has the same four fields — `error_code`, `message`, `details`, `retry_after` —
whether it came from a structured `EngineError`, from a route that raises `HTTPException` with the
older `{"error": …}` dict, or from FastAPI's own request validation.

**Why handlers rather than `try/except` in every route.** The previous arrangement mapped
exceptions to statuses inside each path function, which meant the mapping was correct only where
somebody had remembered to write it: an exception raised one frame deeper than the `try` — from a
dependency, from a background task's re-entry, from a helper added later — fell through to a bare
500. A handler catches it wherever it is raised, and the status now travels *on the exception*, so
the route no longer has to know that a Soufflé failure is a 503.

**What is not centralised.** Routes still raise `HTTPException` for the things that are genuinely
about the HTTP resource rather than about the engine — a proposal id that does not exist, a status
transition that is not allowed. Those keep their shape and gain the envelope through
`http_exception_handler`, which is the compatibility half of this module: no existing client or
test has to change to read the new fields.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.core.observability import record_exception
from app.errors import EngineError, ErrorCode, error_envelope

log = logging.getLogger(__name__)


def _json(status_code: int, body: dict[str, Any], *, retry_after: int | None = None) -> JSONResponse:
    """The response, plus the `Retry-After` header when the body advertises one.

    Both, not one: the header is what an HTTP client, a proxy or a load balancer already knows how
    to honour without being taught this API, and the field is what a browser reading JSON can act
    on. A body that said "retry in 5" while the headers said nothing would be a promise only our
    own client could keep.

    Everything goes through `jsonable_encoder` on the way out. `error_envelope` already handles the
    types the engine puts in `details`, but Pydantic's own validation errors carry the original
    exception object under `ctx`, and an error response that cannot serialise itself turns a 422
    the caller could have fixed into a 500 nobody can.
    """
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(
        status_code=status_code, content=jsonable_encoder(body), headers=headers
    )


async def engine_error_handler(_request: Request, exc: EngineError) -> JSONResponse:
    """Anything in the catalog: the status, code and details all come off the exception."""
    if exc.http_status >= 500:
        # A 5xx is ours. Logged with the traceback because nobody else is going to see it — the
        # client gets a message and a code, never a stack.
        log.exception("engine error %s: %s", exc.error_code, exc)
    else:
        log.info("engine error %s: %s", exc.error_code, exc)
    return _json(exc.http_status, exc.envelope(), retry_after=exc.retry_after)


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """`HTTPException` — including every route that predates the error catalog.

    Three shapes reach this, and all three leave with the envelope:

    * `detail={"error": "proposal_not_found", "message": …, …}` — the convention the proposal,
      batch and rules routes already use. The `error` value becomes the `error_code` upper-cased,
      and every other key it carries is preserved in `details`, so a client reading
      `current_status` off an illegal-transition 409 still finds it.
    * `detail="some string"` — the message, with no details.
    * anything else (a list, from a nested validation error) — kept whole under `details.detail`.

    `detail` itself is re-emitted unchanged, which is the point: this handler adds fields, it never
    takes one away.
    """
    detail = exc.detail
    extra_headers = dict(getattr(exc, "headers", None) or {})

    if isinstance(detail, dict):
        legacy_code = str(detail.get("error") or f"HTTP_{exc.status_code}")
        message = str(detail.get("message") or legacy_code.replace("_", " "))
        details = {k: v for k, v in detail.items() if k not in {"error", "message"}}
    elif isinstance(detail, str):
        legacy_code = f"HTTP_{exc.status_code}"
        message = detail
        details = {}
    else:
        legacy_code = f"HTTP_{exc.status_code}"
        message = f"HTTP {exc.status_code}"
        details = {"detail": detail}

    body = error_envelope(
        error_code=legacy_code.upper(),
        message=message,
        details=details,
        retry_after=None,
        http_status=exc.status_code,
    )
    # Preserve exactly what the route said, not a reconstruction of it. A test or a client that
    # reads `detail["current_status"]` must keep reading the same value.
    body["detail"] = detail if detail is not None else body["detail"]

    response = _json(exc.status_code, body)
    for name, value in extra_headers.items():
        response.headers[name] = value
    return response


async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """FastAPI's own 422, given a code and left otherwise intact.

    `details.errors` is Pydantic's error list verbatim — the field path, the failing value and the
    reason, which is the only thing that lets a caller fix a rejected extraction without guessing.
    `detail` keeps the bare list, because that is where every client written against FastAPI looks
    and this migration does not move it.
    """
    errors = exc.errors()
    body = error_envelope(
        error_code=ErrorCode.VALIDATION_ERROR,
        message=(
            f"Die Anfrage entspricht nicht dem Schema ({len(errors)} "
            f"{'Verstoß' if len(errors) == 1 else 'Verstöße'}). Details unter details.errors."
        ),
        details={"errors": errors, "error_count": len(errors)},
        retry_after=None,
        http_status=422,
    )
    body["detail"] = errors
    return _json(422, body)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """The last resort: an exception nobody in this codebase named.

    It exists so that the *shape* of an error response is unconditional — a client can parse
    `error_code` from any failure, including the ones we did not anticipate. The message is
    deliberately generic and the exception type is the only detail carried: an unhandled error is
    by definition one whose contents nobody has vetted for what they might leak.

    **It is also the only writer of `error_log`.** A handled failure — a `422` for a malformed
    delivery, a `503` for a missing Soufflé — is the error contract working, and recording those
    would fill the table with noise and bury the rows that mean something is broken. Reaching here
    means the engine did something nobody anticipated, which is exactly the set worth keeping.

    **The request id goes in the body.** Not as decoration: it is the whole reason a user saying
    "the upload didn't work" is answerable. They quote `details.request_id`, and it joins their
    failure to the `error_log` row and to every log line the request produced. Emitting it here and
    not only in the header is deliberate — a header is invisible to somebody reading a screenshot
    of an error, and a screenshot is what a support conversation actually starts with.
    """
    log.exception("unhandled error: %s", exc)
    request_id = await record_exception(exc, request=request)
    return _json(
        500,
        error_envelope(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=(
                "Die Engine hat einen unerwarteten Fehler ausgelöst. Der Vorgang wurde nicht "
                "abgeschlossen. Bitte nennen Sie bei einer Rückfrage die Vorgangsnummer "
                f"{request_id or '(nicht verfügbar)'}. — An unexpected error occurred; quote the "
                "request id when reporting it."
            ),
            details={"exception": type(exc).__name__, "request_id": request_id},
            retry_after=None,
            http_status=500,
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Wire all four onto the app. Called once, from `app.main`."""
    app.add_exception_handler(EngineError, engine_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)


__all__ = [
    "engine_error_handler",
    "http_exception_handler",
    "register_error_handlers",
    "unhandled_error_handler",
    "validation_error_handler",
]
