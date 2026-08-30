"""Issue, verify and revoke the credentials the partner API authenticates on.

One token, one practice. `POST /api/v1/audit/*` reads `X-API-Key`, this module turns it into an
`organization_id`, and every query downstream filters on that id — so a billing centre integrating
against the engine reaches its own uploads and nothing else. The substitution is the security
property: the tenant is *derived from the credential*, never taken from a header the caller writes.

**The token shape**

    azm_live_ab12cd34ef56_9f4c…                (70 characters, fixed width)
    └───┬───┘└────┬─────┘ └──┬──┘
      prefix    key_id     secret
                (12 hex)   (48 hex, 192 bits)

`key_id` is stored in the clear and `key_hash` is SHA-256 over the **whole** token. Splitting the
token this way is what makes verification one indexed read: look the `key_id` up, hash what was
sent, compare. Without a public half, every request would have to hash the candidate against every
row in the table — which is `O(keys)` per call and gets slower as the product succeeds.

The secret is 192 bits of `secrets.token_bytes`. There is no `azm_test_` counterpart, deliberately:
a test key that behaves differently from a live one is a second code path through an authentication
check, and the way to test against this engine is to point at a deployment holding synthetic data,
which is what `PADNEXT_ALLOW_REAL_DATA=false` already enforces everywhere.

**Nothing here can show a caller their key.** `mint` returns the token once, in memory, to the
endpoint that will put it in one response body. After that it exists only in the caller's keeping:
the row holds a hash, and a hash is not reversible. "I lost my key" therefore resolves to "mint
another and revoke the old one", which is the honest answer and also the safe one.

**Plain SHA-256, not bcrypt or Argon2, and that is not a shortcut.** A password KDF exists to make
each guess expensive because human-chosen passwords come from a small space. This secret is 192
random bits: there is no space to search, so the work factor would buy nothing and cost every
authenticated request the same tens of milliseconds. What *is* required — and is here — is a
constant-time comparison, so the hash check cannot be turned into an oracle by timing it.

**Revocation is a column.** A revoked key keeps its row with `revoked_at` set; `verify` refuses it.
"This key was live from March to July and these jobs ran under it" is a question a billing dispute
asks, and a deleted row cannot answer it.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.models import ApiKeyRecord, as_utc, utcnow
from app.db.session import Database, get_database

log = logging.getLogger(__name__)

#: What every token starts with. `live` and not an environment marker the caller can vary — see the
#: module docstring on why there is no test variant.
KEY_PREFIX = "azm_live_"

#: Widths, in hex characters. Fixed so a token can be split without a regex and validated by length
#: before a database is touched at all.
KEY_ID_HEX = 12
SECRET_HEX = 48

#: `azm_live_` + 12 + `_` + 48.
TOKEN_LENGTH = len(KEY_PREFIX) + KEY_ID_HEX + 1 + SECRET_HEX

#: How stale `last_used_at` may get before a successful verification bothers to update it.
#:
#: The column answers "is anything still using this key", which is a question about days. Writing it
#: on every request would put an UPDATE in front of every audit — at the rate limit's own ceiling
#: that is 100 extra writes a minute per key, to record a fact that changes nothing. One write a
#: minute is exact enough for what it is for and costs nothing.
LAST_USED_RESOLUTION = timedelta(minutes=1)


@dataclass(frozen=True)
class MintedKey:
    """A newly issued key: the token, and the row that will outlive it.

    `token` is the only place the secret ever exists. It is returned to exactly one caller, put in
    exactly one response body, and never written down — which is why this is a frozen dataclass
    handed straight to the route rather than something with a `save()` that might be tempted to.
    """

    token: str
    key_id: str
    name: str
    organization_id: str
    created_at: datetime


@dataclass(frozen=True)
class AuthenticatedKey:
    """What a verified request carries: which key, and whose data it may touch.

    Deliberately not the ORM row. Nothing outside this module should hold `key_hash`, and a
    detached SQLAlchemy object crossing a request boundary is how a lazy load ends up in a
    dependency. `organization_id` here is the value every downstream query filters on.
    """

    key_id: str
    organization_id: str
    name: str


def _hash(token: str) -> str:
    """SHA-256 over the whole token, hex. The only hashing in this module."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> tuple[str, str]:
    """A fresh `(token, key_id)`.

    `secrets`, not `random`: the module-level Mersenne Twister is seeded from state an attacker can
    sometimes reconstruct, and a credential generated from it is a credential that can be predicted.
    """
    key_id = secrets.token_hex(KEY_ID_HEX // 2)
    secret = secrets.token_hex(SECRET_HEX // 2)
    return f"{KEY_PREFIX}{key_id}_{secret}", key_id


def split_token(token: str) -> str | None:
    """The `key_id` inside a token, or `None` if it is not shaped like one at all.

    Checked before any query runs, so a caller sending a session cookie, a JWT or an empty string
    costs a string comparison rather than a database round trip. It is a *shape* check and not a
    validity check: a well-formed token for a key that does not exist gets past here and is refused
    by `verify`, which is the only place that can tell.
    """
    if len(token) != TOKEN_LENGTH or not token.startswith(KEY_PREFIX):
        return None
    body = token[len(KEY_PREFIX) :]
    key_id, separator, secret = body.partition("_")
    if separator != "_" or len(key_id) != KEY_ID_HEX or len(secret) != SECRET_HEX:
        return None
    if not all(character in "0123456789abcdef" for character in key_id + secret):
        return None
    return key_id


class ApiKeyStore:
    """Every read and write against `api_keys`.

    A store rather than free functions for the same reason `ProposalStore` is one: the database is
    injectable, so a test can drive it against its own engine without touching the process-wide
    singleton. It holds no connection of its own — `get_database()` is asked per call — so the
    instance is safe to keep for the life of the process.
    """

    def __init__(self, database: Database | None = None) -> None:
        self._database = database

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    async def mint(
        self, *, organization_id: str, name: str, created_by: str | None = None
    ) -> MintedKey:
        """Issue a key for one organisation and return the token exactly once.

        The collision retry is not superstition about randomness — 48 bits of `key_id` will not
        collide in this lifetime — it is about the `unique=True` index being the thing that decides.
        A second attempt costs one statement and turns an astronomically unlikely `IntegrityError`
        on somebody's onboarding into a non-event.
        """
        for attempt in range(3):
            token, key_id = generate_token()
            created_at = utcnow()
            record = ApiKeyRecord(
                key_id=key_id,
                key_hash=_hash(token),
                organization_id=organization_id,
                name=name,
                created_by=created_by,
                created_at=created_at,
            )
            async with self.database.session() as session:
                existing = await session.execute(
                    select(ApiKeyRecord.id).where(ApiKeyRecord.key_id == key_id)
                )
                if existing.scalar_one_or_none() is not None:  # pragma: no cover - see docstring
                    log.warning("api key id %s collided on attempt %d; regenerating", key_id, attempt)
                    continue
                session.add(record)

            log.info(
                "api key %s issued to organisation %s by %s", key_id, organization_id, created_by
            )
            return MintedKey(
                token=token,
                key_id=key_id,
                name=name,
                organization_id=organization_id,
                created_at=as_utc(created_at),
            )

        raise RuntimeError(  # pragma: no cover - unreachable with 48 bits of key_id
            "could not generate a unique api key id in three attempts; something is wrong with "
            "the entropy source"
        )

    async def verify(self, token: str) -> AuthenticatedKey | None:
        """Resolve a token to the practice it acts for, or `None`.

        `None` covers every way a token can fail — malformed, unknown, wrong secret, revoked — and
        the caller must not be told which. Distinguishing them would let somebody enumerate issued
        prefixes, or confirm a `key_id` without holding its secret. `app.errors.ApiKeyInvalid` says
        the same thing from the HTTP side.

        The comparison is `hmac.compare_digest` rather than `==`. Both operands are hex digests of
        the same length, so the timing signal is small — but it is a signal, it is free to remove,
        and "small enough not to matter" is a judgement that ages badly.
        """
        key_id = split_token(token)
        if key_id is None:
            return None

        candidate = _hash(token)
        now = utcnow()

        async with self.database.session() as session:
            record = (
                await session.execute(
                    select(ApiKeyRecord).where(ApiKeyRecord.key_id == key_id)
                )
            ).scalar_one_or_none()

            if record is None or record.revoked_at is not None:
                return None
            if not hmac.compare_digest(record.key_hash, candidate):
                # A well-formed token whose secret is wrong for a key that exists. Worth a log line
                # — it is the shape a brute-force attempt has — and worth being terse: the token
                # itself never reaches a log, only the prefix that is public anyway.
                log.warning("api key %s presented with a wrong secret", key_id)
                return None

            # Throttled, per `LAST_USED_RESOLUTION`. Written inside the same session so a verified
            # request costs one round trip rather than two.
            previous = as_utc(record.last_used_at)
            if previous is None or now - previous >= LAST_USED_RESOLUTION:
                record.last_used_at = now

            return AuthenticatedKey(
                key_id=record.key_id,
                organization_id=record.organization_id,
                name=record.name,
            )

    async def list_keys(self, *, organization_id: str) -> list[ApiKeyRecord]:
        """This practice's keys, newest first, including the revoked ones.

        Revoked rows are included and not filtered out, because the listing is the only place an
        operator can see that a key *was* revoked and when — hiding them would make a revocation
        indistinguishable from a key that never existed.

        Returns detached rows: the session is closed before they are read. That is safe here and
        only here, because every column is loaded eagerly (there is no relationship on this table)
        and the caller only projects them onto a response model.
        """
        async with self.database.session() as session:
            rows = (
                await session.execute(
                    select(ApiKeyRecord)
                    .where(ApiKeyRecord.organization_id == organization_id)
                    .order_by(ApiKeyRecord.created_at.desc())
                )
            ).scalars().all()
            session.expunge_all()
            return list(rows)

    async def revoke(self, key_id: str, *, organization_id: str) -> bool:
        """Refuse every future request carrying this key. `False` if there is no such key here.

        Scoped to the organisation, so one practice cannot revoke another's credential by guessing
        a `key_id` — and the miss is reported as "no such key" rather than "not yours", for the same
        reason `load_batch` answers `404` across a tenant boundary.

        Idempotent: revoking an already-revoked key succeeds and leaves the original `revoked_at`
        alone. The caller asked for a state, and it holds.
        """
        async with self.database.session() as session:
            record = (
                await session.execute(
                    select(ApiKeyRecord).where(
                        ApiKeyRecord.key_id == key_id,
                        ApiKeyRecord.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            if record is None:
                return False
            if record.revoked_at is None:
                record.revoked_at = utcnow()
                log.info("api key %s revoked for organisation %s", key_id, organization_id)
            return True


__all__ = [
    "KEY_ID_HEX",
    "KEY_PREFIX",
    "LAST_USED_RESOLUTION",
    "SECRET_HEX",
    "TOKEN_LENGTH",
    "ApiKeyStore",
    "AuthenticatedKey",
    "MintedKey",
    "generate_token",
    "split_token",
]
