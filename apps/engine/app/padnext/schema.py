"""Framing validation for a PADnext payload, before anything is read out of it.

A delivery arrives as a file someone else's software produced, and there are two very different
things that can be wrong with it. It can be the wrong kind of document — not an ADL payload, no
message type, a treatment code that is not a treatment code — or it can be a perfectly ordinary
ADL payload with mistakes in it, which is the entire reason this engine exists. This module draws
that line and nothing else:

    framing is fatal        the document cannot be audited, or cannot be priced, so refuse it
    positions are advisory  every claimed line still gets a verdict and a reason

The schema itself is `data/schemas/padnext/padx_adl_v2.12.subset.xsd`, and the long comment at the
top of that file is the real documentation for this module: what it enforces, what it deliberately
does not, and why each divergence from the official PADneXt schema is a decision rather than an
omission. It is our own subset — the official XSD is not redistributable here, and an operator who
holds it can drop it in `data/licensed/padnext/` to have it preferred (`Settings.padnext_xsd_path`).

**One invariant lives in code rather than in the schema, and it is not an oversight.** XSD 1.0
cannot express "this child is required, and unknown siblings are still welcome": a wildcard beside
a required particle is a non-deterministic content model and libxml2 refuses to compile it. A real
Abrechnungsfall carries patient identity, diagnoses and dates this engine never parses, so closing
that content model would refuse nearly every real delivery. `_missing_positionen` therefore checks
the one thing that matters there — that an Abrechnungsfall has positions at all — and reports it
through the same `SchemaViolation` channel with the same line number. Without it, an Abrechnungsfall
with no `<positionen>` is read as an invoice claiming nothing: totals of 0.00, no findings, and a
report that looks like a clean audit of an empty invoice rather than a malformed file.

**Why lxml.** Line and column numbers. `xml.etree` cannot validate against a schema at all, and a
validator that can only say *what* is wrong and not *where* leaves the person fixing the export
grepping. Validation happens on its own hardened parse of the same bytes; the reader's existing
`xml.etree` parse is untouched, so nothing about how a valid delivery is read has changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from lxml import etree

from app.config import PadnextSchemaPolicy, get_settings
from app.schemas import Warning_

PAD_NS = "http://padinfo.de/ns/pad"

#: Our own invariants, reported like schema violations. Prefixed so a reader can tell them from
#: libxml2's own rule names (`SCHEMAV_*`) at a glance.
RULE_MISSING_POSITIONEN = "PADX_ABRECHNUNGSFALL_WITHOUT_POSITIONEN"

#: The `type` every framing violation carries as a finding. Named once here because three places
#: depend on the exact string — the reader that produces it, `PadnextAuditReport.schema_warnings`
#: that lifts it back out, and the tests that assert a `warn` delivery reports one.
SCHEMA_VIOLATION_FINDING_TYPE = "padnext_schema_violation"

#: Cap on how many violations travel in one error. A file with a systematic mistake produces one
#: violation per position, and an exception carrying nine hundred of them helps nobody; the count
#: is always reported honestly, so nothing is hidden by the truncation.
MAX_REPORTED_VIOLATIONS = 20


@dataclass(frozen=True)
class SchemaViolation:
    """One reason a delivery is not a readable ADL payload, and where in the file it is.

    `line` and `column` come from libxml2 and point into the payload as submitted — which is the
    only location worth reporting, because the person who has to fix it is looking at that file in
    an editor. `path` is resolved to element names rather than left as libxml2's positional XPath
    (`/*/*[2]/*/*[1]`), since a path a human can read is the difference between a usable error and
    a puzzle.
    """

    message: str
    line: int
    column: int
    path: str
    rule: str
    element: str = ""

    @property
    def location(self) -> str:
        """`line 12, column 8 at rechnungen/rechnung/abrechnungsfall/positionen`."""
        where = f"line {self.line}" if self.line else "line unknown"
        if self.column:
            where += f", column {self.column}"
        return f"{where} at {self.path}" if self.path else where

    def as_finding(self) -> Warning_:
        """The same violation as a finding, for `warn` policy. German, like every other finding."""
        return Warning_(
            type=SCHEMA_VIOLATION_FINDING_TYPE,
            severity="error",
            message=(
                f"Die Lieferung verstößt gegen das PADnext-Schema ({self.location}): "
                f"{self.message}"
            ),
        )


def describe_violations(violations: list[SchemaViolation]) -> str:
    """One line naming every violation, truncated with an honest count.

    The exception type itself lives in `reader.py`, beside `PadnextError` it must subclass so that
    the API's existing handler keeps returning 422 for it. This module stays pure validation: it
    reports what is wrong and never decides what that costs.
    """
    shown = violations[:MAX_REPORTED_VIOLATIONS]
    detail = "; ".join(f"{v.location}: {v.message}" for v in shown)
    more = len(violations) - len(shown)
    if more > 0:
        detail += f"; and {more} further violation(s)"
    return (
        f"PADnext payload does not conform to the expected ADL framing "
        f"({len(violations)} violation(s)): {detail}"
    )


class SchemaUnavailable(RuntimeError):
    """The schema file is missing or will not compile. A deployment fault, not a bad delivery."""


@lru_cache
def load_schema(path: str | Path) -> etree.XMLSchema:
    """Compile the schema once per process. Compilation is the expensive part, not validation."""
    p = Path(path)
    if not p.is_file():
        raise SchemaUnavailable(
            f"PADnext schema not found at {p}. It ships with the repository under "
            "data/schemas/padnext/; check DATA_DIR if this is a container."
        )
    try:
        return etree.XMLSchema(etree.parse(str(p)))
    except etree.XMLSchemaParseError as exc:
        raise SchemaUnavailable(f"PADnext schema at {p} does not compile: {exc}") from exc


def _parser() -> etree.XMLParser:
    """A parser that will not fetch, expand or explode.

    The reader has already refused a DOCTYPE outright by the time validation runs, so this is
    belt and braces — but this parse is a second, independent entry point for untrusted bytes and
    it does not get to be the lenient one.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        recover=False,
    )


def _element_path(element: etree._Element) -> tuple[str, str]:
    """`(rechnungen/rechnung/abrechnungsfall/positionen, positionen)` — local names, no namespaces.

    Namespace URIs are stripped on purpose. There is exactly one namespace in play and repeating
    it at every step turns a path into something nobody reads.
    """
    names = [etree.QName(node).localname for node in reversed(list(element.iterancestors()))]
    tag = etree.QName(element).localname
    return "/".join([*names, tag]), tag


def _readable_path(tree: etree._ElementTree, xpath: str | None) -> tuple[str, str]:
    """Resolve libxml2's positional XPath (`/*/*[2]/*/*[1]`) to a path of element names.

    Falls back to the raw XPath rather than inventing one: a wrong path is worse than an ugly one.
    """
    if not xpath:
        return "", ""
    try:
        found = tree.xpath(xpath)
    except etree.XPathError:
        return xpath, ""
    if not found or not isinstance(found[0], etree._Element):
        return xpath, ""
    return _element_path(found[0])


def _missing_positionen(tree: etree._ElementTree) -> list[SchemaViolation]:
    """Every `abrechnungsfall` with no `positionen` child. See the module docstring for why this
    is not in the XSD."""
    violations: list[SchemaViolation] = []
    for case in tree.iter(f"{{{PAD_NS}}}abrechnungsfall"):
        if case.find(f"{{{PAD_NS}}}positionen") is not None:
            continue
        path, tag = _element_path(case)
        violations.append(
            SchemaViolation(
                message=(
                    "Element 'abrechnungsfall' has no 'positionen' child. An Abrechnungsfall "
                    "without positions is not an invoice this engine can audit — it would be read "
                    "as one claiming nothing at all."
                ),
                line=case.sourceline or 0,
                column=0,
                path=path or "rechnungen/rechnung/abrechnungsfall",
                rule=RULE_MISSING_POSITIONEN,
                element=tag or "abrechnungsfall",
            )
        )
    return violations


def validate_payload(
    payload: bytes,
    *,
    policy: PadnextSchemaPolicy | None = None,
    schema_path: Path | None = None,
) -> list[SchemaViolation]:
    """Validate the framing of a payload. Returns violations; never raises for a bad delivery.

    Raising is the caller's decision, because it depends on policy and the caller owns the
    findings list — see `reader.read_delivery`. `off` returns nothing without touching the file.

    A payload that will not even parse here returns no violations rather than reporting a parse
    error: the reader's own `parse_xml` is the authority on well-formedness and has already run,
    with a message tuned for it. Two different parsers disagreeing about the same bytes must not
    turn into two different errors for one problem.
    """
    settings = get_settings()
    policy = policy or settings.padnext_schema_policy
    if policy == PadnextSchemaPolicy.OFF:
        return []

    path = schema_path or settings.padnext_xsd_path
    schema = load_schema(path)

    try:
        tree = etree.ElementTree(etree.fromstring(payload, _parser()))
    except etree.XMLSyntaxError:
        return []

    violations: list[SchemaViolation] = []
    if not schema.validate(tree):
        for entry in schema.error_log:
            readable, tag = _readable_path(tree, entry.path)
            violations.append(
                SchemaViolation(
                    message=entry.message,
                    line=entry.line or 0,
                    column=entry.column or 0,
                    path=readable,
                    rule=entry.type_name or "SCHEMAV",
                    element=tag,
                )
            )
    violations.extend(_missing_positionen(tree))
    return violations
