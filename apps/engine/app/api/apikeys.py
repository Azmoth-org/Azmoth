"""The credential the partner API authenticates on, and the tenant it resolves to.

This is the third of the three "who is this request for" modules, and the only one that *checks*
anything:

    app/api/identity.py    X-User-ID           who — asserted, recorded, never required
    app/api/tenancy.py     X-Organization-ID   whose — asserted by a trusted proxy, required
    app/api/apikeys.py     X-API-Key           whose — **verified**, required, and the tenant
                                               comes out of the database rather than the request

The difference matters and is the whole reason this module exists. `tenancy.py` is honest that its
header is asserted, not proven: it works because the engine is not published to the browser and the
Next.js proxy is its only caller. That deployment shape is exactly what a commercial API breaks — a
PVS vendor's integration reaches the engine directly, from a network we do not control, and a
caller who can name any organisation they like would be able to read any practice's uploads.

So `/api/v1/audit/*` does not read `X-Organization-ID` at all. It reads a key, resolves it against
`api_keys`, and takes `organization_id` **from the row**. A caller cannot choose their tenant
because the request has no field in which to say one.

**What still requires the proxy headers, and why.** Minting a key does
(`POST /api/v1/settings/api-keys`), because the alternative is a chicken and egg: the first key has
to be issued to a caller who does not have one yet. That endpoint is reached by a signed-in human
through the web tier, under a Better Auth session the proxy has already verified against the
database — which is a stronger check than an API key, not a weaker one. It is the same boundary the
approval endpoints sit behind.

**Errors are deliberately uninformative.** Missing is `401 API_KEY_REQUIRED`; anything else —
malformed, unknown, wrong secret, revoked — is one indistinguishable `401 API_KEY_INVALID`. See
`app.errors.ApiKeyInvalid` for why the three cannot be told apart without handing out an
enumeration oracle.

**The header is declared through `APIKeyHeader`**, unlike the two proxy headers, which are read off
the raw request specifically to keep them out of the OpenAPI document. Here the opposite is wanted:
`X-API-Key` is published contract, it belongs in the document a partner generates a client from,
and it is what puts the **Authorize** button on `/docs`. `auto_error=False` because Starlette's own
403-with-a-string does not carry the error envelope; the refusal is raised here instead.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from app.core.observability import bind
from app.errors import ApiKeyInvalid, ApiKeyRequired
from app.services.api_keys import AuthenticatedKey

log = logging.getLogger(__name__)

#: What a partner sends. Must match the `X-API-Key` in `docs/api/PARTNER_API.md` and in whatever
#: client a vendor generates from the OpenAPI document.
API_KEY_HEADER = "X-API-Key"

api_key_scheme = APIKeyHeader(
    name=API_KEY_HEADER,
    auto_error=False,
    scheme_name="AzmothApiKey",
    description=(
        "Der API-Schlüssel der Praxis bzw. des Rechnungszentrums, im Format "
        "`azm_live_<id>_<secret>`. Er bestimmt zugleich die Organisation, deren Daten die Anfrage "
        "sehen darf — es gibt keinen Header, mit dem ein Aufrufer eine andere Organisation "
        "angeben könnte.\n\n"
        "The practice's API key. It also determines which organisation's data the request may "
        "reach; there is no header with which a caller could name a different one. Mint one with "
        "`POST /api/v1/settings/api-keys` from a signed-in session."
    ),
)


async def require_api_key(
    presented: Annotated[str | None, Security(api_key_scheme)],
) -> AuthenticatedKey:
    """Verify `X-API-Key` and return the key it resolved to, or refuse with a `401`.

    `async def` because the verification is a database read. It runs on every partner request, so
    it is one indexed lookup by `key_id` and one constant-time hash comparison — see
    `app.services.api_keys.ApiKeyStore.verify` for why the token is split the way it is.

    The store is fetched through `app.api.deps` rather than constructed here, so the process holds
    one instance and a test that swaps the database swaps it for everything at once.
    """
    from app.api.deps import api_keys

    if not presented or not presented.strip():
        raise ApiKeyRequired(
            "Diese Schnittstelle benötigt einen API-Schlüssel. Senden Sie ihn im Header "
            f"{API_KEY_HEADER}. Einen Schlüssel erzeugt POST /api/v1/settings/api-keys. — This "
            f"endpoint requires an API key in the {API_KEY_HEADER} header.",
            details={"header": API_KEY_HEADER},
        )

    key = await api_keys().verify(presented.strip())
    if key is not None:
        # Bound here, at the one point every partner request passes through, rather than in each
        # route. From now on every log line the request emits — including ones from the reader and
        # the solver, which know nothing about HTTP — carries who made it and for which practice.
        # That is what turns "an upload failed at 14:32" into "this customer's upload failed".
        bind(key_id=key.key_id, organization_id=key.organization_id)
    if key is None:
        raise ApiKeyInvalid(
            "Der API-Schlüssel ist ungültig, unbekannt oder wurde widerrufen. Prüfen Sie, ob er "
            "noch aktiv ist (GET /api/v1/settings/api-keys), und erzeugen Sie andernfalls einen "
            "neuen. — The API key is invalid, unknown or has been revoked.",
            details={"header": API_KEY_HEADER},
        )
    return key


async def require_api_key_organization(
    key: Annotated[AuthenticatedKey, Depends(require_api_key)],
) -> str:
    """Just the organisation, for the endpoints that need nothing else about the caller.

    A separate dependency rather than `key.organization_id` at each call site, because FastAPI
    caches a dependency per request: a path function that wants both the tenant and the key id gets
    one verification, not two.
    """
    return key.organization_id


#: What a partner endpoint annotates with when it needs to know *which* key — the rate limiter and
#: the attribution written onto a job.
RequestApiKey = Annotated[AuthenticatedKey, Depends(require_api_key)]

#: And when it only needs the tenancy filter. Interchangeable with `RequestOrganization` at the
#: call site by design, so a service takes `organization_id: str` and does not know or care which
#: of the two boundaries produced it.
ApiKeyOrganization = Annotated[str, Depends(require_api_key_organization)]


__all__ = [
    "API_KEY_HEADER",
    "ApiKeyOrganization",
    "RequestApiKey",
    "api_key_scheme",
    "require_api_key",
    "require_api_key_organization",
]
