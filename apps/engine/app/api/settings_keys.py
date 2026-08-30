"""Issue and manage the API keys the partner surface authenticates on.

Three endpoints, and the notable thing about all three is which credential *they* require:

    POST   /api/v1/settings/api-keys              mint one; the token is in the response, once
    GET    /api/v1/settings/api-keys              this practice's keys, without their secrets
    DELETE /api/v1/settings/api-keys/{key_id}     revoke one

**They are behind the session, not behind an API key**, and that is not an inconsistency with
`/api/v1/audit/*` — it is the only arrangement that can work. The first key has to be issued to
somebody who does not have one yet, so a mint endpoint gated on an API key could never issue a
first key. What guards these instead is the same boundary the approval endpoints sit behind: the
web tier resolves a Better Auth session against the database and forwards `X-Organization-ID` and
`X-User-ID` (`app.api.tenancy`, `app.api.identity`). That is a *stronger* check than a key, not a
weaker one — it is a verified session rather than a bearer secret — and it is why the engine must
not be published to the browser.

The practical consequence for a partner: keys are minted from the Azmoth web application by a
signed-in member of the practice, not by an automated caller. That is the correct shape for a
credential-issuing endpoint anyway.

**`POST` is not idempotent and is not meant to be.** Calling it twice gives two live keys, because
that is exactly what a rotation is: mint the new one, deploy it, revoke the old one. An endpoint
that returned the existing key on a second call would be an endpoint that could show a caller a
secret — which is the one thing the storage design makes impossible.

`/settings` rather than `/organizations/{id}/keys`: there is no id in the path anywhere here, and
that is deliberate. The organisation is whichever one the session is active in, so there is no path
segment a caller could edit to mint themselves a key into a practice they are not a member of.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Security, status

from app.api.apikeys import api_key_scheme
from app.api.deps import api_keys, usage
from app.api.identity import RequestActor
from app.api.tenancy import RequestOrganization, require_organization
from app.core.observability import bind
from app.db.models import as_utc
from app.errors import ApiKeyInvalid
from app.schemas.api_keys import (
    ApiKeyIssued,
    ApiKeyList,
    ApiKeyRequest,
    ApiKeyRevoked,
    ApiKeySummary,
    UsageSummary,
)
from app.services.proposal_store import ANONYMOUS_ACTOR
from app.services.usage import month_to_date

log = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.post(
    "/api-keys",
    response_model=ApiKeyIssued,
    status_code=status.HTTP_201_CREATED,
    summary="Einen neuen API-Schlüssel erzeugen",
)
async def generate_api_key(
    organization: RequestOrganization,
    actor: RequestActor,
    body: ApiKeyRequest = Body(default_factory=ApiKeyRequest),
) -> ApiKeyIssued:
    """Erzeugt einen API-Schlüssel für die aktive Praxis und gibt ihn **genau einmal** zurück.

    Der Schlüssel hat die Form `azm_live_<id>_<secret>` und wird nur als SHA-256-Hash gespeichert.
    Es gibt keinen Weg, ihn später erneut anzuzeigen — auch nicht für uns. Speichern Sie ihn sofort
    im Secret-Store Ihrer Anwendung; geht er verloren, erzeugen Sie einen neuen und widerrufen den
    alten.

    Der Schlüssel handelt ausschliesslich für die Organisation, in der die Sitzung gerade aktiv
    ist. Er kann keine andere angeben: die Organisation steckt in der Datenbankzeile, nicht in der
    Anfrage.

    Mehrfaches Aufrufen erzeugt mehrere gültige Schlüssel. Genau so wird rotiert: neuen erzeugen,
    ausrollen, alten widerrufen (`DELETE /api/v1/settings/api-keys/{key_id}`).

    ---

    Mints a key for the session's active organisation and returns the token exactly once.

    Only a SHA-256 hash is stored, so the secret cannot be shown again by anyone, including us.
    Calling this twice yields two live keys — which is how a rotation is performed.
    """
    minted = await api_keys().mint(
        organization_id=organization,
        name=body.name.strip(),
        created_by=None if actor == ANONYMOUS_ACTOR else actor,
    )
    log.info("api key %s minted for %s", minted.key_id, organization)
    return ApiKeyIssued(
        token=minted.token,
        key_id=minted.key_id,
        name=minted.name,
        organization_id=minted.organization_id,
        created_at=minted.created_at,
        created_by=None if actor == ANONYMOUS_ACTOR else actor,
    )


@router.get("/api-keys", response_model=ApiKeyList, summary="API-Schlüssel dieser Praxis")
async def list_api_keys(organization: RequestOrganization) -> ApiKeyList:
    """Alle Schlüssel dieser Praxis, neueste zuerst — **ohne** die Geheimnisse.

    Widerrufene Schlüssel bleiben in der Liste und tragen `revoked_at`. Das ist der Unterschied
    zwischen »dieser Schlüssel wurde am 3. widerrufen« und »diesen Schlüssel gab es nie«, und genau
    das ist die Frage, die jemand stellt, wenn eine Integration morgens aufhört zu funktionieren.

    `last_used_at` ist auf etwa eine Minute genau: die Spalte wird bewusst nicht bei jeder Anfrage
    geschrieben. Sie beantwortet »benutzt das noch jemand«, und das ist eine Frage über Tage.

    ---

    This practice's keys, newest first, with no secrets. Revoked keys are included and carry
    `revoked_at`; `last_used_at` is accurate to about a minute by design.
    """
    rows = await api_keys().list_keys(organization_id=organization)
    return ApiKeyList(
        keys=[
            ApiKeySummary(
                key_id=row.key_id,
                name=row.name,
                created_at=as_utc(row.created_at),
                created_by=row.created_by,
                last_used_at=as_utc(row.last_used_at),
                revoked_at=as_utc(row.revoked_at),
            )
            for row in rows
        ]
    )


@router.delete(
    "/api-keys/{key_id}",
    response_model=ApiKeyRevoked,
    summary="Einen API-Schlüssel widerrufen",
)
async def revoke_api_key(key_id: str, organization: RequestOrganization) -> ApiKeyRevoked:
    """Widerruft einen Schlüssel. Ab sofort wird jede Anfrage damit mit `401` abgelehnt.

    Die Zeile bleibt bestehen — widerrufen ist eine Spalte, kein `DELETE`. »Dieser Schlüssel war
    von März bis Juli gültig« ist eine Frage, die in einer Abrechnungsstreitigkeit gestellt wird,
    und eine gelöschte Zeile kann sie nicht beantworten.

    Idempotent: ein bereits widerrufener Schlüssel bleibt widerrufen, mit dem ursprünglichen
    Zeitpunkt. Ein Schlüssel einer anderen Praxis ergibt `404` und nicht `403` — sonst könnte man
    durch Raten feststellen, welche Schlüssel-IDs überhaupt existieren.

    ---

    Revokes a key; every request carrying it is refused with `401` from now on. The row stays and
    gains `revoked_at`. Idempotent, and a key belonging to another practice is a `404`.
    """
    if not await api_keys().revoke(key_id, organization_id=organization):
        raise HTTPException(
            status_code=404,
            detail={
                "error": "api_key_not_found",
                "message": (
                    f"Kein Schlüssel {key_id} in dieser Praxis. — No key {key_id} belongs to this "
                    "organisation."
                ),
                "key_id": key_id,
            },
        )
    return ApiKeyRevoked(key_id=key_id, revoked=True)


# ------------------------------------------------------------------------------------------
# usage
# ------------------------------------------------------------------------------------------


async def resolve_reader(
    request: Request,
    presented: Annotated[str | None, Security(api_key_scheme)] = None,
) -> str:
    """Which organisation's usage the caller may read — by API key, or by session.

    The one endpoint in this module that both kinds of caller want. A partner integrating against
    the API needs to see what they are spending without opening a browser; a practice manager needs
    to see it in the web application, where there is a session and no key.

    **The branch cannot be used to get past either check**, which is the only property that matters
    here. Presenting `X-API-Key` means it is verified and the tenant comes out of the row —
    presenting a *wrong* one is a `401`, never a silent fall-through to the header. Presenting none
    puts the request in the trusted-proxy regime every other endpoint in this service already uses,
    with the same caveat `app.api.tenancy` documents at length. There is no combination of headers
    that authenticates as one practice and reads another's.

    Ordered key-first deliberately. A partner's request carries both headers when it goes through
    our own proxy for testing, and the credential we can actually *verify* has to win.
    """
    if presented and presented.strip():
        from app.api.deps import api_keys as key_store

        key = await key_store().verify(presented.strip())
        if key is None:
            raise ApiKeyInvalid(
                "Der API-Schlüssel ist ungültig, unbekannt oder wurde widerrufen. — The API key is "
                "invalid, unknown or has been revoked.",
                details={"header": "X-API-Key"},
            )
        bind(key_id=key.key_id, organization_id=key.organization_id)
        return key.organization_id

    return require_organization(request)


#: What the usage endpoint annotates with. Deliberately *not* `RequestOrganization`: that one would
#: refuse a partner holding a perfectly good key, because a key is not the header it reads.
UsageReader = Annotated[str, Depends(resolve_reader)]


@router.get(
    "/usage",
    response_model=UsageSummary,
    summary="Verbrauch dieser Praxis",
)
async def read_usage(
    organization: UsageReader,
    since: datetime | None = Query(
        default=None,
        description=(
            "Beginn des Zeitraums, einschliesslich. ISO-8601; ohne Zeitzone als UTC gelesen. "
            "Standard: der 1. des laufenden Monats, 00:00 UTC. — Inclusive start; defaults to the "
            "first of the current month."
        ),
    ),
    until: datetime | None = Query(
        default=None,
        description="Ende des Zeitraums, einschliesslich. Standard: jetzt. — Inclusive end.",
    ),
) -> UsageSummary:
    """Wie viele Anfragen, wie viele Bytes und wie viel Rechenzeit diese Praxis verbraucht hat.

    Standardmässig der laufende Kalendermonat in UTC — der Zeitraum, den eine Rechnung abbildet.
    Der tatsächlich verwendete Zeitraum steht immer in der Antwort (`period_start`, `period_end`):
    eine Verbrauchszahl, deren Zeitraum der Leser raten muss, ist eine Zahl, die zwei Personen aus
    denselben Daten unterschiedlich berechnen.

    **Gezählt wird jede zurechenbare Anfrage, auch die fehlgeschlagenen.** Eine Integration, die
    täglich vierhundert `422` erzeugt, ist ein Problem, das man sehen will, bevor der Kunde
    abspringt — ein Bericht, der nur Erfolge zählte, würde genau diesen Kunden verbergen.

    `by_key` trennt die Integrationen voneinander; `key_id: null` sind Aufrufe aus der
    Weboberfläche selbst. `by_endpoint` zeigt, wofür der Verbrauch anfällt.

    ---

    What this practice consumed: requests, request bytes and wall-clock time, for the current
    calendar month in UTC unless `since` / `until` say otherwise. The window used is always stated
    in the response.

    Readable **either** with an API key — a partner checking their own spend — **or** from a
    signed-in session in the web application. Whichever credential is presented determines the
    organisation; there is no parameter that names one.

    Failed calls are counted and reported separately, because an integration producing errors is
    the customer most worth noticing.
    """
    # Flush before reading. Without this the endpoint tells a partner who has just made five calls
    # that they have made none — the buffer holds up to 25 rows or 15 seconds of traffic, and a
    # quiet integration reaches neither. "Zero" is the one answer a usage screen must never give
    # wrongly: it reads as "metering is broken", and the reader cannot tell that it is not.
    #
    # Safe here specifically because it happens *inside a request*: that is the same discipline
    # `app.services.usage` is built around — no background task, so no transaction interleaving on
    # SQLite's single writer. It costs one batched INSERT on an endpoint nobody polls.
    from app.api.deps import usage_meter

    await usage_meter().flush()

    start, end = month_to_date()
    return UsageSummary.model_validate(
        await usage().summarise(
            organization_id=organization,
            since=since or start,
            until=until or end,
        )
    )
