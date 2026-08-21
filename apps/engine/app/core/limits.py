"""Reject oversized request bodies at the perimeter.

The problem this solves. `POST /api/v1/padnext/audit` declares `body: bytes`, and FastAPI buffers the
ENTIRE body before the handler runs — so the 32 MiB check inside `app.padnext.reader` fires only
*after* the memory has already been allocated. On an endpoint that needs no authentication, a single
oversized POST was enough to exhaust the process.

This middleware runs before the body is read, so a request that advertises more than the limit is
refused having cost nothing but a header parse.

KNOWN LIMITATION, stated rather than papered over: this checks `Content-Length`. A client that omits
it (chunked transfer encoding) cannot be pre-screened this way, and such a request still reaches the
in-handler check — which is why that check stays in place as defence in depth rather than being
replaced. Closing that hole properly means counting bytes as they stream, which is a larger change
than this one and is not what a demo needs.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """413 for any request whose declared body size exceeds `max_bytes`."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                length = int(declared)
            except ValueError:
                # A malformed Content-Length is not something to guess about.
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "malformed_content_length",
                        "message": f"Content-Length is not an integer: {declared!r}",
                    },
                )
            if length > self.max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "request_too_large",
                        "message": (
                            f"Request body is {length} bytes; this API accepts at most "
                            f"{self.max_bytes}. Rejected before reading the body."
                        ),
                        "max_bytes": self.max_bytes,
                    },
                )
        return await call_next(request)
