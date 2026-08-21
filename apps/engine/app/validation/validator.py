"""Independent validation, exact money, and the audit trail.

Two things here are worth pointing at.

**It does not trust the layers above it.** Every hard rule the Datalog layer enforced is checked
again against the final invoice through a separate code path, and the Steigerungsfaktoren the
solver chose are fed *back into* Datalog so the rules engine rules on them independently. If the
two disagree, this module raises: the component that picks the number is not the component that
approves it, and a disagreement is a bug, not something to paper over.

**Money is exact.** ``Decimal`` throughout, with the rounding the law prescribes:

    Gebühr = Punktzahl x Punktwert x Steigerungsfaktor        (§ 5 Abs. 1 Satz 1-3 GOÄ)
    fractions below 0.5 down, 0.5 and above up                (§ 5 Abs. 1 Satz 4 GOÄ)

so ROUND_HALF_UP at cent granularity is statutory, not a house convention. Both the unrounded
cent amount and the rounded EUR amount are returned, so a reviewer can audit the rounding.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from app.bridge.entity_to_ziffer import BridgeResult, resolve_justifications
from app.catalog import Catalog, load_catalog
from app.config import Settings, get_settings
from app.schemas import (
    AuditTrail,
    AuditTrailEntry,
    ClinicalAct,
    ClinicalExtraction,
    CodeCandidate,
    Coding,
    InvoiceLine,
    OptimizationResult,
    ProofStep,
    RulesResult,
    Totals,
    ValidationViolation,
    Warning_,
)
from app.rules.rule_store import RuleStore, load_rules
from app.services import rule_coverage as rule_coverage_service

LOW_CONFIDENCE_THRESHOLD = Decimal("0.7")
CENT = Decimal("0.01")


class ValidationFailed(RuntimeError):
    """Independent validation contradicted the solver. Never swallowed."""

    def __init__(self, violations: list[ValidationViolation]) -> None:
        super().__init__(
            "validation_failed: " + "; ".join(f"{v.code}({v.ziffer or '-'})" for v in violations)
        )
        self.violations = violations


def line_amount_cent(punkte: int, factor: Decimal, punktwert_cent: Decimal) -> Decimal:
    """Gebühr in cents, unrounded. § 5 Abs. 1 Satz 1-3 GOÄ."""
    return Decimal(punkte) * Decimal(factor) * Decimal(punktwert_cent)


def cent_to_eur(cents: Decimal) -> Decimal:
    """§ 5 Abs. 1 Satz 4 GOÄ: half up, at cent granularity."""
    return (cents / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)


class Validator:
    def __init__(
        self,
        settings: Settings | None = None,
        catalog: Catalog | None = None,
        rules: RuleStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.catalog = catalog or load_catalog()
        self.rules = rules or load_rules()

    # -- verification input ----------------------------------------------------------------

    def build_verification_bridge(self, optimization: OptimizationResult) -> BridgeResult:
        """A synthetic bridge result containing exactly the final invoice.

        Re-running Datalog over this makes the rules engine reason about what is actually being
        charged, including analog positions, which were never candidates on the first pass.
        """
        verification = BridgeResult()
        charged = sorted(set(optimization.billed) | {a.ziffer for a in optimization.analogs})
        for index, ziffer in enumerate(charged, start=1):
            act_id = f"v{index}"
            verification.acts.append(
                ClinicalAct(
                    act_id=act_id,
                    entity_id=act_id,
                    source="procedure",
                    entity_type=f"final_invoice_line_{ziffer}",
                    description=f"Verifikation GOÄ {ziffer}",
                    confidence=Decimal("1"),
                )
            )
            verification.candidates.append(
                CodeCandidate(act_id=act_id, ziffer=ziffer, priority=100, confidence=Decimal("1"))
            )
        return verification

    # -- blocked-reason reconciliation -----------------------------------------------------

    @staticmethod
    def _reconcile_blocked(blocked, charged: set[str]):
        """Keep only blocking reasons whose blocker is on the final invoice.

        The layers interact: Nr. 5 can be suppressed during rule evaluation by a position that
        then loses an arbitration. "Blocked by GOÄ 7" would be a true statement about an
        intermediate step and a misleading one about the invoice, and pointing a Rechnungsprüfer
        at a code that is not on the bill is exactly the kind of audit trail that does not
        survive contact with one.

        If *every* blocker of a position fell away, the suppression has lost its basis and the
        position may well be chargeable — reported as a warning rather than silently reinstated.
        """
        issues: list[Warning_] = []
        losses = [b for b in blocked if b.reason == "conflict_lost"]
        rule_blocks = [b for b in blocked if b.reason != "conflict_lost"]

        by_ziffer: dict[str, list] = {}
        for entry in rule_blocks:
            by_ziffer.setdefault(entry.ziffer, []).append(entry)

        kept = []
        for ziffer, entries in by_ziffer.items():
            supported = [e for e in entries if e.blocked_by and e.blocked_by in charged]
            unsupported = [e for e in entries if e not in supported]
            for entry in supported:
                entry.reconciled_with_final_invoice = True
            if supported:
                kept.extend(supported)
                continue
            for entry in unsupported:
                entry.reconciled_with_final_invoice = False
            kept.extend(unsupported)
            if ziffer not in charged:
                blockers = ", ".join(sorted({e.blocked_by or "?" for e in entries}))
                issues.append(
                    Warning_(
                        type="blocking_basis_removed",
                        ziffer=ziffer,
                        severity="warning",
                        message=(
                            f"GOÄ {ziffer} wurde durch GOÄ {blockers} verdrängt, aber "
                            f"GOÄ {blockers} steht nicht auf der endgültigen Rechnung. "
                            f"GOÄ {ziffer} ist möglicherweise doch berechnungsfähig – bitte "
                            "manuell prüfen."
                        ),
                    )
                )
        for entry in losses:
            entry.reconciled_with_final_invoice = True

        return sorted(kept + losses, key=lambda b: (b.ziffer, b.reason)), issues

    # -- main entry point ------------------------------------------------------------------

    def build(
        self,
        extraction: ClinicalExtraction,
        rules_result: RulesResult,
        optimization: OptimizationResult,
        bridge: BridgeResult,
        *,
        verification: RulesResult | None = None,
        extraction_mode: str = "manual",
        extraction_model: str = "manual",
        souffle_version: str = "",
        clingo_version: str = "",
        logic_version: str = "",
        stage_timings_ms: dict[str, float] | None = None,
    ) -> tuple[Coding, AuditTrail]:
        violations: list[ValidationViolation] = []
        warnings: list[Warning_] = list(rules_result.warnings) + list(optimization.warnings)

        factor_by_ziffer = {f.ziffer: f for f in optimization.factors}
        analog_by_ziffer = {a.ziffer: a for a in optimization.analogs}
        charged = sorted(set(optimization.billed) | set(analog_by_ziffer))
        charged_set = set(charged)

        def fail(code: str, message: str, ziffer: str | None = None, basis: str = "") -> None:
            violations.append(
                ValidationViolation(code=code, message=message, ziffer=ziffer, legal_basis=basis)
            )

        # -- 1/2. every charged position exists and is active ------------------------------
        for ziffer in charged:
            entry = self.catalog.get(ziffer)
            if entry is None:
                fail("unknown_ziffer", f"GOÄ {ziffer} ist im geladenen Katalog nicht enthalten.", ziffer)
            elif not entry.is_active:
                fail("inactive_ziffer", f"GOÄ {ziffer} ist im Katalog nicht als aktiv geführt.", ziffer)

        # -- 3. exclusions, re-checked independently of Datalog ----------------------------
        for rule in self.rules.exclusions:
            if rule.from_ziffer in charged_set and rule.to_ziffer in charged_set:
                fail(
                    "exclusion_violation",
                    f"GOÄ {rule.from_ziffer} und GOÄ {rule.to_ziffer} stehen gemeinsam auf der "
                    f"Rechnung, obwohl Regel {rule.rule_id} das ausschließt.",
                    rule.to_ziffer,
                    rule.legal_basis,
                )

        # -- 4. Zielleistungsprinzip, re-checked -------------------------------------------
        for zrule in self.rules.zielleistung:
            if zrule.parent_ziffer in charged_set and zrule.child_ziffer in charged_set:
                fail(
                    "zielleistung_violation",
                    f"GOÄ {zrule.child_ziffer} ist Bestandteil der Zielleistung "
                    f"GOÄ {zrule.parent_ziffer} und darf nicht gesondert berechnet werden.",
                    zrule.child_ziffer,
                    zrule.legal_basis,
                )

        # -- 5. duplicates -----------------------------------------------------------------
        if len(charged) != len(charged_set):
            fail("duplicate_ziffer", "Eine Ziffer erscheint mehrfach auf der Rechnung.")

        # -- 6/7/8. factor bounds, § 12 Abs. 3, category caps ------------------------------
        for ziffer in charged:
            decision = factor_by_ziffer.get(ziffer)
            if decision is None:
                fail("missing_factor", f"Für GOÄ {ziffer} wurde kein Faktor bestimmt.", ziffer)
                continue
            band = self.catalog.factor_band(ziffer)
            cap = self.rules.factor_cap(ziffer)
            ceiling = min(band.max, cap.max_factor) if cap else band.max

            if decision.factor > ceiling:
                fail(
                    "factor_above_max",
                    f"GOÄ {ziffer}: Faktor {decision.factor} überschreitet den zulässigen "
                    f"Höchstwert {ceiling}.",
                    ziffer,
                    cap.legal_basis if cap else band.legal_basis,
                )
            if decision.factor < Decimal(1):
                fail(
                    "factor_below_einfachsatz",
                    f"GOÄ {ziffer}: Faktor {decision.factor} liegt unter dem Einfachsatz.",
                    ziffer,
                    "§ 5 Abs. 1 GOÄ",
                )
            if decision.factor > band.threshold and not decision.justification:
                fail(
                    "missing_justification",
                    f"GOÄ {ziffer}: Faktor {decision.factor} liegt über dem Schwellenwert "
                    f"{band.threshold}, es fehlt aber die schriftliche Begründung.",
                    ziffer,
                    "§ 12 Abs. 3 GOÄ",
                )

        # -- 9. second opinion from the rules engine ---------------------------------------
        if verification is not None:
            for ziffer in verification.factor_invalid:
                fail(
                    "factor_invalid_confirmed_by_rules_engine",
                    f"GOÄ {ziffer}: Die Regel-Engine bestätigt eine Überschreitung des "
                    "zulässigen Faktors.",
                    ziffer,
                    "§ 5 GOÄ",
                )
            for ziffer in verification.factor_needs_justification:
                decision = factor_by_ziffer.get(ziffer)
                if decision and not decision.justification:
                    fail(
                        "missing_justification_confirmed_by_rules_engine",
                        f"GOÄ {ziffer}: Die Regel-Engine verlangt für den gewählten Faktor eine "
                        "schriftliche Begründung; es liegt keine vor.",
                        ziffer,
                        "§ 12 Abs. 3 GOÄ",
                    )
            optimizer_view = {z for z, d in factor_by_ziffer.items() if d.justification_required}
            rules_view = set(verification.factor_needs_justification)
            for ziffer in sorted(optimizer_view ^ rules_view):
                fail(
                    "engine_disagreement",
                    f"GOÄ {ziffer}: Optimierer und Regel-Engine bewerten die "
                    "Begründungspflicht unterschiedlich.",
                    ziffer,
                )
            # The rules engine must agree that every charged position is chargeable.
            verified_chargeable = set(verification.billable) | set(
                verification.arbitration_candidates
            )
            for ziffer in charged:
                if ziffer not in verified_chargeable:
                    fail(
                        "not_chargeable_on_reverification",
                        f"GOÄ {ziffer} steht auf der Rechnung, wurde bei der unabhängigen "
                        "Nachprüfung durch die Regel-Engine aber nicht als abrechenbar bestätigt.",
                        ziffer,
                    )

        # A disagreement between the layers is a bug. Fail hard.
        if violations:
            raise ValidationFailed(violations)

        # -- 10. invoice lines and money ---------------------------------------------------
        setting = extraction.patient.setting
        minderung_rate = self.catalog.minderung_rate(setting)
        punktwert = self.catalog.punktwert_cent

        lines: list[InvoiceLine] = []
        total_punkte = 0
        total_cent_unrounded = Decimal(0)
        total_before = Decimal(0)
        total_after = Decimal(0)

        for ziffer in charged:
            entry = self.catalog.get(ziffer)
            decision = factor_by_ziffer[ziffer]
            analog = analog_by_ziffer.get(ziffer)
            assert entry is not None  # guaranteed by check 1

            exempt = self.catalog.minderung_exempt(ziffer)
            rate = Decimal(0) if exempt else minderung_rate

            gross_cent = line_amount_cent(entry.punkte, decision.factor, punktwert)
            net_cent = gross_cent * (Decimal(1) - rate)

            total_punkte += entry.punkte
            total_cent_unrounded += net_cent
            total_before += cent_to_eur(gross_cent)
            total_after += cent_to_eur(net_cent)

            steps = [s for s in rules_result.proof if s.ziffer == ziffer]
            if not steps and verification is not None:
                # An analog position was never a candidate on the first pass, so its proof comes
                # from the verification pass — it is auditable exactly like any other line.
                steps = [s for s in verification.proof if s.ziffer == ziffer]
            steps = [
                ProofStep(
                    ziffer=s.ziffer,
                    rule=(
                        "conflict_arbitration_won"
                        if s.rule == "conflict_pending_arbitration"
                        else s.rule
                    ),
                    detail=s.detail,
                    rule_id=s.rule_id,
                    legal_basis=s.legal_basis,
                )
                for s in steps
            ]
            if analog:
                steps.append(
                    ProofStep(
                        ziffer=ziffer,
                        rule="analogansatz",
                        detail=f"analog_for:{analog.entity_type}",
                        rule_id=analog.rule_id,
                        legal_basis=analog.legal_basis,
                    )
                )

            if not steps:
                fail("line_without_proof", f"GOÄ {ziffer} hat keinen Beweisbaum.", ziffer)

            confidence = max(
                (c.confidence for c in rules_result.proposed if c.ziffer == ziffer),
                default=analog.similarity if analog else Decimal("1"),
            )

            lines.append(
                InvoiceLine(
                    ziffer=ziffer,
                    official_text=entry.official_text,
                    punkte=entry.punkte,
                    category=entry.category,
                    factor=decision.factor,
                    factor_basis=decision.basis,
                    factor_legal_basis=decision.legal_basis,
                    justification_required=decision.justification_required,
                    justification_present=bool(decision.justification),
                    justification=decision.justification,
                    confidence=confidence,
                    status="billable_analog" if analog else "billable",
                    is_analog=analog is not None,
                    analog_for=analog.entity_type if analog else None,
                    amount_cent_unrounded=net_cent,
                    amount_eur=cent_to_eur(net_cent),
                    amount_eur_before_minderung=cent_to_eur(gross_cent),
                    minderung_applied=rate > 0,
                    proof=steps,
                    catalog_provenance=entry.provenance,
                    text_quality=entry.text_quality,
                )
            )

        if violations:
            raise ValidationFailed(violations)

        # -- 11. total equals the sum of the lines -----------------------------------------
        line_sum = sum((line.amount_eur for line in lines), Decimal(0))
        if line_sum != total_after:
            fail(
                "total_mismatch",
                f"Summe der Einzelbeträge ({line_sum}) weicht von der Gesamtsumme "
                f"({total_after}) ab.",
            )
            raise ValidationFailed(violations)

        totals = Totals(
            punkte=total_punkte,
            amount_cent_unrounded=total_cent_unrounded,
            # Quantised so an empty invoice reads "0.00" like every other amount. A monetary
            # field whose format depends on its value is a trap for whoever parses it.
            amount_eur_before_minderung=total_before.quantize(CENT),
            amount_eur=total_after.quantize(CENT),
            minderung_applied=minderung_rate > 0,
            minderung_rate=minderung_rate,
            punktwert_cent=punktwert,
            rounding_policy=self.catalog.rounding.get("policy", "ROUND_HALF_UP"),
            rounding_legal_basis=self.catalog.rounding.get("legal_basis", ""),
        )

        # -- 12. blocked reasons, reconciled with the final invoice ------------------------
        blocked_codes, reconciliation_warnings = self._reconcile_blocked(
            list(rules_result.blocked) + list(optimization.dropped), charged_set
        )
        warnings.extend(reconciliation_warnings)

        for entry in blocked_codes:
            if not entry.explanation:
                fail("blocked_without_reason", f"GOÄ {entry.ziffer} ist ohne Begründung gesperrt.")
        if violations:
            raise ValidationFailed(violations)

        # -- 13. advisory warnings ---------------------------------------------------------
        warnings.extend(self._coverage_warnings(charged))
        warnings.extend(self._advisory_warnings(extraction, bridge, rules_result, optimization, lines))
        if minderung_rate > 0:
            warnings.append(
                Warning_(
                    type="minderung_applied",
                    severity="info",
                    legal_basis="§ 6a Abs. 1 GOÄ",
                    message=(
                        f"Behandlungsart '{setting}': alle Gebühren wurden um "
                        f"{(minderung_rate * 100).normalize()} % gemindert."
                    ),
                )
            )

        coding = Coding(
            proposed_codes=lines,
            blocked_codes=blocked_codes,
            analog_codes=optimization.analogs,
            conflicts_arbitrated=rules_result.conflicts,
            warnings=warnings,
            # Surfaced, never acted on: the § 5 headroom the record does not support. See
            # app/solvers/clingo_solver.py::_missing_documentation.
            missing_documentation=list(optimization.missing_documentation),
            total=totals,
        )

        # -- 14. audit trail ----------------------------------------------------------------
        per_code: list[AuditTrailEntry] = []
        relevant = charged_set | {b.ziffer for b in blocked_codes}
        for ziffer in sorted(relevant):
            steps = [s for s in rules_result.proof if s.ziffer == ziffer]
            if not steps and verification is not None:
                steps = [s for s in verification.proof if s.ziffer == ziffer]
            per_code.append(AuditTrailEntry(ziffer=ziffer, steps=steps))

        audit = AuditTrail(
            extraction_mode=extraction_mode,
            extraction_model=extraction_model,
            extraction_confidence_avg=extraction.average_confidence(),
            catalog_version=self.catalog.catalog_version,
            catalog_source=self.catalog.source.url or self.catalog.source.name,
            catalog_sha256=self.catalog.sha256(),
            rule_coverage=self.catalog.rule_coverage,
            rules_version=self.catalog.rules_version,
            rules_engine_version=souffle_version,
            optimizer_version=clingo_version,
            logic_version=logic_version,
            unverified_rule_policy=str(self.settings.unverified_rule_policy),
            base_factor_policy=str(self.settings.base_factor_policy),
            llm_saw_goae_catalog=False,
            rule_summary=self.rules.summary(),
            rule_coverage_detail=rule_coverage_service.build(
                self.rules,
                rule_coverage=self.catalog.rule_coverage,
                rules_version=self.catalog.rules_version,
            ),
            solver_status=optimization.solver_status,
            timestamp=datetime.now(timezone.utc),
            per_code=per_code,
            stage_timings_ms=stage_timings_ms or {},
        )

        return coding, audit

    # -- warnings --------------------------------------------------------------------------

    def _coverage_warnings(self, charged: list[str]) -> list[Warning_]:
        """Say plainly where the encoded rule set is thinner than the law."""
        out: list[Warning_] = []
        summary = self.rules.summary()

        out.append(
            Warning_(
                type="rule_coverage_incomplete",
                severity="warning",
                message=(
                    f"Regelabdeckung ist unvollständig: {summary['exclusions_enforced']} "
                    f"Ausschlussregeln werden durchgesetzt, "
                    f"{summary['unverified_rules_not_enforced']} automatisch extrahierte Regeln "
                    f"sind NICHT verifiziert und wirken bei Policy "
                    f"'{summary['policy_for_unverified_rules']}' nicht blockierend. Die "
                    "Rechnung ist ein Vorschlag und ersetzt keine ärztliche Prüfung."
                ),
            )
        )

        if not self.rules.zielleistung:
            out.append(
                Warning_(
                    type="zielleistung_coverage_none",
                    severity="warning",
                    legal_basis="§ 4 Abs. 2a GOÄ",
                    message=(
                        "Es sind keine Zielleistungs-Regeln geladen. Das "
                        "Zielleistungsprinzip wird in der GOÄ überwiegend als allgemeiner "
                        "Grundsatz formuliert und nicht als maschinenlesbare Ziffernpaare; "
                        "die Rechnung wird daher NICHT auf Zielleistungsverstöße geprüft."
                    ),
                )
            )

        # Per-position: does the catalog claim full rule coverage for this Ziffer?
        for ziffer in charged:
            entry = self.catalog.get(ziffer)
            if entry and entry.rule_coverage != "full":
                out.append(
                    Warning_(
                        type="rule_coverage_incomplete",
                        ziffer=ziffer,
                        severity="info",
                        message=(
                            f"Die Ausschluss- und Bestandteilsregeln für GOÄ {ziffer} sind nur "
                            f"teilweise importiert (rule_coverage={entry.rule_coverage})."
                        ),
                    )
                )
            if entry and entry.text_quality != "ok":
                out.append(
                    Warning_(
                        type="catalog_text_quality",
                        ziffer=ziffer,
                        severity="warning",
                        message=(
                            f"Der Leistungstext für GOÄ {ziffer} wurde beim Import als "
                            f"'{entry.text_quality}' markiert (mehrzeilige Legende). Bitte "
                            "gegen die amtliche Fassung prüfen."
                        ),
                    )
                )
        return out

    def _advisory_warnings(
        self,
        extraction: ClinicalExtraction,
        bridge: BridgeResult,
        rules_result: RulesResult,
        optimization: OptimizationResult,
        lines: list[InvoiceLine],
    ) -> list[Warning_]:
        out: list[Warning_] = []

        _per, _enc, justification_warnings = resolve_justifications(extraction, bridge)
        out.extend(justification_warnings)

        charged = {line.ziffer for line in lines}
        for candidate in rules_result.proposed:
            if candidate.ziffer in charged and candidate.confidence < LOW_CONFIDENCE_THRESHOLD:
                out.append(
                    Warning_(
                        type="low_extraction_confidence",
                        ziffer=candidate.ziffer,
                        severity="warning",
                        message=(
                            f"GOÄ {candidate.ziffer} beruht auf einer Angabe mit Konfidenz "
                            f"{candidate.confidence} (< {LOW_CONFIDENCE_THRESHOLD}). Manuelle "
                            "Prüfung empfohlen."
                        ),
                    )
                )

        for analog in optimization.analogs:
            out.append(
                Warning_(
                    type="analogansatz_requires_human_review",
                    ziffer=analog.ziffer,
                    severity="warning",
                    rule_id=analog.rule_id,
                    legal_basis=analog.legal_basis,
                    message=(
                        f"'{analog.entity_type}' ist im Gebührenverzeichnis nicht enthalten und "
                        f"wird analog GOÄ {analog.ziffer} berechnet (Gleichwertigkeit "
                        f"{analog.similarity}). Die Rechnung muss die Analogziffer als solche "
                        "kennzeichnen und die Gleichwertigkeit begründen; die Auswahl ist "
                        "ÄRZTLICH ZU PRÜFEN."
                    ),
                )
            )

        for line in lines:
            if line.justification_required and not line.justification_present:
                out.append(
                    Warning_(
                        type="justification_missing",
                        ziffer=line.ziffer,
                        severity="error",
                        legal_basis="§ 12 Abs. 3 GOÄ",
                        message=f"GOÄ {line.ziffer}: Begründung erforderlich, aber nicht vorhanden.",
                    )
                )
        return out
