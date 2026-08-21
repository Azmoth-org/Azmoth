"""Clingo wrapper: resolve the choices Datalog left open.

Driven through the Python API so the program text, the grounding and the answer set stay in one
process and every failure surfaces as an exception with the program attached. The program itself is
`logic/asp/goae_optimize.lp`, resolved through `settings.asp_path` (`LOGIC_DIR`) — see
`logic/README.md` for why its objective ordering must not be changed without legal review.

**Solving is bounded.** `SOLVER_TIMEOUT_SECONDS` is a hard ceiling enforced with the asynchronous
solve handle: start, wait, cancel. There is no configuration in which the solver runs unbounded.
When the ceiling is reached the best model found so far is returned with
`solver_status="TIMEOUT_PARTIAL"` and a warning, and when no model was found at all the request
fails with `ClingoTimeout` rather than an empty invoice that looks like "nothing is chargeable".

Solving is CPU-bound, so callers must not run it on the event loop: the API routes that reach this
module are declared `def`, not `async def`, which puts them in FastAPI's threadpool.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal

import clingo

from app.bridge.entity_to_ziffer import BridgeResult, resolve_justifications
from app.catalog import Catalog, load_catalog
from app.config import BaseFactorPolicy, Settings, get_settings
from app.rules.rule_store import RuleStore, load_rules
from app.schemas import (
    AnalogDecision,
    BlockedCode,
    ClinicalExtraction,
    FactorDecision,
    OptimizationResult,
    RulesResult,
    Warning_,
)
from app.schemas.solver import MissingDocumentation
from app.solvers.souffle_facts import scale, unscale

log = logging.getLogger(__name__)

SEVERITY_RANK = {"leicht": 1, "mittel": 2, "schwer": 3}


class ClingoError(RuntimeError):
    def __init__(self, message: str, *, program: str = "") -> None:
        super().__init__(message)
        self.program = program


class ClingoTimeout(ClingoError):
    """The hard timeout expired before any answer set existed. Never returned as an invoice."""

    def __init__(self, timeout_seconds: float, *, program: str = "") -> None:
        super().__init__(
            f"The optimiser did not produce an answer set within {timeout_seconds}s. No invoice "
            "draft is returned: an empty result here would be indistinguishable from 'nothing is "
            "chargeable', which is a different and much more dangerous statement.",
            program=program,
        )
        self.timeout_seconds = timeout_seconds


def _q(value: str) -> str:
    """Quote a Ziffer as an ASP string term. Real GOÄ has positions like 'K1' and '437a', so
    Ziffern are strings throughout, never integers."""
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


class ClingoSolver:
    def __init__(
        self,
        settings: Settings | None = None,
        catalog: Catalog | None = None,
        rules: RuleStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.catalog = catalog or load_catalog()
        self.rules = rules or load_rules()
        self._per_ziffer_reasons: dict[str, list[tuple[str, str]]] = {}
        self._encounter_reasons: list[tuple[str, str]] = []

    @property
    def version(self) -> str:
        return clingo.__version__

    @property
    def timeout_seconds(self) -> float:
        return float(self.settings.solver_timeout_seconds)

    # -- fact generation -------------------------------------------------------------------

    def build_facts(
        self,
        rules_result: RulesResult,
        extraction: ClinicalExtraction,
        bridge: BridgeResult,
    ) -> str:
        lines: list[str] = ["% ---- injected facts ----"]

        analog_ziffern: set[str] = set()
        for request in rules_result.analog_requests:
            for candidate in self.rules.analog_for(request.entity_type):
                if self.catalog.is_active(candidate.target_ziffer):
                    analog_ziffern.add(candidate.target_ziffer)

        in_play = (
            set(rules_result.billable)
            | set(rules_result.arbitration_candidates)
            | analog_ziffern
        )

        for ziffer in sorted(in_play):
            entry = self.catalog.get(ziffer)
            if entry is None:
                continue
            lines.append(
                f"code_info({_q(ziffer)}, {entry.punkte}, {_q(entry.category or 'UNKNOWN')})."
            )
            band = self.catalog.factor_band(ziffer)
            lines.append(f"sf({_q(ziffer)}, {scale(band.threshold)}, {scale(band.max)}).")
            if cap := self.rules.factor_cap(ziffer):
                lines.append(f"cap({_q(ziffer)}, {scale(cap.max_factor)}).")

        # Evidence and specificity per proposed position: the strongest candidate wins.
        best_conf: dict[str, Decimal] = {}
        best_priority: dict[str, int] = {}
        for candidate in rules_result.proposed:
            z = candidate.ziffer
            best_conf[z] = max(best_conf.get(z, Decimal(0)), candidate.confidence)
            best_priority[z] = max(best_priority.get(z, 0), candidate.priority)
        for ziffer in sorted(in_play):
            if ziffer in best_conf:
                lines.append(f"conf({_q(ziffer)}, {scale(best_conf[ziffer])}).")
                lines.append(f"spec_priority({_q(ziffer)}, {best_priority[ziffer]}).")

        for ziffer in rules_result.billable:
            lines.append(f"fixed({_q(ziffer)}).")
        for ziffer in rules_result.arbitration_candidates:
            lines.append(f"arbitrate({_q(ziffer)}).")
        for conflict in rules_result.conflicts:
            lines.append(f"conflict_pair({_q(conflict.ziffer_a)}, {_q(conflict.ziffer_b)}).")

        for request in rules_result.analog_requests:
            lines.append(f"analog_needed({_q(request.act_id)}, {_q(request.entity_type)}).")
            for candidate in self.rules.analog_for(request.entity_type):
                if candidate.target_ziffer in analog_ziffern:
                    lines.append(
                        f"analog_cand({_q(request.act_id)}, {_q(candidate.target_ziffer)}, "
                        f"{scale(candidate.similarity)})."
                    )

        for rule in self.rules.exclusions:
            if rule.from_ziffer in in_play and rule.to_ziffer in in_play:
                lines.append(f"excluded({_q(rule.from_ziffer)}, {_q(rule.to_ziffer)}).")
        for rule in self.rules.zielleistung:
            if rule.parent_ziffer in in_play and rule.child_ziffer in in_play:
                lines.append(f"zielleistung({_q(rule.parent_ziffer)}, {_q(rule.child_ziffer)}).")

        per_ziffer, encounter, _warnings = resolve_justifications(extraction, bridge)
        self._per_ziffer_reasons = per_ziffer
        self._encounter_reasons = encounter
        for ziffer, factors in sorted(per_ziffer.items()):
            for severity, _reason in factors:
                lines.append(f"justification({_q(ziffer)}, {SEVERITY_RANK[severity]}).")
        for severity, _reason in encounter:
            lines.append(f"encounter_justification({SEVERITY_RANK[severity]}).")

        policy = (
            "einfachsatz"
            if self.settings.base_factor_policy is BaseFactorPolicy.EINFACHSATZ
            else "schwellenwert"
        )
        lines.append(f"base_policy({policy}).")
        return "\n".join(lines) + "\n"

    # -- solving ---------------------------------------------------------------------------

    def solve(
        self,
        rules_result: RulesResult,
        extraction: ClinicalExtraction,
        bridge: BridgeResult,
    ) -> OptimizationResult:
        self._precheck(rules_result)

        facts = self.build_facts(rules_result, extraction, bridge)
        asp_path = self.settings.asp_path
        if not asp_path.is_file():
            raise ClingoError(
                f"ASP program not found at {asp_path}. It lives in the monorepo's logic/asp/ "
                "directory; set LOGIC_DIR if it is elsewhere."
            )
        program = asp_path.read_text(encoding="utf-8") + "\n" + facts

        ctl = clingo.Control(["--models=0", "--opt-mode=opt"])
        try:
            ctl.add("base", [], program)
            ctl.ground([("base", [])])
        except RuntimeError as exc:
            raise ClingoError(f"ASP program failed to ground: {exc}", program=program) from exc

        best: list[clingo.Symbol] | None = None
        cost: list[int] = []
        count = 0

        def on_model(model: clingo.Model) -> None:
            # Under --opt-mode=opt models arrive in improving order, so the last one seen is the
            # best found so far. Captured eagerly, which is what makes a cancelled solve able to
            # return a usable — if unproven — result instead of nothing.
            nonlocal best, cost, count
            best = model.symbols(shown=True)
            cost = list(model.cost)
            count += 1

        started = time.perf_counter()
        timed_out = False
        with ctl.solve(on_model=on_model, async_=True) as handle:
            if not handle.wait(self.timeout_seconds):
                handle.cancel()
                timed_out = True
            status = str(handle.get())
        solve_ms = round((time.perf_counter() - started) * 1000, 2)

        if best is None:
            if timed_out:
                log.error("clingo timed out after %ss with no answer set", self.timeout_seconds)
                raise ClingoTimeout(self.timeout_seconds, program=program)
            raise ClingoError(
                "ASP program has no answer set: the hard constraints are unsatisfiable for this "
                "input, which means the enforced rule set contradicts itself for the proposed "
                "positions.",
                program=program,
            )

        if timed_out:
            log.warning(
                "clingo cancelled after %ss; returning the best of %d model(s) found",
                self.timeout_seconds,
                count,
            )
            status = "TIMEOUT_PARTIAL"

        result = self._parse_model(best, rules_result, cost, count, status)
        result.solve_ms = solve_ms
        result.timed_out = timed_out
        if timed_out:
            result.warnings.append(
                Warning_(
                    type="solver_timeout_partial",
                    severity="warning",
                    message=(
                        f"Der Optimierer wurde nach {self.timeout_seconds} s abgebrochen. "
                        f"Zurückgegeben wird das beste bis dahin gefundene Modell von {count}; "
                        "Optimalität ist NICHT bewiesen. Jede harte Regel (Ausschluss, "
                        "Zielleistung, Faktorgrenzen) gilt unverändert – nur die Auswahl unter "
                        "gleich zulässigen Alternativen ist möglicherweise nicht die beste."
                    ),
                )
            )
        return result

    def _precheck(self, rules_result: RulesResult) -> None:
        """Catch a contradictory rule set before the solver turns it into a bare UNSAT."""
        fixed = set(rules_result.billable)
        for rule in self.rules.exclusions:
            if rule.from_ziffer in fixed and rule.to_ziffer in fixed:
                raise ClingoError(
                    f"Rule set inconsistency: GOÄ {rule.from_ziffer} and GOÄ {rule.to_ziffer} "
                    f"were both proved chargeable by the rules engine, but rule "
                    f"{rule.rule_id} excludes the second given the first. The exclusion is "
                    "probably declared one-way where it should be mutual."
                )

    def _parse_model(
        self,
        symbols: list[clingo.Symbol],
        rules_result: RulesResult,
        cost: list[int],
        count: int,
        status: str,
    ) -> OptimizationResult:
        billed: set[str] = set()
        factors: dict[str, int] = {}
        analogs: dict[str, str] = {}
        justification_required: set[str] = set()
        bad: list[str] = []
        collisions: list[tuple[str, str]] = []

        for symbol in symbols:
            name, args = symbol.name, symbol.arguments
            if name == "bill":
                billed.add(args[0].string)
            elif name == "factor":
                factors[args[0].string] = args[1].number
            elif name == "analog":
                analogs[args[0].string] = args[1].string
            elif name == "justification_required":
                justification_required.add(args[0].string)
            elif name == "factor_count_bad":
                bad.append(args[0].string)
            elif name == "analog_collision":
                collisions.append((args[0].string, args[1].string))

        if bad:
            raise ClingoError(
                f"Internal inconsistency: no unique Steigerungsfaktor was derived for "
                f"GOÄ {', '.join(sorted(bad))}. The factor ladder in goae_optimize.lp is "
                "incomplete or overlapping for these positions."
            )

        result = OptimizationResult(
            billed=sorted(billed),
            objective=cost,
            models_enumerated=count,
            solver_status=status,
        )

        # Positions that lost an arbitration.
        for ziffer in rules_result.arbitration_candidates:
            if ziffer in billed:
                continue
            winner = next(
                (
                    other
                    for conflict in rules_result.conflicts
                    for other in (conflict.ziffer_a, conflict.ziffer_b)
                    if ziffer in (conflict.ziffer_a, conflict.ziffer_b)
                    and other != ziffer
                    and other in billed
                ),
                None,
            )
            entry = self.catalog.get(ziffer)
            rule = next(
                (
                    c.rule_id
                    for c in rules_result.conflicts
                    if ziffer in (c.ziffer_a, c.ziffer_b)
                ),
                "",
            )
            result.dropped.append(
                BlockedCode(
                    ziffer=ziffer,
                    official_text=entry.official_text if entry else "",
                    reason="conflict_lost",
                    detail=f"blocked_by:{winner}" if winner else "not_selected",
                    blocked_by=winner,
                    rule_id=rule,
                    legal_basis=(
                        r.legal_basis if (r := self.rules.rule_by_id(rule)) is not None else ""
                    ),
                    explanation=(
                        f"GOÄ {ziffer} konkurriert wechselseitig mit GOÄ {winner}. Der "
                        f"Optimierer hat GOÄ {winner} gewählt, weil diese Position im Befund "
                        "besser belegt bzw. spezifischer ist – die Entscheidung folgt der "
                        "Dokumentationslage, nicht der Honorarhöhe."
                    )
                    if winner
                    else f"GOÄ {ziffer} wurde nicht abgerechnet.",
                )
            )

        # Analog decisions.
        for act_id, ziffer in sorted(analogs.items()):
            request = next(
                (r for r in rules_result.analog_requests if r.act_id == act_id), None
            )
            entity_type = request.entity_type if request else act_id
            candidate = next(
                (c for c in self.rules.analog_for(entity_type) if c.target_ziffer == ziffer),
                None,
            )
            result.analogs.append(
                AnalogDecision(
                    act_id=act_id,
                    entity_type=entity_type,
                    ziffer=ziffer,
                    similarity=candidate.similarity if candidate else Decimal(0),
                    rule_id=candidate.rule_id if candidate else "",
                    legal_basis=candidate.legal_basis if candidate else "§ 6 Abs. 2 GOÄ",
                    quote=candidate.quote if candidate else "",
                    requires_human_review=True,
                )
            )

        # Factor decisions for everything on the invoice.
        charged = sorted(billed | set(analogs.values()))
        for ziffer in charged:
            entry = self.catalog.get(ziffer)
            if entry is None:
                continue
            band = self.catalog.factor_band(ziffer)
            factor = unscale(factors[ziffer]) if ziffer in factors else Decimal(1)
            cap = self.rules.factor_cap(ziffer)

            if cap and factor >= cap.max_factor:
                basis = "capped"
            elif factor >= band.max:
                basis = "hoechstsatz"
            elif factor > band.threshold:
                basis = "ueber_schwellenwert"
            elif factor == band.threshold:
                basis = "schwellenwert"
            else:
                basis = "einfachsatz"

            reasons = [r for _s, r in self._per_ziffer_reasons.get(ziffer, [])]
            reasons += [r for _s, r in self._encounter_reasons]
            result.factors.append(
                FactorDecision(
                    ziffer=ziffer,
                    factor=factor,
                    basis=basis,  # type: ignore[arg-type]
                    threshold=band.threshold,
                    max_factor=cap.max_factor if cap else band.max,
                    justification_required=ziffer in justification_required,
                    justification="; ".join(reasons) if reasons else None,
                    legal_basis=cap.legal_basis if cap else band.legal_basis,
                )
            )

        result.total_punkte = sum(
            entry.punkte for z in charged if (entry := self.catalog.get(z)) is not None
        )
        result.missing_documentation = self._missing_documentation(result)

        for act_id, ziffer in collisions:
            message = (
                f"Analogansatz-Kollision: Die als Analogziffer gewählte GOÄ {ziffer} wird "
                f"bereits direkt abgerechnet (Akt {act_id}). Es existiert kein kollisionsfreier "
                "Analogkandidat – bitte manuell prüfen."
            )
            log.warning(message)
            result.warnings.append(
                Warning_(type="analog_collision", ziffer=ziffer, severity="warning", message=message)
            )

        return result

    # -- documentation gaps ----------------------------------------------------------------

    def _missing_documentation(self, result: OptimizationResult) -> list[MissingDocumentation]:
        """The gap between what was documented and what the § 5 band would allow.

        Read only off decisions the solver already made — the chosen factor, the band, the cap and
        whether a written reason is present. The objective is not consulted and not changed: this
        says "the record does not support more", never "charge more". A physician who did in fact
        document a difficulty can then say so and re-run; one who did not, cannot.
        """
        out: list[MissingDocumentation] = []
        for decision in result.factors:
            ceiling = decision.max_factor
            if decision.justification_required and not decision.justification:
                # Reachable only if a policy change let a factor above the Schwellenwert through
                # without a reason; the validator refuses such an invoice outright. Reported here
                # so the gap is named rather than only rejected.
                out.append(
                    MissingDocumentation(
                        ziffer=decision.ziffer,
                        current_factor=str(decision.factor),
                        possible_factor=str(decision.factor),
                        missing=(
                            f"Der angesetzte Faktor {decision.factor} liegt über dem "
                            f"Schwellenwert {decision.threshold}, es liegt aber keine "
                            "schriftliche Begründung vor (§ 12 Abs. 3 GOÄ)."
                        ),
                    )
                )
                continue
            if decision.justification or decision.factor >= ceiling:
                continue
            out.append(
                MissingDocumentation(
                    ziffer=decision.ziffer,
                    current_factor=str(decision.factor),
                    possible_factor=str(ceiling),
                    missing=(
                        f"Es ist keine besondere Schwierigkeit, kein erhöhter Zeitaufwand und "
                        f"keine erschwerende Umstände dokumentiert. Der Faktor bleibt daher bei "
                        f"{decision.factor}. § 5 Abs. 2 GOÄ erlaubt bis {ceiling}, sofern eine "
                        "schriftliche Begründung nach § 12 Abs. 3 GOÄ vorliegt — diese kann und "
                        "darf nur der behandelnde Arzt formulieren."
                    ),
                )
            )
        return sorted(out, key=lambda m: m.ziffer)
