"""Every failure this engine can hand a caller, in one place.

Three things live here and nothing else: the **codes** (`ErrorCode`), the **envelope** every error
response is rendered into (`ErrorResponse`), and the **base exception** that carries both
(`EngineError`). The specific exceptions stay in the modules they belong to — `PadnextSchemaError`
beside the reader that raises it, `ClingoTimeout` beside the solver — and inherit from a base here
so that one handler can render all of them. Centralising the *catalog* without centralising the
*raising* is deliberate: an exception defined three imports away from its trigger goes stale.

**The envelope.** Four fields carry the contract:

    {
      "error_code": "SOLVER_TIMEOUT",       # stable, machine-readable, SCREAMING_SNAKE
      "message":    "…",                    # human-readable, and the only field that may change
      "details":    {...},                  # machine-readable specifics: line numbers, codes, …
      "retry_after": 5                      # seconds, only when retrying could plausibly work
    }

Two more fields are emitted for compatibility and are not new contract: `error` is the lowercase
spelling that the web client's `toReviewError` already reads, and `detail` mirrors the whole thing
because FastAPI puts error bodies there and every existing client and test unwraps it. They are
duplication, and the duplication is the cheapest way to add a contract without breaking the one
that shipped. See `docs/errors.md`.

**`retry_after` means something specific.** It is present only on failures where the *same request*
sent again later could succeed — the database was briefly unreachable, the rules engine could not
be started. It is absent from every deterministic failure: a malformed XML document does not become
well formed by being sent again, and a client that retried it would be hammering the service to get
the same 400. That distinction is also what `app.core.retry` keys on.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    """The complete catalog. Every value here has a row in `docs/errors.md`.

    Adding one is a contract change: a client may switch on these strings, so a code is renamed
    only with the same care as renaming a response field. `tests/test_error_handling.py` asserts
    that the enum and the documentation table stay in step, so a new code that nobody wrote a row
    for fails the suite rather than shipping undocumented.
    """

    # -- the client sent something the engine cannot use ---------------------------------------
    INVALID_XML = "INVALID_XML"
    EMPTY_REQUEST_BODY = "EMPTY_REQUEST_BODY"
    MALFORMED_CONTENT_LENGTH = "MALFORMED_CONTENT_LENGTH"
    REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PADNEXT_UNREADABLE = "PADNEXT_UNREADABLE"
    PADNEXT_SCHEMA_VIOLATION = "PADNEXT_SCHEMA_VIOLATION"
    UNKNOWN_ZIFFER = "UNKNOWN_ZIFFER"
    REAL_DATA_REFUSED = "REAL_DATA_REFUSED"
    ECHTDATEN_UNDECLARED = "ECHTDATEN_UNDECLARED"
    UNSUPPORTED_INPUT_FORMAT = "UNSUPPORTED_INPUT_FORMAT"

    # -- the client may not do this ------------------------------------------------------------
    ORGANIZATION_REQUIRED = "ORGANIZATION_REQUIRED"
    API_KEY_REQUIRED = "API_KEY_REQUIRED"
    API_KEY_INVALID = "API_KEY_INVALID"

    # -- the client is doing it too often ------------------------------------------------------
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # -- the client asked for something that is not there --------------------------------------
    CATALOG_NOT_FOUND = "CATALOG_NOT_FOUND"

    # -- the engine could not answer -----------------------------------------------------------
    SOLVER_TIMEOUT = "SOLVER_TIMEOUT"
    SOLVER_FAILED = "SOLVER_FAILED"
    ENGINE_VALIDATION_DISAGREEMENT = "ENGINE_VALIDATION_DISAGREEMENT"

    # -- transient: the same request may succeed later -----------------------------------------
    RULES_ENGINE_UNAVAILABLE = "RULES_ENGINE_UNAVAILABLE"
    TRANSIENT_DB_FAILURE = "TRANSIENT_DB_FAILURE"

    #: The last resort, for an exception nobody in this codebase named. In the enum so that a
    #: client switching on `error_code` has a complete set to switch on — including the case it
    #: most needs a default branch for.
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: Default `Retry-After`, in seconds, for the two transient failures.
#:
#: Short, because both are usually a restarting dependency rather than a queue: a Postgres failover
#: completes in single-digit seconds, and a Soufflé binary that is missing will still be missing in
#: an hour — for that one the header is a courtesy, not a promise. A client that honours it backs
#: off; a client that ignores it gets the same 503.
DEFAULT_RETRY_AFTER_SECONDS = 5


class ErrorResponse(BaseModel):
    """The body of every non-2xx response this API produces.

    Declared as a model so it appears in the OpenAPI document and the generated TypeScript, rather
    than being an undocumented dict that clients discover by hitting it in production.
    """

    error_code: str = Field(description="Stable machine-readable code. See docs/errors.md.")
    message: str = Field(description="Human-readable. May change; do not switch on it.")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Specifics a client can act on: line and column, unknown Ziffern, partials.",
    )
    retry_after: int | None = Field(
        default=None,
        description=(
            "Seconds to wait before retrying the identical request. Present only when retrying "
            "could plausibly succeed; also sent as the `Retry-After` header."
        ),
    )
    error: str = Field(
        description="Lowercase spelling of `error_code`, for clients written before it existed."
    )
    status: int = Field(
        description="The HTTP status, repeated in the body so a logged payload is self-contained."
    )
    detail: Any = Field(
        default=None,
        description=(
            "Compatibility mirror, where FastAPI clients already look. Usually an object holding "
            "the same four fields; on a `VALIDATION_ERROR` it is Pydantic's own list of field "
            "errors, and on an error raised by a route as `HTTPException` it is whatever that "
            "route passed. Read the top-level fields instead — this one is deliberately untyped "
            "because it reproduces what shipped."
        ),
    )


class EngineError(Exception):
    """Base for every failure that has a place in the catalog.

    Subclasses set `error_code`, `http_status` and — only where retrying makes sense —
    `retry_after`. They may also inherit from a domain base at the same time
    (`ClingoTimeout(ClingoError, SolverTimeoutError)`), which is the whole reason this is a plain
    `Exception` with class attributes rather than a framework type: it has to be mixable into
    hierarchies that already exist without disturbing what already catches them.
    """

    error_code: ErrorCode = ErrorCode.SOLVER_FAILED
    http_status: int = 500
    retry_after: int | None = None

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details or {})
        if retry_after is not None:
            self.retry_after = retry_after

    def envelope(self) -> dict[str, Any]:
        return error_envelope(
            error_code=self.error_code,
            message=self.message,
            details=self.details,
            retry_after=self.retry_after,
            http_status=self.http_status,
        )


def error_envelope(
    *,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retry_after: int | None = None,
    http_status: int,
) -> dict[str, Any]:
    """Build the response body. The one place its shape is decided.

    `details` is passed through `to_jsonable` because it routinely carries `Decimal` amounts and
    `Path` objects straight off a domain object, and an error response that itself fails to
    serialise turns a 422 a client could have fixed into a 500 nobody can.
    """
    from app.core.canonical import to_jsonable

    body: dict[str, Any] = {
        "error_code": str(error_code),
        "message": message,
        "details": to_jsonable(dict(details or {})),
        "retry_after": retry_after,
        "error": str(error_code).lower(),
        "status": http_status,
    }
    # The mirror, minus itself. Clients that already read `detail` see the same four fields; the
    # top level is where new clients should read.
    body["detail"] = {k: v for k, v in body.items() if k != "detail"}
    return body


# ==============================================================================================
# the specific failures that have no better home
# ==============================================================================================
#
# Everything below is raised from more than one place, or from a place that must not import the
# module it would otherwise live in. Failures with exactly one raiser stay next to it — see
# `app.padnext.reader.InvalidXmlError`, `app.solvers.clingo_solver.ClingoTimeout`,
# `app.catalog.catalog_loader.CatalogNotFoundError`.


class EmptyRequestBody(EngineError):
    """A body-taking endpoint got no body. `400`, because nothing about it is processable.

    Its own code rather than a generic 400: an empty POST is almost always a client that built the
    request wrong — a fetch with the file in the wrong field, a proxy that dropped the body — and
    naming it saves the caller from looking for a problem in a file that never arrived.
    """

    error_code = ErrorCode.EMPTY_REQUEST_BODY
    http_status = 400


class OrganizationRequired(EngineError):
    """The request did not say which organisation it acts for. `403`, and there is no default.

    Raised by `app.api.tenancy.require_organization` for every endpoint that reads or writes a
    proposal or a batch. `403` rather than `401` because the engine authenticates nobody and is not
    claiming the caller failed to: the request is well-formed and simply does not state a tenant,
    which is not something a credential would fix.

    Not retryable in the `Retry-After` sense — the identical request fails identically — so no
    `retry_after` is set. What fixes it is the header.
    """

    error_code = ErrorCode.ORGANIZATION_REQUIRED
    http_status = 403


class UnknownZifferError(EngineError):
    """The request names GOÄ positions the loaded catalog does not contain.

    422 rather than 404: the request is well formed and the resource exists, but the engine cannot
    process the entity it was given. `details.unknown_ziffern` is the full list, so a client fixes
    every one of them in a single round trip instead of discovering them one at a time, and
    `details.catalog_version` is there because the usual cause is not a typo — it is a delivery
    coded against a different edition of the fee schedule.
    """

    error_code = ErrorCode.UNKNOWN_ZIFFER
    http_status = 422

    def __init__(
        self,
        message: str,
        *,
        unknown_ziffern: list[str],
        catalog_version: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            details={
                "unknown_ziffern": sorted(set(unknown_ziffern)),
                "unknown_count": len(set(unknown_ziffern)),
                "catalog_version": catalog_version,
                **(details or {}),
            },
        )
        self.unknown_ziffern = sorted(set(unknown_ziffern))


class UnsupportedInputFormat(EngineError):
    """The caller sent something that is not PADnext XML. `400`, named rather than generic.

    The commercial API takes one input format and it is worth being blunt about which: a PVS
    integration that posts a PDF, a JSON body, or a bare ZIP to `/audit/single` is not going to
    work out what happened from a schema violation three layers down. So the format is sniffed at
    the edge — magic bytes and the first non-whitespace character, never the filename, which a
    client controls and routinely gets wrong — and refused with the format it *looks* like named
    in `details.detected`.

    `400` rather than `415 Unsupported Media Type`: 415 is about the `Content-Type` header, and the
    header is not what was wrong. A caller who declares `application/xml` and sends a PDF has sent
    a bad *body*, and answering 415 would send them editing a header that was correct.
    """

    error_code = ErrorCode.UNSUPPORTED_INPUT_FORMAT
    http_status = 400


class ApiKeyRequired(EngineError):
    """No `X-API-Key` on a request to the partner API. `401`.

    `401`, and note the contrast with `ORGANIZATION_REQUIRED`, which is a `403` for what looks like
    a similar refusal. The difference is real: the tenancy header is not a credential and the engine
    cannot check one, so a `401` there would invite a client to retry with proof this service has no
    way to verify. An API key *is* a credential, this endpoint *does* verify it, and a caller who
    presents none has failed to authenticate — which is what `401` means.

    A `WWW-Authenticate` header is deliberately not sent. The scheme is a bare header, not one of
    the ones that header names, and advertising `Bearer` would send a client down an OAuth path
    that does not exist here.
    """

    error_code = ErrorCode.API_KEY_REQUIRED
    http_status = 401


class ApiKeyInvalid(EngineError):
    """The key does not resolve, or has been revoked. `401`.

    Deliberately one exception for three different facts — no such key, a hash that does not match,
    a key that was revoked — because the response must not distinguish them. A caller who could tell
    "this key is unknown" from "this key was revoked" could enumerate which prefixes have ever been
    issued, and a caller who could tell either from "the secret is wrong" could confirm a `key_id`
    without holding its token. `details` carries nothing for the same reason.

    The *message* does mention revocation, because the overwhelmingly likely reader is a partner
    whose integration stopped working this morning, and "check whether this key was revoked" is the
    sentence that saves them a support ticket. It says it as a possibility, not as a finding about
    the key they sent.
    """

    error_code = ErrorCode.API_KEY_INVALID
    http_status = 401


class RateLimitExceeded(EngineError):
    """The key has spent its budget for this window. `429`, with a `Retry-After`.

    Retryable, and the one failure here where `retry_after` is a genuine promise rather than a
    hint: the window is a fixed length and the limiter knows exactly when it rolls over, so the
    value is computed from that instant rather than defaulted. See `app.api.ratelimit`.
    """

    error_code = ErrorCode.RATE_LIMIT_EXCEEDED
    http_status = 429

    def __init__(
        self,
        message: str,
        *,
        limit: int,
        window_seconds: int,
        retry_after: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            details={
                "limit": limit,
                "window_seconds": window_seconds,
                **(details or {}),
            },
            retry_after=retry_after,
        )
        self.limit = limit
        self.window_seconds = window_seconds


class SolverTimeoutError(EngineError):
    """The optimiser hit its hard ceiling before there was anything to return.

    504 rather than 500: the engine did not fail, it ran out of the time it was allowed. The
    distinction matters to a caller deciding whether to retry — this one may succeed with a longer
    ceiling or a smaller case, where a 500 will not.

    Note what this is *not*. A solve that is cut short but has already found a model returns a
    normal 200 whose `solver_status` is `TIMEOUT_PARTIAL`, with every hard rule still enforced and
    a warning saying optimality was not proved. This exception is the other case — the ceiling
    expired with no answer set at all — and it exists so that "nothing was computable in time" can
    never be served as "nothing is chargeable".
    """

    error_code = ErrorCode.SOLVER_TIMEOUT
    http_status = 504


class TransientDatabaseError(EngineError):
    """The database was unreachable, and retrying it did not help.

    Raised by `app.core.retry` once the attempts are spent — never on the first failure, because a
    connection dropped by a failover is exactly what the retries are for. Reaching a client means
    the outage outlasted the backoff window, so `retry_after` is the honest answer rather than a
    500 that says "engine bug".
    """

    error_code = ErrorCode.TRANSIENT_DB_FAILURE
    http_status = 503
    retry_after = DEFAULT_RETRY_AFTER_SECONDS


class RulesEngineUnavailable(EngineError):
    """Soufflé could not be run, so no audit or solve can be answered.

    503 with a `Retry-After`: it is an engine-side failure rather than a fault in the request, and
    the two common causes — the binary is missing, or the process could not be started under
    memory pressure — differ in whether waiting helps. The header covers the second; the message
    names the first so nobody waits for a binary to appear on its own.
    """

    error_code = ErrorCode.RULES_ENGINE_UNAVAILABLE
    http_status = 503
    retry_after = DEFAULT_RETRY_AFTER_SECONDS


class EngineValidationDisagreement(EngineError):
    """The independent validation pass contradicted the solver. Never returned as an invoice.

    500, and deliberately so: this is a defect in the engine, not in the input, and a status that
    blamed the caller would send them editing a case that was fine. The violations travel in
    `details` because they are what a bug report needs.
    """

    error_code = ErrorCode.ENGINE_VALIDATION_DISAGREEMENT
    http_status = 500


__all__ = [
    "DEFAULT_RETRY_AFTER_SECONDS",
    "ApiKeyInvalid",
    "ApiKeyRequired",
    "EmptyRequestBody",
    "EngineError",
    "EngineValidationDisagreement",
    "ErrorCode",
    "ErrorResponse",
    "RateLimitExceeded",
    "RulesEngineUnavailable",
    "SolverTimeoutError",
    "TransientDatabaseError",
    "UnknownZifferError",
    "UnsupportedInputFormat",
    "error_envelope",
]
