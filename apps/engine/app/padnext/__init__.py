"""PADnext ingestion: read a delivery from a practice or PVS and audit it against the GOÄ rules.

`reader` parses. `validation` collects every reason a delivery cannot be read, so a practice
fixing an export sees all of them at once instead of one per upload. `audit` checks. None of them
trusts the file's own pricing, and none reads patient identity — see the module docstrings for
why. The models live in `app.schemas.padnext`, with every other contract the engine speaks.
"""

from app.padnext.audit import (
    EchtdatenUndeclared,
    RealDataRefused,
    audit_delivery,
    real_data_allowed,
)
from app.padnext.reader import (
    InvalidXmlError,
    PadnextError,
    PadnextSchemaError,
    parse_echtdaten,
    read_delivery,
    read_file,
)
from app.padnext.schema import SchemaUnavailable, SchemaViolation, validate_payload
from app.padnext.validation import (
    CATALOG,
    MAX_REPORTED_ISSUES,
    SUPPORTED_VERSION,
    PadnextValidationFailed,
    ParsedPreview,
    ValidationError,
    ValidationResult,
    build_preview,
    validate_bytes,
    validate_file,
)
from app.schemas.padnext import (
    PadnextAuditedPosition,
    PadnextAuditReport,
    PadnextDelivery,
    PadnextFinding,
    PadnextParsedPreview,
    PadnextPosition,
    PadnextValidationIssue,
    PadnextValidationReport,
)

__all__ = [
    "CATALOG",
    "MAX_REPORTED_ISSUES",
    "SUPPORTED_VERSION",
    "EchtdatenUndeclared",
    "InvalidXmlError",
    "PadnextAuditReport",
    "PadnextAuditedPosition",
    "PadnextDelivery",
    "PadnextError",
    "PadnextFinding",
    "PadnextParsedPreview",
    "PadnextPosition",
    "PadnextSchemaError",
    "PadnextValidationFailed",
    "PadnextValidationIssue",
    "PadnextValidationReport",
    "ParsedPreview",
    "RealDataRefused",
    "SchemaUnavailable",
    "SchemaViolation",
    "ValidationError",
    "ValidationResult",
    "audit_delivery",
    "build_preview",
    "parse_echtdaten",
    "read_delivery",
    "read_file",
    "real_data_allowed",
    "validate_bytes",
    "validate_file",
    "validate_payload",
]
