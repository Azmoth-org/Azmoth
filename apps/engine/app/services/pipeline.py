"""The pipeline.

    clinical entities (JSON)
        -> [bridge]     candidate Ziffern              (deterministic CSV lookup)
        -> [Soufflé]    what is certainly chargeable    (stratified Datalog, explainable)
        -> [Clingo]     what requires a choice          (ASP, legality hard-constrained, bounded)
        -> [Soufflé]    independent re-check of the chosen factors
        -> [validator]  independent re-check, exact money, audit trail
        -> [proposal]   DRAFT, receipted, awaiting a human

No model runs on this path and none is required anywhere in the configuration. Every result is a
`Proposal` in status `DRAFT`: the engine proposes, a physician approves.

The pipeline is CPU-bound throughout (two subprocess/solver calls), so it is a synchronous API.
Callers on the event loop must not await it — the HTTP routes are declared `def` so FastAPI runs
them in its threadpool.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from app.bridge.entity_to_ziffer import BridgeResult, map_extraction
from app.catalog import Catalog, load_catalog
from app.config import Settings, get_settings
from app.rules.rule_store import RuleStore, load_rules
from app.schemas import (
    AuditTrail,
    ClinicalExtraction,
    Coding,
    CodingResponse,
    OptimizationResult,
    Proposal,
    ProposalStatus,
    RuleCoverage,
    RulesResult,
    Setting,
)
from app.services import rule_coverage as rule_coverage_service
from app.services.cache import InMemoryLRU, ResultCache, cache_key
from app.services.cache import entry as cache_entry
from app.services.receipt import receipt_hash
from app.solvers.clingo_solver import ClingoSolver
from app.solvers.souffle_engine import SouffleEngine
from app.validation.validator import Validator

log = logging.getLogger(__name__)


@dataclass
class StageTimer:
    timings: dict[str, float] = field(default_factory=dict)

    def time(self, name: str):
        timer = self

        class _Ctx:
            def __enter__(self) -> None:
                self.start = time.perf_counter()

            def __exit__(self, *exc) -> None:
                timer.timings[name] = round((time.perf_counter() - self.start) * 1000, 2)

        return _Ctx()


class Pipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        catalog: Catalog | None = None,
        rules: RuleStore | None = None,
        cache: ResultCache | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.catalog = catalog or load_catalog(self.settings.catalog_path)
        self.rules = rules or load_rules(
            self.settings.rules_data_dir, policy=self.settings.unverified_rule_policy
        )
        self.souffle = SouffleEngine(self.settings, self.catalog, self.rules)
        self.clingo = ClingoSolver(self.settings, self.catalog, self.rules)
        self.validator = Validator(self.settings, self.catalog, self.rules)
        self.cache = cache or ResultCache(
            InMemoryLRU(self.settings.cache_max_entries),
            enabled=self.settings.cache_enabled,
        )
        #: Hashed once per process: the rule CSVs do not change under a running service, and
        #: hashing 260 kB of CSV on every request would dominate a 30 ms solve.
        self._rules_hash = rule_coverage_service.rules_hash(self.settings.rules_data_dir)

    # -- identity ---------------------------------------------------------------------------

    @property
    def rules_hash(self) -> str:
        return self._rules_hash

    def rule_coverage(self) -> RuleCoverage:
        return rule_coverage_service.build(
            self.rules,
            rule_coverage=self.catalog.rule_coverage,
            rules_version=self.catalog.rules_version,
        )

    def _identity(self) -> dict[str, str]:
        return {
            "catalog_version": self.catalog.catalog_version,
            "catalog_sha256": self.catalog.sha256(),
            "rules_version": self.catalog.rules_version,
            "rules_hash": self._rules_hash,
            "logic_version": self.settings.logic_version,
            "solver_version": self.clingo.version,
            "rules_engine_version": self.souffle.version(),
        }

    # -- individual stages -----------------------------------------------------------------

    def bridge(self, extraction: ClinicalExtraction) -> BridgeResult:
        return map_extraction(extraction, self.catalog, self.rules)

    def apply_rules(
        self,
        extraction: ClinicalExtraction,
        bridge: BridgeResult,
        proposed_factors: dict[str, Decimal] | None = None,
    ) -> RulesResult:
        return self.souffle.run(extraction, bridge, proposed_factors=proposed_factors)

    def optimize(
        self, rules_result: RulesResult, extraction: ClinicalExtraction, bridge: BridgeResult
    ) -> OptimizationResult:
        return self.clingo.solve(rules_result, extraction, bridge)

    # -- the coding path --------------------------------------------------------------------

    def run(
        self, extraction: ClinicalExtraction, *, setting: Setting | None = None
    ) -> CodingResponse:
        coding, audit, _rules, _opt = self.run_symbolic(extraction, setting=setting)
        return CodingResponse(extraction=extraction, coding=coding, audit_trail=audit)

    def run_symbolic(
        self, extraction: ClinicalExtraction, *, setting: Setting | None = None
    ) -> tuple[Coding, AuditTrail, RulesResult, OptimizationResult]:
        if setting is not None:
            extraction.patient.setting = setting

        timer = StageTimer()

        with timer.time("bridge"):
            bridge = self.bridge(extraction)
        with timer.time("souffle"):
            rules_result = self.apply_rules(extraction, bridge)
        with timer.time("clingo"):
            optimization = self.optimize(rules_result, extraction, bridge)

        # Feed the chosen factors back through the rules engine for an independent verdict on
        # the final invoice — including analog positions, which were never candidates before.
        with timer.time("souffle_verification"):
            verification_bridge = self.validator.build_verification_bridge(optimization)
            verification = self.apply_rules(
                extraction,
                verification_bridge,
                proposed_factors={f.ziffer: f.factor for f in optimization.factors},
            )

        with timer.time("validation"):
            coding, audit = self.validator.build(
                extraction,
                rules_result,
                optimization,
                bridge,
                verification=verification,
                extraction_mode=str(self.settings.extraction_mode),
                extraction_model="manual",
                souffle_version=self.souffle.version(),
                clingo_version=self.clingo.version,
                logic_version=self.settings.logic_version,
                stage_timings_ms=timer.timings,
            )

        # Pydantic copies the dict on validation, so the validation stage's own duration — only
        # known once build() returned — has to be written back explicitly.
        audit.stage_timings_ms = dict(timer.timings)
        return coding, audit, rules_result, optimization

    # -- the proposal path (what the API returns) -------------------------------------------

    def propose(
        self,
        extraction: ClinicalExtraction,
        *,
        setting: Setting | None = None,
        case_id: str | None = None,
        proposal_id: str | None = None,
    ) -> Proposal:
        """Run the pipeline (or serve the cache) and wrap the result as a DRAFT proposal.

        The cache is content-addressed: identical facts under identical data, logic, solver
        versions and policy hit; anything else misses. A cached hit is still returned as a *new*
        DRAFT proposal with its own id — a previous approval does not transfer to a new request.
        """
        if setting is not None:
            extraction.patient.setting = setting

        identity = self._identity()
        facts = extraction.model_dump(mode="python")
        key = cache_key(policy=self.settings.policy_fingerprint(), facts=facts, **identity)

        cached = self.cache.get(key)
        if cached is not None:
            log.debug("cache hit %s", key[:12])
            result = CodingResponse.model_validate(cached["solver_result"])
            return self._wrap(
                result,
                identity=identity,
                receipt=cached["receipt_hash"],
                case_id=case_id,
                proposal_id=proposal_id,
                cached=True,
            )

        coding, audit, _rules, optimization = self.run_symbolic(extraction)
        result = CodingResponse(extraction=extraction, coding=coding, audit_trail=audit)

        receipt = receipt_hash(
            policy=self.settings.policy_fingerprint(),
            facts=facts,
            # The invoice itself, not the audit trail: timings and timestamps must not move the
            # receipt, and `canonical()` would strip them anyway.
            output=coding.model_dump(mode="python"),
            **identity,
        )

        coverage = self.rule_coverage()
        self.cache.set(
            key,
            cache_entry(
                solver_result=result.model_dump(mode="python"),
                proof_atoms=[step.model_dump(mode="python") for step in _rules.proof],
                warnings=[w.model_dump(mode="python") for w in coding.warnings],
                rule_coverage=coverage.model_dump(mode="python"),
                missing_documentation=[
                    m.model_dump(mode="python") for m in optimization.missing_documentation
                ],
                receipt_hash=receipt,
            ),
        )
        return self._wrap(
            result,
            identity=identity,
            receipt=receipt,
            case_id=case_id,
            proposal_id=proposal_id,
            cached=False,
        )

    def _wrap(
        self,
        result: CodingResponse,
        *,
        identity: dict[str, str],
        receipt: str,
        case_id: str | None,
        proposal_id: str | None,
        cached: bool,
    ) -> Proposal:
        coverage = self.rule_coverage()
        audit = result.audit_trail
        return Proposal(
            proposal_id=proposal_id or f"prop_{uuid.uuid4().hex[:16]}",
            case_id=case_id,
            status=ProposalStatus.DRAFT,
            created_at=datetime.now(timezone.utc),
            receipt_hash=receipt,
            catalog_version=identity["catalog_version"],
            catalog_sha256=identity["catalog_sha256"],
            rules_version=identity["rules_version"],
            rules_hash=identity["rules_hash"],
            solver_version=identity["solver_version"],
            rules_engine_version=identity["rules_engine_version"],
            logic_version=identity["logic_version"],
            solver_result=result,
            warnings=list(result.coding.warnings),
            missing_documentation=list(result.coding.missing_documentation),
            # Read off the audit trail rather than threaded through as another argument, so the
            # cached path and the fresh path cannot report different statuses for one result.
            solver_status=audit.solver_status,
            solver_timed_out=audit.solver_status == "TIMEOUT_PARTIAL",
            enforced_rule_count=coverage.enforced_rule_count,
            advisory_rule_count=coverage.advisory_rule_count,
            unverified_rule_count=coverage.unverified_rule_count,
            analog_candidate_count=coverage.analog_candidate_count,
            suppressed_unverified_rule_count=coverage.suppressed_unverified_rule_count,
            rule_coverage=coverage,
            cached=cached,
        )
