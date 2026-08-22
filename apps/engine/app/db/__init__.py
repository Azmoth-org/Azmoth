"""Persistence.

Proposals and the audit log are the only state this service keeps. Everything else — the catalog,
the rule tables, the logic programs — is read-only input, and the result cache is content-addressed
and disposable. So this package is small on purpose: two tables, one session factory, and a
repository (`app.services.proposal_store`) that is the only thing above it allowed to hold a
`Session`.

Why a database at all, when `proposal_store` used to argue against one: an approval that dies with
the process cannot be shown to a Rechnungsprüfer, and "who approved this, and when" is the one
question a billing system must always be able to answer. The retention and access-control questions
that argument raised are still open — see `docs/compliance/PRIVATE_DATA_WARNING.md` — but they are
now open *above* a durable record rather than instead of one.
"""

from app.db.base import Base
from app.db.models import AuditEvent, AuditEventType, ProposalRecord
from app.db.session import (
    Database,
    SchemaNotMigrated,
    get_database,
    init_models,
    reset_database,
    set_database,
)

__all__ = [
    "AuditEvent",
    "AuditEventType",
    "Base",
    "Database",
    "ProposalRecord",
    "SchemaNotMigrated",
    "get_database",
    "init_models",
    "reset_database",
    "set_database",
]
