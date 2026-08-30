"""Reject oversized request bodies at the perimeter.

The problem this solves. `POST /api/v1/padnext/audit` declares `body: bytes`, and FastAPI buffers the
ENTIRE body before the handler runs — so the 32 MiB check inside `app.padnext.reader` fires only
*after* the memory has already been allocated. On an endpoint that needs no authentication, a single
oversized POST was enough to exhaust the process.

This middleware runs before the body is read, so a request that advertises more than the limit is
refused having cost nothing but a header parse.

**Per-path overrides.** One global ceiling stopped being expressible once the bulk endpoint
existed: `POST /api/v1/audit/bulk` legitimately takes a 50 MB archive, which is above the 32 MiB
that is right for everything else, and raising the global limit to suit it would hand every other
endpoint — including the unauthenticated single-file audit — a bigger body to buffer. So the
middleware takes a list of `(path prefix, limit)` pairs, longest prefix wins, and everything not
named keeps the global default. The overrides are set once, in `app.main`, from the same settings
the endpoints themselves enforce their own limits with, so the perimeter and the handler cannot
come to disagree about a number.

The per-endpoint checks stay regardless. This one screens on `Content-Length`; the handler's check
is what actually holds when there is no such header, and it is also the one that can produce a
useful `error_code` naming the specific limit that was hit.

KNOWN LIMITATION, stated rather than papered over: this checks `Content-Length`. A client that omits
it (chunked transfer encoding) cannot be pre-screened this way, and such a request still reaches the
in-handler check — which is why that check stays in place as defence in depth rather than being
replaced. Closing that hole properly means counting bytes as they stream, which is a larger change
than this one and is not what a demo needs.
"""

from __future__ import annotations

from collections.abc import Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.errors import ErrorCode, error_envelope


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """413 for any request whose declared body size exceeds the limit for its path.

    Builds its responses with `error_envelope` rather than raising an `EngineError`: middleware
    runs outside the exception handlers, so raising here would surface as an unhandled 500. The
    bodies are byte-identical to what the handlers produce — the `error`/`max_bytes` keys the
    existing tests read are still there, alongside the new `error_code` and `details`.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        overrides: Sequence[tuple[str, int]] = (),
    ) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes
        # Sorted longest-first so `limit_for` can return on the first match. Done once here rather
        # than per request, because the list is fixed at startup and a sort per request would be a
        # cost paid on every call to serve a configuration that never changes.
        self.overrides = sorted(overrides, key=lambda pair: len(pair[0]), reverse=True)

    def limit_for(self, path: str) -> int:
        """The ceiling that applies to this path. Longest matching prefix, else the global one."""
        for prefix, limit in self.overrides:
            if path.startswith(prefix):
                return limit
        return self.max_bytes

    async def dispatch(self, request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared is not None:
            limit = self.limit_for(request.url.path)
            try:
                length = int(declared)
            except ValueError:
                # A malformed Content-Length is not something to guess about.
                return JSONResponse(
                    status_code=400,
                    content=error_envelope(
                        error_code=ErrorCode.MALFORMED_CONTENT_LENGTH,
                        message=f"Content-Length is not an integer: {declared!r}",
                        details={"content_length": declared},
                        http_status=400,
                    ),
                )
            if length > limit:
                return JSONResponse(
                    status_code=413,
                    content=error_envelope(
                        error_code=ErrorCode.REQUEST_TOO_LARGE,
                        message=(
                            f"Request body is {length} bytes; this API accepts at most "
                            f"{limit}. Rejected before reading the body."
                        ),
                        details={"declared_bytes": length, "max_bytes": limit},
                        http_status=413,
                    ),
                )
        return await call_next(request)
