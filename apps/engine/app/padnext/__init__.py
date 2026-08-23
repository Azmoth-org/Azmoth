"""PADnext ingestion: read a delivery from a practice or PVS and audit it against the GOÄ rules.

`reader` parses. `audit` checks. Neither trusts the file's own pricing, and neither reads patient
identity — see the module docstrings for why. The models live in `app.schemas.padnext`, with every
other contract the engine speaks.
"""

from app.padnext.audit import RealDataRefused, audit_delivery, real_data_allowed
from app.padnext.reader import (
    PadnextError,
    PadnextSchemaError,
    read_delivery,
    read_file,
)
from app.padnext.schema import SchemaUnavailable, SchemaViolation, validate_payload
from app.schemas.padnext import (
    PadnextAuditedPosition,
    PadnextAuditReport,
    PadnextDelivery,
    PadnextFinding,
    PadnextPosition,
)

__all__ = [
    "PadnextAuditReport",
    "PadnextAuditedPosition",
    "PadnextDelivery",
    "PadnextError",
    "PadnextFinding",
    "PadnextPosition",
    "PadnextSchemaError",
    "RealDataRefused",
    "SchemaUnavailable",
    "SchemaViolation",
    "audit_delivery",
    "read_delivery",
    "read_file",
    "real_data_allowed",
    "validate_payload",
]
