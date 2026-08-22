"""What leaves this system, and what has to be true of it.

An export is the point at which a billing draft stops being something the engine holds and becomes
a document somebody else acts on — a PVS imports it, a Rechnungsprüfer reads it, a payer disputes
it. Two properties follow from that, and both are structural rather than advisory.

**An export is only ever made from the durable record.** Not from the response the caller happens
to be holding, and not from a cache. The document below is assembled from the Postgres row inside
the same transaction that marks the proposal `EXPORTED` and writes the audit event, so "this is
what was exported" and "this is what the database says" cannot come apart. There is no code path
that builds a `ProposalExport` from anything else.

**An export carries its own provenance.** `receipt_hash` identifies the catalog, rule tables, logic
programs, solver versions, policy and input that produced the result; `input_hash` identifies the
clinical input alone. Together with the version fields and the audit log, a document read a year
from now can be tied back to the exact engine state that produced it and the named person who
accepted responsibility for it. A billing document that cannot answer "who approved this, against
what rules" is the thing this whole layer exists to avoid.

What an export is **not** is an invoice. It is the record of an approved draft, and the approval it
carries was signed by a name the service did not authenticate — there is no login in front of any
of this. `docs/compliance/PRIVATE_DATA_WARNING.md` tracks that gap; the document states the name it
was given and never implies more.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import RuleCoverage, Warning_
from app.schemas.result import CodingResponse
from app.schemas.solver import MissingDocumentation

#: Bumped when the shape below changes in a way an importer would notice.
#:
#: Present because the consumer of this document is a system we do not control and cannot redeploy
#: — a PVS's importer, a spreadsheet somebody built. A file that changed shape without saying so
#: would fail on their side with no way to tell a new format from a corrupt file.
EXPORT_FORMAT_VERSION = "1.0"


class ExportRequest(BaseModel):
    """Who is taking the export.

    Required for the same reason `approved_by` is required on an approval: an export is a thing a
    person did, and an unattributed one is indistinguishable from one nobody can account for. It is
    recorded, not verified — see the module docstring.
    """

    model_config = ConfigDict(extra="forbid")

    exported_by: str = Field(
        min_length=1,
        description="Who is taking this export. Recorded in the audit log; not authenticated.",
    )
    #: Free-text context, written to the audit event alongside the name. A ticket number, the PVS
    #: the file is going to — whatever makes the log readable six months later.
    note: str = ""

    @field_validator("exported_by", "note", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        """Trim before the length constraint runs, so `"   "` is refused rather than recorded.

        `mode="before"` matters and is not incidental: an `after` validator runs *past*
        `min_length`, so two spaces would satisfy the constraint, be stripped to nothing, and reach
        the store as an export attributed to no one — a 500 where a 422 about a field belongs.

        Non-strings are passed through untouched for Pydantic's own type error to report; coercing
        here would turn "exported_by was a number" into a confusing length complaint.
        """
        return value.strip() if isinstance(value, str) else value


class EngineIdentity(BaseModel):
    """Everything that decides what the engine would answer, named and pinned.

    Flattened out of the proposal rather than referenced, because an export is read on its own: a
    field that said "see the proposal" would be useless in a document whose whole purpose is to be
    separable from this database.
    """

    model_config = ConfigDict(extra="forbid")

    catalog_version: str = ""
    catalog_sha256: str = ""
    rules_version: str = ""
    rules_hash: str = ""
    logic_version: str = ""
    solver_version: str = ""
    rules_engine_version: str = ""


class DecisionRecord(BaseModel):
    """Who decided what, and when. The half of the document a dispute actually turns on."""

    model_config = ConfigDict(extra="forbid")

    approved_by: str | None = None
    approved_at: datetime | None = None
    #: Present for completeness, always null in practice: a rejected proposal cannot be exported,
    #: because `REJECTED` is terminal. Carried so the shape does not change if that ever does.
    rejected_by: str | None = None
    rejected_at: datetime | None = None
    rejected_reason: str | None = None
    exported_by: str
    exported_at: datetime


class AuditEventRecord(BaseModel):
    """One row of the append-only log, as it is written in the database."""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    actor: str
    timestamp: datetime
    metadata: dict[str, Any] | None = None


class ProposalExport(BaseModel):
    """The downloadable record of one approved proposal.

    Served as `proposal_{proposal_id}.json` with a `Content-Disposition: attachment` header. The
    JSON is the contract; the filename is a convenience.
    """

    model_config = ConfigDict(extra="forbid")

    export_format_version: str = EXPORT_FORMAT_VERSION

    proposal_id: str
    case_id: str | None = None
    #: Always `EXPORTED` — the transition happened in the transaction that built this document.
    #: Stated rather than implied, because a reader holding the file should not have to know that.
    status: str
    created_at: datetime

    #: SHA-256 over the catalog, rule tables, logic programs, solver versions, policy and input.
    receipt_hash: str
    #: SHA-256 over the canonical clinical input alone. Two exports sharing this and differing in
    #: `receipt_hash` are the same case coded by two different engine states.
    input_hash: str

    engine: EngineIdentity
    decision: DecisionRecord

    #: The invoice draft in full: extraction, accepted and blocked Ziffern with their factors and
    #: amounts, the audit trail, and the proof tree behind every line. Stored whole rather than
    #: summarised — a summary is not evidence, and the proof atoms are the reason a position can be
    #: defended at all.
    solver_result: CodingResponse

    warnings: list[Warning_] = Field(default_factory=list)
    missing_documentation: list[MissingDocumentation] = Field(default_factory=list)

    #: How much of the rule set was actually enforced when this was produced. Travels with the
    #: export because a reader must not take "no finding" for "the rules confirmed it" — the
    #: coverage is partial and the document has to say so on its own.
    rule_coverage: RuleCoverage | None = None

    #: The full append-only log for this proposal, oldest first, including the `EXPORTED` event
    #: this very export wrote. Self-describing on purpose: the document records its own creation.
    audit_events: list[AuditEventRecord] = Field(default_factory=list)


__all__ = [
    "EXPORT_FORMAT_VERSION",
    "AuditEventRecord",
    "DecisionRecord",
    "EngineIdentity",
    "ExportRequest",
    "ProposalExport",
]
