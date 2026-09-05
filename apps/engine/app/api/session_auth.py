"""Verifies the Better Auth session token the web proxy attaches to `POST …/rules/{rule_id}/review`.

`app.api.identity` says at length that the engine authenticates nobody: `X-User-ID` is asserted by
the Next.js proxy and never checked, and what makes that safe is the deployment shape — the engine
is not published to the browser, and the proxy is its only caller. That module also names the next
step, for the day that boundary needs reinforcing: "a Better Auth JWT the engine verifies itself…
`requireIdentity` is where it goes."

This is that seam, applied to the one endpoint where trusting the network alone is worth
narrowing: a verdict here changes what every subsequent audit enforces platform-wide, for every
practice, immediately (`app.api.rules` re-merges the rule store before answering). `POST
/api/v1/rules/{rule_id}/review` is the write; `GET /rules/review-queue` and `GET /rules/coverage`
are reads and stay on the existing model.

## What travels, and what is checked

`apps/web/lib/auth.ts` mints a short-lived (2-minute) JWT with Better Auth's `jwt()` plugin the
moment a request needs to reach the engine — EdDSA-signed with a key the plugin manages and rotates,
`iss`/`aud` fixed to this pair of services rather than derived from a per-deployment origin.
`apps/web/lib/engine.ts` attaches it as `Authorization: Bearer <token>` beside the existing
`X-User-ID` and `X-Organization-ID`.

This module fetches the plugin's public JWKS (`GET {AUTH_JWKS_URL}` — a public key, so the request
carries no credential of its own), verifies the signature against the key named by the token's
`kid`, and checks `iss`, `aud` and `exp`. Anything else — no header, an unknown `kid`, a bad
signature, an expired or mismatched claim — is one indistinguishable `401`, for the reason
`app.errors.ApiKeyInvalid` gives for doing the same thing with a partner's API key: telling the
failures apart would hand a forger an oracle for which part to fix next.

The JWKS is cached in-process (`AUTH_JWKS_CACHE_SECONDS`, default 300s) because this dependency runs
on a write endpoint a reviewer calls interactively, and fetching the web tier's keys on every single
review would be one more request in that loop for a key that essentially never changes.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any

import httpx
import jwt as pyjwt
from fastapi import Depends, Request

from app.config import get_settings
from app.errors import SessionTokenInvalid, SessionTokenRequired

log = logging.getLogger(__name__)

#: What `apps/web/lib/engine.ts` sends. A real credential, unlike the two headers beside it, which
#: is why it travels as `Authorization` rather than a house header like `X-User-ID`.
AUTHORIZATION_HEADER = "authorization"

_INVALID_TOKEN_MESSAGE = (
    "Das Sitzungs-Token ist ungültig oder abgelaufen. Bitte laden Sie die Seite neu und "
    "versuchen Sie es erneut. — The session token is invalid or has expired. Reload the page "
    "and try again."
)


class _JwksCache:
    """The most recently fetched JWKS, keyed by `kid`.

    A module-level singleton rather than a per-request fetch or a per-request client-side cache
    object: the point is exactly that repeated calls into this process share one fetch, the same
    reason `app.api.deps` keeps one `ApiKeyStore` rather than one per request.
    """

    def __init__(self) -> None:
        self.fetched_at: float = 0.0
        self.keys_by_kid: dict[str, dict[str, Any]] = {}

    def is_stale(self, ttl_seconds: int) -> bool:
        return time.monotonic() - self.fetched_at > ttl_seconds


_cache = _JwksCache()


async def _fetch_jwks(jwks_url: str) -> dict[str, dict[str, Any]]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        body = response.json()
    return {key["kid"]: key for key in body.get("keys", []) if "kid" in key}


async def _signing_key(kid: str) -> dict[str, Any] | None:
    """The JWK for `kid`, refetching the set when it is stale or the key is not in it yet.

    A fetch failure does not raise: it leaves whatever was cached in place (possibly nothing) and
    logs, so a momentary blip in reaching the web tier degrades to "this one token cannot be
    verified right now" rather than taking the whole engine process's logging down with it.
    """
    settings = get_settings()
    if kid not in _cache.keys_by_kid or _cache.is_stale(settings.auth_jwks_cache_seconds):
        try:
            _cache.keys_by_kid = await _fetch_jwks(settings.auth_jwks_url)
            _cache.fetched_at = time.monotonic()
        except httpx.HTTPError as exc:
            log.warning("could not fetch JWKS from %s: %s", settings.auth_jwks_url, exc)
    return _cache.keys_by_kid.get(kid)


async def require_verified_session(request: Request) -> str:
    """The Better Auth user id (`sub`) of a verified, unexpired session token, or a `401`.

    `async def` because verifying a token this engine has not seen the `kid` for yet is a network
    call (the JWKS fetch); every other case resolves from the in-process cache and is pure CPU.
    """
    header = request.headers.get(AUTHORIZATION_HEADER, "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise SessionTokenRequired(
            "Diese Aktion verändert die plattformweite Regeldurchsetzung und benötigt eine "
            "gültige Sitzung. Senden Sie ein Bearer-Token im Authorization-Header. — This action "
            "changes platform-wide rule enforcement and requires a valid session, sent as a "
            "bearer token in the Authorization header.",
            details={"header": "Authorization"},
        )
    token = token.strip()

    try:
        unverified_header = pyjwt.get_unverified_header(token)
    except pyjwt.PyJWTError as exc:
        raise SessionTokenInvalid(_INVALID_TOKEN_MESSAGE) from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise SessionTokenInvalid(_INVALID_TOKEN_MESSAGE)

    jwk_dict = await _signing_key(kid)
    if jwk_dict is None:
        raise SessionTokenInvalid(_INVALID_TOKEN_MESSAGE)

    settings = get_settings()
    try:
        signing_key = pyjwt.PyJWK.from_dict(jwk_dict).key
        payload = pyjwt.decode(
            token,
            key=signing_key,
            algorithms=[jwk_dict.get("alg", "EdDSA")],
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
        )
    except pyjwt.PyJWTError as exc:
        raise SessionTokenInvalid(_INVALID_TOKEN_MESSAGE) from exc

    sub = payload.get("sub")
    if not sub:
        raise SessionTokenInvalid(_INVALID_TOKEN_MESSAGE)
    return sub


#: What `POST /rules/{rule_id}/review` annotates with — the verified caller's Better Auth user id.
VerifiedSession = Annotated[str, Depends(require_verified_session)]


__all__ = [
    "AUTHORIZATION_HEADER",
    "VerifiedSession",
    "require_verified_session",
]
