"""Check a PADnext delivery against the rules engine.

A PADnext file arrives already coded, so this is not the coding pipeline — it is the coding
pipeline run backwards. The claimed positions become the candidate set, the same Datalog program
decides which of them survive the GOÄ suppression rules, and the money is recomputed from our own
catalog and compared with what the file claims.

Three things this deliberately does:

**It refuses real patient data.** `auftrag/@echtdaten` distinguishes production from test data. This
project's ground rule is synthetic data only, so a delivery flagged as real data is rejected before
anything is parsed out of it, unless someone with a lawful basis sets
`PADNEXT_ALLOW_REAL_DATA=1`. Refusing is the safe default; a POC has no business holding real
billing records.

**It does not trust the file's arithmetic.** `gesamtbetrag` is recomputed and any difference is
reported to the cent. The spec is explicit that these fields exist *für Kontrollzwecke*, so
checking them is the intended use, not an imposition.

**It never silently drops a position.** Every claimed line comes back with a verdict, and every
verdict that is not `chargeable` carries a reason.
"""

from __future__ import annotations

import os
from decimal import Decimal

from app.bridge.entity_to_ziffer import BridgeResult
from app.catalog import Catalog
from app.config import Settings, get_settings
from app.schemas import (
    ClinicalAct,
    ClinicalExtraction,
    CodeCandidate,
    JustificationFactor,
    Patient,
    Setting,
    Warning_,
)
from app.schemas.padnext import (
    BEHANDLUNGSART_LABEL,
    BEHANDLUNGSART_TO_SETTING,
    PadnextAuditedPosition,
    PadnextAuditReport,
    PadnextDelivery,
    PadnextFinding,
    PadnextPosition,
)
from app.rules.rule_store import RuleStore
from app.services import rule_coverage as rule_coverage_service
from app.services.receipt import receipt_hash
from app.validation.validator import cent_to_eur, line_amount_cent

#: § 6a Abs. 1 rates, as percentages, keyed by the setting our rules use.
SETTING_MINDERUNG_PERCENT: dict[Setting, Decimal] = {
    "ambulant": Decimal("0"),
    "stationaer": Decimal("25"),
    "belegarzt": Decimal("15"),
}


#: Engine warning types this module re-reports itself, with a position number and a recomputation
#: attached. Keeping both would show a reviewer one defect twice under two different names.
ENGINE_WARNINGS_REPORTED_PER_POSITION = frozenset(
    {"unknown_ziffer", "factor_above_hoechstsatz", "inactive_ziffer"}
)


class RealDataRefused(RuntimeError):
    """The delivery says it holds production data, which this POC will not process."""


def real_data_allowed(settings: Settings | None = None) -> bool:
    """Whether a delivery flagged as production data may be processed at all.

    The environment is consulted before settings on purpose: `get_settings()` is cached for the
    process lifetime, so an operator (or a test) flipping the variable must not need a restart to
    tighten it. Absent the variable, the configured default — `False` — applies.
    """
    raw = os.getenv("PADNEXT_ALLOW_REAL_DATA")
    if raw is not None and raw.strip():
        return raw.strip().lower() in {"1", "true", "yes"}
    return bool((settings or get_settings()).padnext_allow_real_data)


def _as_finding(warning: Warning_, *, positionsnr: str | None = None) -> PadnextFinding:
    return PadnextFinding(
        type=warning.type,
        severity=warning.severity,
        message=warning.message,
        ziffer=warning.ziffer,
        positionsnr=positionsnr,
        legal_basis=warning.legal_basis,
        rule_id=warning.rule_id,
    )


def _act_id(position: PadnextPosition, index: int) -> str:
    """Stable, collision-free id. positionsnr is only unique within a case, so the index leads."""
    return f"pad{index}"


def derive_setting(
    delivery: PadnextDelivery, findings: list[PadnextFinding]
) -> tuple[Setting, str]:
    """Work out the § 6a setting from behandlungsart, cross-checked against minderungssatz.

    Both are optional in a PADnext file and either can be wrong, so a disagreement is reported
    rather than resolved silently — the reduction is money, and guessing at it is how a practice
    ends up under-billing an entire quarter.
    """
    art = next(
        (c.behandlungsart for inv in delivery.invoices for c in inv.cases if c.behandlungsart),
        None,
    )
    rate = next(
        (
            c.minderungssatz
            for inv in delivery.invoices
            for c in inv.cases
            if c.minderungssatz is not None
        ),
        None,
    )

    setting: Setting = "ambulant"
    source = "default (keine behandlungsart angegeben)"

    if art is not None:
        if art in BEHANDLUNGSART_TO_SETTING:
            setting = BEHANDLUNGSART_TO_SETTING[art]
            source = f"behandlungsart={art} ({BEHANDLUNGSART_LABEL.get(art, art)})"
        else:
            findings.append(
                PadnextFinding(
                    type="padnext_behandlungsart_not_mapped",
                    severity="warning",
                    message=(
                        f"behandlungsart={art} ({BEHANDLUNGSART_LABEL.get(art, 'unbekannt')}) "
                        "lässt sich nicht eindeutig auf ambulant/stationär/belegärztlich "
                        "abbilden. Die Prüfung läuft als 'ambulant' — die Minderung nach § 6a "
                        "ist damit möglicherweise nicht berücksichtigt."
                    ),
                    legal_basis="§ 6a Abs. 1 GOÄ",
                )
            )
            source = f"behandlungsart={art}, nicht abbildbar → ambulant angenommen"
    elif rate is not None:
        # No behandlungsart, but a rate: infer the setting from the rate the file itself claims.
        for candidate, percent in SETTING_MINDERUNG_PERCENT.items():
            if percent == rate and percent != 0:
                setting = candidate
                source = f"minderungssatz={rate} % (behandlungsart fehlt)"
                break

    if rate is not None:
        expected = SETTING_MINDERUNG_PERCENT[setting]
        if rate != expected:
            findings.append(
                PadnextFinding(
                    type="padnext_minderung_mismatch",
                    severity="warning",
                    message=(
                        f"Die Datei nennt minderungssatz={rate} %, aus '{source}' folgt nach "
                        f"§ 6a Abs. 1 GOÄ aber {expected} %."
                    ),
                    legal_basis="§ 6a Abs. 1 GOÄ",
                    claimed=f"{rate} %",
                    recomputed=f"{expected} %",
                )
            )

    return setting, source


def build_audit_input(
    delivery: PadnextDelivery, setting: Setting
) -> tuple[ClinicalExtraction, BridgeResult, dict[str, Decimal], dict[str, PadnextPosition]]:
    """Turn claimed positions into the shape the rules engine already consumes.

    One synthetic act per claimed position, so a `begruendung` on a position can be bound to it as
    a § 12 Abs. 3 justification through the bridge's existing entity addressing.
    """
    bridge = BridgeResult()
    justifications: list[JustificationFactor] = []
    proposed_factors: dict[str, Decimal] = {}
    by_ziffer: dict[str, PadnextPosition] = {}

    for index, position in enumerate(delivery.positions(), start=1):
        if not position.is_goae:
            continue
        act_id = _act_id(position, index)
        bridge.acts.append(
            ClinicalAct(
                act_id=act_id,
                entity_id=act_id,
                source="procedure",
                entity_type=f"padnext_position_{position.ziffer}",
                description=position.text or f"PADnext Position {position.positionsnr}",
                confidence=Decimal("1"),
            )
        )
        bridge.candidates.append(
            CodeCandidate(
                act_id=act_id,
                ziffer=position.ziffer,
                priority=100,
                confidence=Decimal("1"),
                mapping_provenance="padnext_claimed",
                mapping_notes=f"positionsnr={position.positionsnr}",
            )
        )
        if position.faktor is not None:
            # Last one wins if a Ziffer appears twice; the duplicate is reported separately.
            proposed_factors[position.ziffer] = position.faktor
        if position.begruendung:
            justifications.append(
                JustificationFactor(
                    id=f"just_{act_id}",
                    reason=position.begruendung,
                    severity="schwer",
                    applies_to=[act_id],
                )
            )
        by_ziffer.setdefault(position.ziffer, position)

    extraction = ClinicalExtraction(
        patient=Patient(setting=setting),
        justification_factors=justifications,
        notes="Synthetisiert aus einer PADnext-Lieferung zur Prüfung. Keine Patientendaten.",
    )
    return extraction, bridge, proposed_factors, by_ziffer


def _recompute(
    position: PadnextPosition,
    catalog: Catalog,
    setting: Setting,
) -> tuple[Decimal | None, int | None]:
    """Recompute a line from our own catalog. Returns (eur, punkte)."""
    entry = catalog.get(position.ziffer)
    if entry is None or position.faktor is None:
        return None, (entry.punkte if entry else None)

    gross_cent = line_amount_cent(entry.punkte, position.faktor, catalog.punktwert_cent)

    # § 6a Abs. 1: the reduction applies unless the position is exempt (Buchstabe J).
    percent = position.minderungssatz
    if percent is None:
        percent = SETTING_MINDERUNG_PERCENT[setting]
    if percent and not catalog.minderung_exempt(position.ziffer):
        gross_cent = gross_cent * (Decimal("100") - percent) / Decimal("100")

    per_unit = cent_to_eur(gross_cent)
    return per_unit * position.anzahl, entry.punkte


def audit_delivery(
    delivery: PadnextDelivery,
    *,
    catalog: Catalog,
    rules: RuleStore,
    souffle_run,
    read_findings: list[Warning_] | None = None,
    settings: Settings | None = None,
) -> PadnextAuditReport:
    """Run the claimed positions through the rules engine and reconcile the money.

    `souffle_run(extraction, bridge, proposed_factors=...)` is injected rather than imported so
    this stays testable without a Soufflé binary, and so the caller controls engine construction.
    """
    settings = settings or get_settings()
    if delivery.echtdaten is True and not real_data_allowed(settings):
        raise RealDataRefused(
            "This PADnext delivery is flagged as production data (auftrag/@echtdaten). This "
            "proof of concept processes synthetic data only and has refused it. Set "
            "PADNEXT_ALLOW_REAL_DATA=1 only if you have a lawful basis and appropriate controls."
        )

    findings: list[PadnextFinding] = [_as_finding(w) for w in (read_findings or [])]

    if delivery.echtdaten is None:
        findings.append(
            PadnextFinding(
                type="padnext_echtdaten_unknown",
                severity="info",
                message=(
                    "Ohne Auftragsdatei ist nicht erkennbar, ob es sich um Echt- oder Testdaten "
                    "handelt (auftrag/@echtdaten). Es wurde von Testdaten ausgegangen."
                ),
            )
        )

    setting, setting_source = derive_setting(delivery, findings)
    extraction, bridge, proposed_factors, _ = build_audit_input(delivery, setting)

    claimed = delivery.positions()
    goae = [p for p in claimed if p.is_goae]

    seen: dict[str, str] = {}
    for position in goae:
        if position.ziffer in seen:
            findings.append(
                PadnextFinding(
                    type="padnext_duplicate_ziffer",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"GOÄ {position.ziffer} kommt mehrfach vor (Positionen "
                        f"{seen[position.ziffer]} und {position.positionsnr}). Die Regelprüfung "
                        "betrachtet eine Ziffer nur einmal; Mengenregeln sind nicht modelliert."
                    ),
                )
            )
        else:
            seen[position.ziffer] = position.positionsnr

    rules_result = souffle_run(extraction, bridge, proposed_factors=proposed_factors) if goae else None

    billable: set[str] = set(rules_result.billable) if rules_result else set()
    blocked_by_ziffer = {b.ziffer: b for b in (rules_result.blocked if rules_result else [])}
    conflicts = list(rules_result.conflicts) if rules_result else []
    proof_by_ziffer: dict[str, list[str]] = {}
    for step in rules_result.proof if rules_result else []:
        proof_by_ziffer.setdefault(step.ziffer, []).append(step.rule)
    needs_justification = set(rules_result.factor_needs_justification if rules_result else [])
    factor_invalid = set(rules_result.factor_invalid if rules_result else [])

    # The engine reports some of the same defects, but keyed only by Ziffer. Where we re-report one
    # per position with the position number and the recomputation, the engine's copy is strictly
    # less useful — drop it rather than show a reviewer the same defect twice under two names.
    position_of_ziffer = {p.ziffer: p.positionsnr for p in goae}
    for warning in rules_result.warnings if rules_result else []:
        if warning.type in ENGINE_WARNINGS_REPORTED_PER_POSITION:
            continue
        findings.append(
            _as_finding(warning, positionsnr=position_of_ziffer.get(warning.ziffer or ""))
        )

    audited: list[PadnextAuditedPosition] = []
    claimed_total = Decimal("0.00")
    recomputed_total = Decimal("0.00")
    comparable_claimed = Decimal("0.00")
    unpriceable_claimed = Decimal("0.00")

    for position in claimed:
        entry = catalog.get(position.ziffer)
        row = PadnextAuditedPosition(
            positionsnr=position.positionsnr,
            ziffer=position.ziffer,
            go=position.go,
            is_analog=position.is_analog,
            in_catalog=entry is not None,
            official_text=entry.official_text if entry else "",
            claimed_faktor=position.faktor,
            claimed_amount_eur=position.gesamtbetrag,
            punkte=entry.punkte if entry else None,
        )

        if position.gesamtbetrag is not None:
            claimed_total += position.gesamtbetrag

        if not position.is_goae:
            row.verdict = "out_of_scope"
            row.reason = (
                f"Gebührenordnung '{position.go}' wird von diesem Proof of Concept nicht geprüft."
            )
            findings.append(
                PadnextFinding(
                    type="padnext_fee_schedule_out_of_scope",
                    severity="info",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=row.reason,
                )
            )
            unpriceable_claimed += position.gesamtbetrag or Decimal("0.00")
            audited.append(row)
            continue

        if entry is None:
            row.verdict = "unknown_ziffer"
            row.reason = f"GOÄ {position.ziffer} ist im Katalog {catalog.catalog_version} nicht enthalten."
            findings.append(
                PadnextFinding(
                    type="padnext_unknown_ziffer",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=row.reason,
                )
            )
            unpriceable_claimed += position.gesamtbetrag or Decimal("0.00")
            audited.append(row)
            continue

        if not entry.is_active:
            findings.append(
                PadnextFinding(
                    type="padnext_inactive_ziffer",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=f"GOÄ {position.ziffer} ist im Katalog als '{entry.status}' geführt.",
                )
            )

        blocked = blocked_by_ziffer.get(position.ziffer)
        # A Conflict is an unordered pair (ziffer_a, ziffer_b) the rules refused to decide between.
        in_conflict = next(
            (c for c in conflicts if position.ziffer in (c.ziffer_a, c.ziffer_b)), None
        )

        if blocked is not None:
            row.verdict = "blocked"
            row.reason = blocked.explanation or blocked.detail or blocked.reason
            row.blocked_by = blocked.blocked_by
            row.legal_basis = blocked.legal_basis
            findings.append(
                PadnextFinding(
                    type=f"padnext_blocked_{blocked.reason}",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"GOÄ {position.ziffer} ist neben "
                        f"{'GOÄ ' + blocked.blocked_by if blocked.blocked_by else 'einer anderen Position'}"
                        f" nicht berechnungsfähig: {row.reason}"
                    ),
                    legal_basis=blocked.legal_basis,
                    rule_id=blocked.rule_id,
                )
            )
        elif position.ziffer in billable:
            row.verdict = "chargeable"
            row.proof = sorted(proof_by_ziffer.get(position.ziffer, []))
        elif in_conflict is not None:
            other = (
                in_conflict.ziffer_b
                if in_conflict.ziffer_a == position.ziffer
                else in_conflict.ziffer_a
            )
            row.verdict = "blocked"
            row.blocked_by = other
            row.reason = (
                f"GOÄ {position.ziffer} und GOÄ {other} schließen sich gegenseitig aus. Die "
                "Rechnung enthält beide; nur eine davon ist berechnungsfähig."
            )
            findings.append(
                PadnextFinding(
                    type="padnext_mutual_exclusion",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=row.reason,
                    legal_basis=in_conflict.legal_basis or "Leistungslegende GOÄ",
                    rule_id=in_conflict.rule_id,
                )
            )
        else:
            row.verdict = "blocked"
            row.reason = (
                "Die Regelprüfung hat diese Ziffer nicht als berechnungsfähig bestätigt. "
                "Es liegt keine spezifischere Begründung vor."
            )
            findings.append(
                PadnextFinding(
                    type="padnext_not_confirmed",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=row.reason,
                )
            )

        # -- factor band, § 5 / § 12 Abs. 3 ------------------------------------------------
        band = catalog.factor_band(position.ziffer)
        if position.faktor is not None:
            row.factor_within_band = position.faktor <= band.max
            row.legal_basis = row.legal_basis or band.legal_basis
            if position.faktor > band.max or position.ziffer in factor_invalid:
                findings.append(
                    PadnextFinding(
                        type="padnext_factor_above_maximum",
                        severity="error",
                        positionsnr=position.positionsnr,
                        ziffer=position.ziffer,
                        message=(
                            f"Faktor {position.faktor} überschreitet den Höchstsatz {band.max} "
                            f"für GOÄ {position.ziffer}."
                        ),
                        legal_basis=band.legal_basis or "§ 5 Abs. 1 GOÄ",
                        claimed=str(position.faktor),
                        recomputed=f"max {band.max}",
                    )
                )
            elif position.faktor > band.threshold:
                row.justification_required = True
                row.justification_present = bool(position.begruendung)
                if not position.begruendung:
                    findings.append(
                        PadnextFinding(
                            type="padnext_justification_missing",
                            severity="error",
                            positionsnr=position.positionsnr,
                            ziffer=position.ziffer,
                            message=(
                                f"Faktor {position.faktor} liegt über dem Schwellenwert "
                                f"{band.threshold}. § 12 Abs. 3 GOÄ verlangt eine schriftliche "
                                "Begründung; das Feld 'begruendung' ist leer."
                            ),
                            legal_basis="§ 12 Abs. 3 GOÄ",
                            claimed=str(position.faktor),
                        )
                    )
        elif position.einzelbetrag is None:
            findings.append(
                PadnextFinding(
                    type="padnext_no_faktor_or_einzelbetrag",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        "Position gibt weder faktor noch einzelbetrag an; der Betrag kann nicht "
                        "nachgerechnet werden."
                    ),
                )
            )

        if position.ziffer in needs_justification and not position.begruendung:
            row.justification_required = True

        # -- money -------------------------------------------------------------------------
        recomputed, _ = _recompute(position, catalog, setting)
        if recomputed is None:
            unpriceable_claimed += position.gesamtbetrag or Decimal("0.00")
        else:
            row.recomputed_amount_eur = recomputed
            recomputed_total += recomputed
            if position.gesamtbetrag is not None:
                comparable_claimed += position.gesamtbetrag
                delta = position.gesamtbetrag - recomputed
                row.amount_delta_eur = delta
                if delta != 0:
                    findings.append(
                        PadnextFinding(
                            type="padnext_amount_mismatch",
                            severity="error",
                            positionsnr=position.positionsnr,
                            ziffer=position.ziffer,
                            message=(
                                f"gesamtbetrag {position.gesamtbetrag} € weicht von der "
                                f"Nachrechnung {recomputed} € ab ({delta:+} €). Grundlage: "
                                f"{entry.punkte} Punkte × Faktor {position.faktor} × "
                                f"{catalog.punktwert_cent} ct."
                            ),
                            legal_basis="§ 5 Abs. 1 GOÄ",
                            claimed=f"{position.gesamtbetrag} €",
                            recomputed=f"{recomputed} €",
                        )
                    )

        if position.punktzahl is not None and position.punktzahl != entry.punkte:
            findings.append(
                PadnextFinding(
                    type="padnext_punktzahl_mismatch",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"punktzahl {position.punktzahl} weicht von der Katalog-Punktzahl "
                        f"{entry.punkte} für GOÄ {position.ziffer} ab."
                    ),
                    claimed=str(position.punktzahl),
                    recomputed=str(entry.punkte),
                )
            )

        if position.punktwert is not None and position.punktwert != catalog.punktwert_cent:
            findings.append(
                PadnextFinding(
                    type="padnext_punktwert_mismatch",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"punktwert {position.punktwert} weicht vom gesetzlichen Punktwert "
                        f"{catalog.punktwert_cent} ct ab."
                    ),
                    legal_basis="§ 5 Abs. 1 Satz 3 GOÄ",
                    claimed=str(position.punktwert),
                    recomputed=str(catalog.punktwert_cent),
                )
            )

        if position.is_analog:
            findings.append(
                PadnextFinding(
                    type="padnext_analog_needs_review",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"Position ist als Analogansatz zu GOÄ {position.analog_for} deklariert. "
                        "Ob die Gleichwertigkeit medizinisch trägt, ist eine ärztliche "
                        "Entscheidung und wird hier nicht geprüft."
                    ),
                    legal_basis="§ 6 Abs. 2 GOÄ",
                )
            )

        audited.append(row)

    # A line is billable as claimed only if the rules kept it AND nothing else about it is wrong.
    # Computing this after the loop is deliberate: an error finding can be raised about a position
    # after its verdict is set (an illegal factor, an amount that does not recompute), and a
    # single-pass version silently counted those euros as defensible.
    errors_per_position: dict[str, int] = {}
    for finding in findings:
        if finding.severity == "error" and finding.positionsnr:
            errors_per_position[finding.positionsnr] = (
                errors_per_position.get(finding.positionsnr, 0) + 1
            )

    defensible_total = Decimal("0.00")
    for row in audited:
        row.accepted_as_claimed = row.verdict == "chargeable" and not errors_per_position.get(
            row.positionsnr
        )
        if row.accepted_as_claimed and row.recomputed_amount_eur is not None:
            defensible_total += row.recomputed_amount_eur

    coverage = rule_coverage_service.build(
        rules,
        rule_coverage=catalog.rule_coverage,
        rules_version=catalog.rules_version,
    )
    findings.extend(
        PadnextFinding(type=w.type, severity=w.severity, message=w.message)
        for w in rule_coverage_service.warnings_for(coverage)
    )

    receipt = receipt_hash(
        catalog_version=catalog.catalog_version,
        catalog_sha256=catalog.sha256(),
        rules_version=catalog.rules_version,
        rules_hash=rule_coverage_service.rules_hash(settings.rules_data_dir),
        logic_version=settings.logic_version,
        solver_version=settings.clingo_version,
        policy=settings.policy_fingerprint(),
        facts=[p.model_dump(mode="python") for p in claimed],
        output=[r.model_dump(mode="python") for r in audited],
    )

    return PadnextAuditReport(
        source_name=delivery.source_name,
        nachrichtentyp=delivery.nachrichtentyp,
        echtdaten=delivery.echtdaten,
        setting=setting,
        setting_source=setting_source,
        positions=audited,
        findings=findings,
        claimed_total_eur=claimed_total,
        recomputed_total_eur=recomputed_total,
        comparable_claimed_eur=comparable_claimed,
        arithmetic_delta_eur=comparable_claimed - recomputed_total,
        defensible_total_eur=defensible_total,
        at_risk_eur=claimed_total - defensible_total,
        unpriceable_claimed_eur=unpriceable_claimed,
        catalog_version=catalog.catalog_version,
        catalog_sha256=catalog.sha256(),  # a method, unlike its neighbours, which are properties
        rules_version=catalog.rules_version,
        logic_version=settings.logic_version,
        enforced_rule_count=coverage.enforced_rule_count,
        advisory_rule_count=coverage.advisory_rule_count,
        suppressed_unverified_rule_count=coverage.suppressed_unverified_rule_count,
        rule_coverage_detail=coverage,
        receipt_hash=receipt,
    )
