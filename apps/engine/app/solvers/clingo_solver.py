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
from app.errors import EngineError, ErrorCode, SolverTimeoutError
from app.rules.rule_store import RuleStore, load_rules
from app.schemas import (
    AnalogDecision,
    BlockedCode,
    ClinicalExtraction,
    FactorDecision,
    GroundingStats,
    OptimizationResult,
    ProofStep,
    RulesResult,
    Warning_,
)
from app.schemas.solver import MissingDocumentation
from app.solvers.souffle_facts import scale, unscale

log = logging.getLogger(__name__)

SEVERITY_RANK = {"leicht": 1, "mittel": 2, "schwer": 3}


class ClingoError(EngineError, RuntimeError):
    """The optimiser could not answer. `500 SOLVER_FAILED` — an engine defect, not a bad request.

    The program text travels on the exception but **not** into `details`: it is the encoding plus
    every injected fact, which is both large and the most sensitive thing in the process. It goes
    to the log for whoever debugs it, never to the caller.
    """

    error_code = ErrorCode.SOLVER_FAILED
    http_status = 500

    def __init__(self, message: str, *, program: str = "", details: dict | None = None) -> None:
        super().__init__(message, details=details)
        self.program = program


class ClingoTimeout(ClingoError, SolverTimeoutError):
    """The hard timeout expired before any answer set existed. Never returned as an invoice.

    `504`, inherited from `SolverTimeoutError`, rather than the `500` its other parent carries: the
    engine did not fail, it ran out of the time it was given. `details` says how long that was and
    how many models had been found — which for this exception is always zero, because a solve that
    *did* find one returns a normal 200 with `solver_status="TIMEOUT_PARTIAL"` instead of raising.
    That is the partial-result path, and it is the reason this exception is narrow.
    """

    #: Stated rather than inherited. `ClingoError` precedes `SolverTimeoutError` in the MRO, so
    #: without these two lines a timeout would render as its parent's 500 — which is exactly the
    #: distinction this class exists to make.
    error_code = ErrorCode.SOLVER_TIMEOUT
    http_status = 504

    def __init__(
        self, timeout_seconds: float, *, program: str = "", positions_in_play: int = 0
    ) -> None:
        super().__init__(
            f"The optimiser did not produce an answer set within {timeout_seconds}s. No invoice "
            "draft is returned: an empty result here would be indistinguishable from 'nothing is "
            "chargeable', which is a different and much more dangerous statement.",
            program=program,
            details={
                "timeout_seconds": timeout_seconds,
                "models_found": 0,
                "partial_result_available": False,
                "positions_in_play": positions_in_play,
            },
        )
        self.timeout_seconds = timeout_seconds


def _q(value: str) -> str:
    """Quote a Ziffer as an ASP string term. Real GOÄ has positions like 'K1' and '437a', so
    Ziffern are strings throughout, never integers."""
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def _grounding_stats(
    ctl: clingo.Control, *, program: str, facts: str
) -> GroundingStats | None:
    """Read the ground-program size off clingo's own statistics.

    Available on `Control.statistics` after a solve without passing `--stats`; the extra flag only
    raises the *detail* level, and nothing below is in the detailed-only set. Wrapped defensively
    all the same: these numbers are diagnostics, and a clingo release that renames a key must not
    be able to fail a solve that already produced a correct invoice.
    """
    try:
        stats = ctl.statistics
        lp = stats["problem"]["lp"]
        solvers = stats.get("solving", {}).get("solvers", {})
        return GroundingStats(
            atoms=int(lp["atoms"]),
            atoms_aux=int(lp["atoms_aux"]),
            bodies=int(lp["bodies"]),
            rules=int(lp["rules"]),
            rules_choice=int(lp["rules_choice"]),
            rules_minimize=int(lp["rules_minimize"]),
            choices=int(solvers.get("choices", 0)),
            conflicts=int(solvers.get("conflicts", 0)),
            program_bytes=len(program.encode("utf-8")),
            fact_lines=sum(1 for line in facts.splitlines() if line and not line.startswith("%")),
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must never fail a valid solve
        log.debug("clingo statistics unavailable: %s", exc)
        return None


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
        #: The ground-program size of the most recent solve, for `engine_cli solve --stats`.
        #:
        #: A profiling hook, not a result: last-run-wins, so under concurrent solves it names
        #: whichever finished last and must not be read by anything that decides an invoice. The
        #: same numbers reach the pipeline properly, on `OptimizationResult.grounding`; this exists
        #: because the CLI holds a proposal, and grounding statistics are deliberately not part of
        #: the response payload a client receives.
        self.last_grounding: GroundingStats | None = None

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

        build_started = time.perf_counter()
        facts = self.build_facts(rules_result, extraction, bridge)
        build_ms = round((time.perf_counter() - build_started) * 1000, 2)
        asp_path = self.settings.asp_path
        if not asp_path.is_file():
            raise ClingoError(
                f"ASP program not found at {asp_path}. It lives in the monorepo's logic/asp/ "
                "directory; set LOGIC_DIR if it is elsewhere."
            )
        program = asp_path.read_text(encoding="utf-8") + "\n" + facts

        ctl = clingo.Control(["--models=0", "--opt-mode=opt"])
        # Grounding is timed on its own because it is the half that scales with the *data*: the
        # encoding is fixed, the number of positions in play is not, and a rule with two unbound
        # Ziffer variables instantiates quadratically in it. A single "clingo took 40 ms" number
        # cannot tell that apart from a hard search, and the two have opposite remedies.
        ground_started = time.perf_counter()
        try:
            ctl.add("base", [], program)
            ctl.ground([("base", [])])
        except RuntimeError as exc:
            raise ClingoError(f"ASP program failed to ground: {exc}", program=program) from exc
        ground_ms = round((time.perf_counter() - ground_started) * 1000, 2)

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
                raise ClingoTimeout(
                    self.timeout_seconds,
                    program=program,
                    positions_in_play=len(
                        set(rules_result.billable) | set(rules_result.arbitration_candidates)
                    ),
                )
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
        result.build_ms = build_ms
        result.ground_ms = ground_ms
        result.grounding = _grounding_stats(ctl, program=program, facts=facts)
        self.last_grounding = result.grounding
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
        #: (act, candidate, blocker, relation) — candidates the final invoice ruled out.
        analog_blocked: list[tuple[str, str, str, str]] = []
        uncovered: list[str] = []

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
            elif name == "analog_blocked":
                analog_blocked.append(
                    (args[0].string, args[1].string, args[2].string, args[3].string)
                )
            elif name == "analog_uncovered":
                uncovered.append(args[0].string)

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

        # Positions that lost an arbitration. `charged`, not `billed`: a member of a mutual cluster
        # that the solver did not bill directly can still be on the invoice as the § 6 Abs. 2
        # Analogziffer for some other service, and a position that is being charged has not lost
        # anything. Reporting it as `conflict_lost` would put the same Ziffer on the invoice and in
        # the blocked list at once — two contradictory statements in one audit trail.
        charged_ziffern = billed | set(analogs.values())
        for ziffer in rules_result.arbitration_candidates:
            if ziffer in charged_ziffern:
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

        # Analog candidates the invoice ruled out, and § 6 Abs. 2 requests it could not cover.
        result.dropped.extend(
            self._analog_blocked_codes(analog_blocked, rules_result, result, charged_ziffern)
        )
        for act_id in sorted(set(uncovered)):
            request = next(
                (r for r in rules_result.analog_requests if r.act_id == act_id), None
            )
            entity_type = request.entity_type if request else act_id
            message = (
                f"Analogansatz nicht möglich: Für die Leistung '{entity_type}' (Akt {act_id}) "
                "ist keiner der Analogkandidaten neben den übrigen abgerechneten Positionen "
                "berechnungsfähig (§ 6 Abs. 2 GOÄ). Die Leistung bleibt unabgerechnet – bitte "
                "manuell prüfen."
            )
            log.warning(message)
            result.warnings.append(
                Warning_(
                    type="analog_uncovered",
                    severity="warning",
                    legal_basis="§ 6 Abs. 2 GOÄ",
                    message=message,
                )
            )

        # Factor decisions for everything on the invoice.
        charged = sorted(charged_ziffern)
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

    # -- the § 6 Abs. 2 ladder's rejected rungs ---------------------------------------------

    def _analog_blocked_codes(
        self,
        blocked: list[tuple[str, str, str, str]],
        rules_result: RulesResult,
        result: OptimizationResult,
        charged: set[str],
    ) -> list[BlockedCode]:
        """Analogansatz candidates the final invoice ruled out, as reported blocked positions.

        These are the rungs of a § 6 Abs. 2 ladder that the two legality constraints in
        `goae_optimize.lp` eliminated: a candidate that is not chargeable next to a position the
        invoice actually carries. Before those constraints ranged over `charged/1` the solver could
        pick such a candidate, and the validator refused the whole invoice — so this reports the
        *reason* a closer candidate was passed over, which is the question a Rechnungsprüfer asks
        about an Analogansatz.

        The proof atom is built here rather than read out of a Datalog relation because an analog
        candidate was never proposed to the rules engine: it has no row in either proof relation,
        and `Validator.build` keeps this one instead of overwriting it with an empty list.

        Nothing already reported blocked is reported twice — a candidate Ziffer can equally have
        been proposed directly and suppressed by Datalog, and one position with two blocking
        stories in one response is worse than either alone.
        """
        already = {entry.ziffer for entry in rules_result.blocked} | {
            entry.ziffer for entry in result.dropped
        }
        out: dict[str, BlockedCode] = {}
        for _act_id, ziffer, blocker, relation in sorted(blocked):
            if ziffer in already or ziffer in charged or ziffer in out:
                continue
            entry = self.catalog.get(ziffer)
            if relation == "zielleistung":
                rule = self.rules.zielleistung_rule(blocker, ziffer) or (
                    self.rules.zielleistung_rule(ziffer, blocker)
                )
                explanation = (
                    f"GOÄ {ziffer} käme als Analogziffer (§ 6 Abs. 2 GOÄ) in Betracht, ist aber "
                    f"methodisch notwendiger Bestandteil der abgerechneten GOÄ {blocker} und "
                    "daher nicht daneben berechnungsfähig (§ 4 Abs. 2a GOÄ)."
                )
            else:
                rule = self.rules.exclusion_rule(ziffer, blocker) or (
                    self.rules.exclusion_rule(blocker, ziffer)
                )
                explanation = (
                    f"GOÄ {ziffer} käme als Analogziffer (§ 6 Abs. 2 GOÄ) in Betracht, ist aber "
                    f"neben der abgerechneten GOÄ {blocker} nicht berechnungsfähig. Der "
                    "Analogansatz weicht deshalb auf einen anderen Kandidaten aus."
                )
            rule_id = rule.rule_id if rule is not None else ""
            legal_basis = rule.legal_basis if rule is not None else ""
            out[ziffer] = BlockedCode(
                ziffer=ziffer,
                official_text=entry.official_text if entry else "",
                reason="zielleistung" if relation == "zielleistung" else "exclusion",
                detail=f"analog_candidate_blocked_by:{blocker}",
                blocked_by=blocker,
                rule_id=rule_id,
                legal_basis=legal_basis,
                explanation=explanation,
                proof=[
                    ProofStep(
                        ziffer=ziffer,
                        rule="analog_candidate_blocked",
                        detail=blocker,
                        rule_id=rule_id,
                        legal_basis=legal_basis,
                    )
                ],
            )
        return list(out.values())

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
