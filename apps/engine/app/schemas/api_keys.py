"""The wire shapes for issuing and managing a partner's API keys.

Three models, and the interesting one is the asymmetry between the first two. `ApiKeyIssued`
carries the token; `ApiKeySummary`, which every later read returns, cannot — the row holds a hash
and there is nothing to put in such a field. That is not an omission to be tidied up later: it is
the storage decision made visible in the contract, so a client generated from the OpenAPI document
has no `token` property to go looking for on a listing and no reason to build a UI that promises to
show one.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: The longest a caller-supplied label may be. Matches `api_keys.name`, which is `String(128)`.
MAX_KEY_NAME_LENGTH = 128


class ApiKeyRequest(BaseModel):
    """What a caller sends to mint a key: a label, and nothing else.

    Nothing else, deliberately. Not the organisation — that comes from the session the web tier
    already verified, and a body field naming a tenant would be an endpoint for issuing yourself a
    credential to somebody else's data. Not an expiry either: an expiring key that nothing renews
    is an integration that breaks at 3 a.m. for a reason nobody remembers, and rotation is a thing
    to do deliberately (mint, deploy, revoke) rather than a thing to schedule and forget.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        default="",
        max_length=MAX_KEY_NAME_LENGTH,
        description=(
            "Bezeichnung des Schlüssels, z. B. 'PVS-Export nächtlich' oder "
            "'Rechnungszentrum Süd'. Frei wählbar und der einzige Anhaltspunkt, um später zu "
            "erkennen, wozu ein Schlüssel gehört — das Geheimnis selbst ist nicht mehr "
            "einsehbar. — A human label. The secret is never shown again, so this is the only "
            "way to tell two keys apart."
        ),
    )


class ApiKeySummary(BaseModel):
    """One key as it can be read back: everything about it except the secret.

    `revoked_at` is present rather than the row being filtered out of a listing, because "this key
    was revoked on the 3rd" and "this key never existed" are different answers to the question an
    operator is asking when an integration stops working.
    """

    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(
        description=(
            "Die öffentliche Hälfte des Schlüssels. Erscheint in Logs, im Ratenlimit und ist der "
            "Wert, mit dem ein Schlüssel widerrufen wird. — The public half: what a log line "
            "names, what the rate limit counts, and what you pass to revoke this key."
        )
    )
    name: str = ""
    created_at: datetime
    created_by: str | None = Field(
        default=None,
        description="Better Auth user id of whoever minted it, where the request carried one.",
    )
    last_used_at: datetime | None = Field(
        default=None,
        description=(
            "Letzte erfolgreiche Verwendung, auf etwa eine Minute genau — die Spalte wird "
            "absichtlich nicht bei jeder Anfrage geschrieben. `null` bedeutet: nie benutzt. — "
            "Last successful use, accurate to about a minute; `null` means never used."
        ),
    )
    revoked_at: datetime | None = Field(
        default=None,
        description="Non-null means every request carrying this key is refused with a 401.",
    )

    @property
    def active(self) -> bool:
        return self.revoked_at is None


class ApiKeyIssued(ApiKeySummary):
    """A freshly minted key. **The only response that will ever carry the token.**

    It extends `ApiKeySummary` rather than being a separate shape so that a client can treat the
    creation response as a listing row with one extra field, which is what it is.
    """

    model_config = ConfigDict(extra="forbid")

    token: str = Field(
        description=(
            "Der vollständige API-Schlüssel, im Format `azm_live_<id>_<secret>`. **Er wird genau "
            "einmal angezeigt und ist danach nicht wiederherstellbar** — gespeichert wird nur "
            "sein SHA-256-Hash. Bewahren Sie ihn sofort im Secret-Store Ihrer Anwendung auf; "
            "geht er verloren, erzeugen Sie einen neuen und widerrufen den alten. — The complete "
            "key. Shown exactly once and unrecoverable afterwards: only its SHA-256 hash is "
            "stored. Save it now."
        )
    )

    organization_id: str = Field(
        description=(
            "Die Organisation, für die dieser Schlüssel handelt. Jede Anfrage mit ihm sieht "
            "ausschließlich deren Daten. — The organisation this key acts for. Every request made "
            "with it reaches that practice's data and no other."
        )
    )


class ApiKeyList(BaseModel):
    """This practice's keys, newest first.

    No `total`, `limit` or `offset`, unlike the proposal and batch listings. A practice has a
    handful of keys — the number is bounded by how many integrations it has, not by how long it has
    been a customer — so a page would be a ceremony over a list that fits on a screen. If that ever
    stops being true, adding the envelope is a change; adding it now would be a guess.
    """

    model_config = ConfigDict(extra="forbid")

    keys: list[ApiKeySummary] = Field(default_factory=list)


class ApiKeyRevoked(BaseModel):
    """The answer to a revocation: which key, and when it stopped working."""

    model_config = ConfigDict(extra="forbid")

    key_id: str
    revoked: bool = True


__all__ = [
    "MAX_KEY_NAME_LENGTH",
    "ApiKeyIssued",
    "ApiKeyList",
    "ApiKeyRequest",
    "ApiKeyRevoked",
    "ApiKeySummary",
]
