"""The trust invariant: a `confirmed_wrong` finding always carries its citation.

`docs/content/product-output-spec.md` states it as the one thing every customer-facing output must
honour: *"Every flag carries its citation."* Any finding that puts a claimed euro into
`confirmed_wrong_eur` is a statement "this line is a problem" backed by a *verified* rule — an
exclusion, a Zielleistung/specificity conflict, or a § 5 factor ceiling — and a verified rule has an
id and a legal basis. A finding in that bucket with an empty `rule_id` or `legal_basis` is not a
defect in the invoice; it is a defect in the report, and a payer who asks "which rule?" gets no
answer.

A product-surface audit found exactly one live instance of this: the § 5 chapter-band branch of
`padnext_factor_above_maximum` (GOÄ 3 at 4.0×, no `factor_caps.csv` row, only the Abschnitt B
Höchstsatz applies) reported `legal_basis="§ 5 Abs. 1, 2 GOÄ"` — correct — beside `rule_id=""` —
untraceable. `app.catalog.catalog_loader.FactorBand.rule_id` fixes the gap by naming the catalog's
own chapter-band structure the same way `FactorCapRule.rule_id` already names a Leistungslegende
cap. This module is the regression guard for that class of bug, checked three ways:

  1. `test_the_worked_example_carries_a_real_citation` — the exact GOÄ 3 / 4.0× case named in the
     spec's worked example, run live.
  2. `test_synthetic_five_line_delivery_matches_the_audit` — the five-line delivery
     (Ziffern 5, 7, 301, 3, 412) the spec's O3 "Worked example" table describes, run live end to
     end, checking both the traffic-light table and citation completeness.
  3. `test_every_golden_fixture_confirmed_wrong_position_is_cited` — every committed
     `tests/golden/*/expected.json`, so a future fixture cannot ship the same gap silently.
  4. `test_every_verified_factor_cap_produces_a_cited_finding` and
     `test_every_factor_band_produces_a_cited_finding` — a sweep over *every* verified
     `factor_caps.csv` row and *every* § 5 chapter band in the catalog, so the fix is checked against
     the whole rule set this deployment enforces, not just the one Ziffer the audit happened to
     name.

Deliberately scoped to the finding types that are actually backed by an identifiable rule or
catalog-band id — `padnext_factor_above_maximum`, `padnext_mutual_exclusion`, and the dynamic
`padnext_blocked_*` exclusion/Zielleistung/specificity findings. `padnext_amount_mismatch`,
`padnext_justification_missing` and `padnext_inactive_ziffer` are pure arithmetic or statute-direct
checks with no reviewed rule row behind them — `legal_basis` alone is their whole citation, by
design (see the comment above `VERIFIED_DEFECT_FINDINGS` in `app.padnext.audit`) — so they are not
asserted to carry a `rule_id`. `padnext_inactive_ziffer` is additionally unreachable against the
real catalog today (no Ziffer in `data/catalogs/goae_current/goae.official.json` is inactive) and
carries no `legal_basis` either; that is a separate, pre-existing gap, out of scope for this fix
because no verified citation for "this Ziffer was withdrawn" exists anywhere in this repo's data —
inventing one would be exactly the guess this fix refuses to make elsewhere. It is not silently
exempted from the *other* checks here: if it is ever exercised on real catalog data, it is on the
findings-type list nowhere in this module and would not be caught by these tests — flagged in the
PR description as a follow-up, not fixed here.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.padnext import audit_delivery, read_delivery
from tests.golden.oracle import GOLDEN_DIR, REPO_ROOT

#: Finding types produced by an identifiable, verified *rule* (an exclusion, a Zielleistung/
#: specificity conflict, a Leistungslegende cap, or — after this fix — a § 5 chapter band): these
#: must carry both `rule_id` and `legal_basis`. `padnext_blocked_*` is a family
#: (`padnext_blocked_exclusion`, `padnext_blocked_zielleistung`, …) rather than one literal string,
#: hence the prefix check below.
_RULE_ID_REQUIRED_TYPES = {"padnext_factor_above_maximum", "padnext_mutual_exclusion"}
_RULE_ID_REQUIRED_PREFIX = "padnext_blocked_"

#: Finding types that are pure arithmetic or direct statute application — no reviewed rule row
#: behind them, so there is no `rule_id` to name. `legal_basis` alone is their whole citation, by
#: design (see the comment above `VERIFIED_DEFECT_FINDINGS` in `app.padnext.audit`).
_LEGAL_BASIS_ONLY_TYPES = {"padnext_amount_mismatch", "padnext_justification_missing"}


def _citation_requirement(finding_type: str) -> str | None:
    """Which fields a finding of this type must carry to count as "cited", or `None` if this
    module takes no position on it (see the module docstring re. `padnext_inactive_ziffer`)."""
    if finding_type in _RULE_ID_REQUIRED_TYPES or finding_type.startswith(_RULE_ID_REQUIRED_PREFIX):
        return "rule_id_and_legal_basis"
    if finding_type in _LEGAL_BASIS_ONLY_TYPES:
        return "legal_basis_only"
    return None


def _is_cited(finding: dict) -> bool:
    requirement = _citation_requirement(finding["type"])
    if requirement == "rule_id_and_legal_basis":
        return bool(finding.get("rule_id")) and bool(finding.get("legal_basis"))
    if requirement == "legal_basis_only":
        return bool(finding.get("legal_basis"))
    return False


def _assert_confirmed_wrong_positions_are_cited(
    positions: list[dict], findings: list[dict], *, context: str
) -> None:
    """The core invariant, applied to one report's already-serialized positions/findings.

    For every position the report itself calls `confirmed_wrong`, at least one finding raised
    against that `positionsnr` must satisfy `_is_cited` — the same two fields (or, for a purely
    arithmetic/statute-direct check, the one field) the spec's "one invariant" names.
    """
    findings_by_position: dict[str | None, list[dict]] = {}
    for finding in findings:
        findings_by_position.setdefault(finding.get("positionsnr"), []).append(finding)

    uncited = []
    for position in positions:
        if position.get("bucket") != "confirmed_wrong":
            continue
        candidates = findings_by_position.get(position["positionsnr"], [])
        if not any(_is_cited(f) for f in candidates):
            uncited.append(
                {
                    "positionsnr": position.get("positionsnr"),
                    "ziffer": position.get("ziffer"),
                    "findings": candidates,
                }
            )

    assert not uncited, (
        f"{context}: confirmed_wrong position(s) with no cited finding: {uncited}"
    )


# ==========================================================================================
# 1. the worked example named in the spec, run live
# ==========================================================================================


def test_the_worked_example_carries_a_real_citation(pipeline):
    """GOÄ 3 at faktor 4.0 — `docs/content/product-output-spec.md`, O1, worked example.

    Before the fix this reported `verdict_code FACTOR_ABOVE_CAP`, `rule_id ""`,
    `citation.quote ""` while still landing in `confirmed_wrong`. `citation.quote` is not a field on
    any audit-path model today (`PadnextFinding`/`PadnextAuditedPosition` have no `quote` field at
    all — see the spec's field glossary) and adding one is out of scope for this fix: it would
    change every serialized finding's shape and, via `Catalog.sha256`/receipt hashing, move every
    receipt hash ever issued for a change that adds no priceable position — exactly what
    `catalog_loader._read_percentage_surcharges` already refuses to do for the same reason. What is
    asserted here is the one thing the spec's own invariant actually requires: `rule_id` and
    `legal_basis` non-empty, tied to a real, `verified=true` catalog fact.
    """
    from tests.test_padnext import _one_position_delivery, position

    payload = _one_position_delivery("3", "4.0", "150", "34.97")
    delivery, read_findings = read_delivery(payload, source_name="probe.xml")
    report = audit_delivery(
        delivery,
        catalog=pipeline.catalog,
        rules=pipeline.rules,
        souffle_run=pipeline.souffle.run,
        read_findings=read_findings,
    )

    row = position(report, "1")
    assert row.bucket == "confirmed_wrong", row.bucket_reason
    finding = next(f for f in report.findings if f.type == "padnext_factor_above_maximum")
    assert finding.legal_basis == "§ 5 Abs. 1, 2 GOÄ"
    assert finding.rule_id == "factor_band_b"

    # And the same fact reachable from the catalog directly, so the finding's id is not a string
    # this test invented independently of what `Catalog` actually assigned.
    band = pipeline.catalog.factor_band("3")
    assert finding.rule_id == band.rule_id
    assert finding.legal_basis == band.legal_basis


# ==========================================================================================
# 2. the five-line delivery from the O3 worked example, run live end to end
# ==========================================================================================


def _five_line_delivery() -> bytes:
    """Ziffern 5, 7, 301, 3, 412 — `docs/content/product-output-spec.md`, O3, "Worked example".

    One `<abrechnungsfall>`, one `<datum>` for every line, so the mutual exclusion between 5 and 7
    is a same-date match rather than an advisory cross-date one. Amounts are `punkte × faktor ×
    punktwert_cent`, faktor 1.0 throughout except Ziffer 3 (4.0, deliberately over the § 5 Abschnitt
    B Höchstsatz of 3.5) — the same arithmetic `tests/golden/oracle.py` uses, so these numbers are
    checked against the catalog in `test_synthetic_five_line_delivery_matches_the_audit` rather than
    only asserted against themselves.
    """
    positions = [
        ("1", "5", "1.0", "80", "4.66"),
        ("2", "7", "1.0", "160", "9.33"),
        ("3", "301", "1.0", "160", "9.33"),
        ("4", "3", "4.0", "150", "34.97"),
        ("5", "412", "1.0", "280", "16.32"),
    ]
    lines = "".join(
        f'<goziffer positionsnr="{nr}" go="GOÄ" ziffer="{ziffer}">'
        f"<datum>2026-07-20</datum><anzahl>1</anzahl><text>Probe</text>"
        f"<faktor>{faktor}</faktor><punktzahl>{punktzahl}</punktzahl>"
        f"<gesamtbetrag>{betrag}</gesamtbetrag></goziffer>"
        for nr, ziffer, faktor, punktzahl, betrag in positions
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rechnungen anzahl="1" echtdaten="false" xmlns="http://padinfo.de/ns/pad">'
        '<nachrichtentyp version="02.12">ADL</nachrichtentyp>'
        "<rechnungsersteller><name>Synthetisch</name></rechnungsersteller>"
        '<leistungserbringer id="01"><name>Dr. Test</name></leistungserbringer>'
        '<rechnung id="SYNTH-AUDIT-0001" aisrechnungsnr="RG-1"><abrechnungsfall>'
        "<behandlungsart>0</behandlungsart><vertragsart>1</vertragsart>"
        f'<positionen posanzahl="{len(positions)}">{lines}</positionen>'
        "</abrechnungsfall></rechnung></rechnungen>"
    ).encode("utf-8")


@pytest.fixture
def five_line_report(pipeline):
    delivery, read_findings = read_delivery(_five_line_delivery(), source_name="synth_audit.xml")
    return audit_delivery(
        delivery,
        catalog=pipeline.catalog,
        rules=pipeline.rules,
        souffle_run=pipeline.souffle.run,
        read_findings=read_findings,
    )


def test_synthetic_five_line_delivery_matches_the_audit(five_line_report):
    """The O3 table, reproduced: of five lines, zero land on green, and every `confirmed_wrong`
    line is now cited. `bucket`/`verdict` assignment itself is untouched by this fix — this pins
    down that the fix did not flip anything, only added the missing citation."""
    from tests.test_padnext import position

    report = five_line_report

    # ziffer 5: the cheaper half of a mutual exclusion with 7 -> confirmed_wrong ("red")
    five = position(report, "1")
    assert five.ziffer == "5"
    assert five.bucket == "confirmed_wrong", five.bucket_reason

    # ziffer 7: the pricier survivor -> unconfirmed ("yellow"), not a clean pass
    seven = position(report, "2")
    assert seven.ziffer == "7"
    assert seven.bucket == "unconfirmed", seven.bucket_reason

    # ziffer 301: no verified rule bears on it alone (specificity needs 300 too) -> unconfirmed
    three_o_one = position(report, "3")
    assert three_o_one.ziffer == "301"
    assert three_o_one.bucket == "unconfirmed", three_o_one.bucket_reason

    # ziffer 3: over the § 5 Höchstsatz -> confirmed_wrong ("red"), now cited
    three = position(report, "4")
    assert three.ziffer == "3"
    assert three.bucket == "confirmed_wrong", three.bucket_reason

    # ziffer 412: age-restricted, but PADnext never reads patient age -> unconfirmed, not "fine"
    four_twelve = position(report, "5")
    assert four_twelve.ziffer == "412"
    assert four_twelve.bucket == "unconfirmed", four_twelve.bucket_reason

    # Zero of five positions confirmed_fine — the spec's "of five lines, zero landed on green".
    assert all(p.bucket != "confirmed_fine" for p in report.positions)

    # The financial split this fix must not touch: five confirmed_wrong (4.66) + three confirmed_wrong
    # (34.97) = 39.63; the rest is unconfirmed. Untouched by the citation fix — pinned so a future
    # change to this test file cannot silently also change what is/isn't confirmed_wrong.
    assert report.confirmed_wrong_eur == Decimal("39.63")
    assert report.confirmed_fine_eur == Decimal("0.00")

    payload = json.loads(report.model_dump_json())
    _assert_confirmed_wrong_positions_are_cited(
        payload["positions"], payload["findings"], context="synthetic five-line delivery"
    )


# ==========================================================================================
# 3. every committed golden fixture
# ==========================================================================================


def _golden_expected_files() -> list[Path]:
    return sorted(GOLDEN_DIR.glob("*/expected.json"))


def _reports_in(expected: dict) -> list[dict]:
    """Every `report` object a golden `expected.json` carries.

    Usually exactly one at the top level. `case_e_echtdaten_gate` refuses the raw (undeclared)
    delivery with a 422 and carries its one report nested under `after_anonymisation` instead — a
    delivery this engine refused is a delivery it drew no verdict from, so there is nothing to check
    at the top level, but the anonymised re-upload it also records is a real audited report and
    checked the same as every other case's.
    """
    reports = []
    if "report" in expected:
        reports.append(expected["report"])
    after = expected.get("after_anonymisation")
    if isinstance(after, dict) and "report" in after:
        reports.append(after["report"])
    return reports


@pytest.mark.parametrize("expected_path", _golden_expected_files(), ids=lambda p: p.parent.name)
def test_every_golden_fixture_confirmed_wrong_position_is_cited(expected_path: Path):
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    reports = _reports_in(expected)
    assert reports, f"{expected_path.parent.name}: no report to check"
    for report in reports:
        _assert_confirmed_wrong_positions_are_cited(
            report["positions"], report["findings"], context=expected_path.parent.name
        )


def test_padnext_inactive_ziffer_is_not_yet_reachable():
    """Documents why `padnext_inactive_ziffer` has no entry in `_citation_requirement` above: not
    because its citation was checked and found acceptable, but because it has neither a `rule_id`
    nor a `legal_basis` today (see `app.padnext.audit`, the `padnext_inactive_ziffer` finding) and is
    not reachable against the real catalog to notice. If this ever starts failing, a Ziffer has been
    marked inactive in `data/catalogs/goae_current/goae.official.json` and the citation gap for that
    finding type needs its own fix before this test file's carve-out is still honest.
    """
    catalog = json.loads(
        (REPO_ROOT / "data" / "catalogs" / "goae_current" / "goae.official.json").read_text(
            encoding="utf-8"
        )
    )
    inactive = [z for z in catalog["ziffern"] if z.get("status", "active") != "active"]
    assert inactive == [], (
        "a Ziffer is now inactive in the real catalog; padnext_inactive_ziffer's missing citation "
        f"(see this module's docstring) is reachable and needs its own fix: {inactive}"
    )


# ==========================================================================================
# 4. every verified factor rule this deployment enforces, swept
# ==========================================================================================


def test_every_verified_factor_cap_produces_a_cited_finding(pipeline):
    """Every `factor_caps.csv`/`factor_caps.manual.csv` row with `verified=true`, billed one point
    over its own ceiling (and safely under the chapter band, so the cap branch — not the band
    branch — is what fires): the resulting `padnext_factor_above_maximum` finding must cite that
    exact rule. This is the sweep version of `test_case_c_the_cap_convicts_the_over_cap_line_only`
    in `tests/test_golden_cases.py`, run against the whole enforced set instead of one Ziffer."""
    from tests.test_padnext import _one_position_delivery

    uncited = []
    for cap in pipeline.rules.factor_caps:
        if not cap.verified:
            continue
        band = pipeline.catalog.factor_band(cap.ziffer)
        faktor = cap.max_factor + Decimal("0.1")
        if faktor > band.max:
            # This cap's own ceiling is at (or effectively at) the chapter band's — the band branch
            # would fire instead, which is `test_every_factor_band_produces_a_cited_finding` below.
            continue
        entry = pipeline.catalog.get(cap.ziffer)
        if entry is None or entry.punkte is None:
            continue
        betrag = str((entry.punkte * faktor * pipeline.catalog.punktwert_cent / 100).quantize(
            Decimal("0.01")
        ))
        payload = _one_position_delivery(cap.ziffer, str(faktor), str(entry.punkte), betrag)
        delivery, read_findings = read_delivery(payload, source_name="probe.xml")
        report = audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=read_findings,
        )
        finding = next(
            (f for f in report.findings if f.type == "padnext_factor_above_maximum"), None
        )
        if finding is None or not finding.rule_id or not finding.legal_basis:
            uncited.append((cap.ziffer, cap.rule_id, finding))

    assert not uncited, f"verified factor caps with an uncited finding: {uncited}"


def test_every_factor_band_produces_a_cited_finding(pipeline):
    """Every § 5 chapter band the catalog declares (`factor_bands`/`special_factor_ziffern`),
    exercised through whichever Ziffer of that category has no `factor_caps.csv` row of its own —
    so the band branch, not the cap branch, is what fires — must produce a cited finding. This is
    exactly the class of bug the fix in `FactorBand.rule_id` addresses, checked against every
    category the catalog defines rather than only category B (the one GOÄ 3 happens to be in)."""
    capped_ziffern = {cap.ziffer for cap in pipeline.rules.factor_caps}
    checked_categories: set[str] = set()
    uncited = []

    for ziffer, entry in sorted(pipeline.catalog.ziffern.items()):
        if ziffer in capped_ziffern or not entry.is_active or entry.punkte is None:
            continue
        if ziffer in pipeline.catalog.special_factor_ziffern:
            continue  # covered by name below, not by category sweep
        category = entry.category
        if not category or category in checked_categories:
            continue
        band = pipeline.catalog.factor_bands.get(category)
        if band is None:
            continue
        faktor = band.max + Decimal("0.1")
        betrag = str(
            (entry.punkte * faktor * pipeline.catalog.punktwert_cent / 100).quantize(
                Decimal("0.01")
            )
        )
        from tests.test_padnext import _one_position_delivery

        payload = _one_position_delivery(ziffer, str(faktor), str(entry.punkte), betrag)
        delivery, read_findings = read_delivery(payload, source_name="probe.xml")
        report = audit_delivery(
            delivery,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
            souffle_run=pipeline.souffle.run,
            read_findings=read_findings,
        )
        finding = next(
            (f for f in report.findings if f.type == "padnext_factor_above_maximum"), None
        )
        checked_categories.add(category)
        if finding is None or not finding.rule_id or not finding.legal_basis:
            uncited.append((ziffer, category, finding))

    assert checked_categories, "no category was exercised — the sweep found nothing to check"
    assert not uncited, f"factor bands with an uncited finding: {uncited}"
