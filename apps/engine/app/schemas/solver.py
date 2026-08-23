"""What the Clingo layer decides, and what it could not justify.

The solver resolves exactly three things Datalog deliberately leaves open: which member of a
mutually exclusive cluster is charged, which Steigerungsfaktor each charged position carries, and
which listed position an unlisted service is charged analogously to. See `logic/asp/goae_optimize.lp`
for the objective ordering and why revenue is last.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import Dec, FactorBasis, Warning_
from app.schemas.facts import BlockedCode

# There is deliberately no closed union for `solver_status`: it is `str(clingo.SolveResult)` plus
# the engine's own TIMEOUT_PARTIAL, and a Clingo upgrade may add a spelling. Typing it shut would
# turn a new status into a validation error instead of a value the caller can display.


class FactorDecision(BaseModel):
    ziffer: str
    factor: Dec
    basis: FactorBasis
    threshold: Dec
    max_factor: Dec
    justification_required: bool = False
    justification: str | None = None
    legal_basis: str = ""


class AnalogDecision(BaseModel):
    act_id: str
    entity_type: str
    ziffer: str
    similarity: Dec
    rule_id: str = ""
    legal_basis: str = "§ 6 Abs. 2 GOÄ"
    quote: str = ""
    requires_human_review: bool = True


class MissingDocumentation(BaseModel):
    """A higher Steigerungsfaktor that the law would permit but the record does not support.

    Derived only from what the existing logic already emits — the § 5 band, the cap, the ladder's
    own output and whether a written reason is present. **Nothing here changes what is billed.**
    The solver's objective is untouched: this is the gap between what was documented and what
    would have to be documented, stated so a physician can decide whether to document it.

    ``current_factor`` is what the solver actually chose and what the invoice charges.
    ``possible_factor`` is the ceiling that a written justification (§ 12 Abs. 3 GOÄ) would open,
    never a proposal to charge it.
    """

    ziffer: str
    current_factor: str
    possible_factor: str
    missing: str
    legal_basis: str = "§ 12 Abs. 3 GOÄ"


class GroundingStats(BaseModel):
    """What grounding actually produced, read off `clingo.Control.statistics` after the solve.

    Grounding is where an ASP program becomes expensive: the propositional program clingo searches
    is the *instantiated* one, so a rule with two unbound Ziffer variables costs |Z|² rules before
    the search has started. These counts are the only honest way to see that happening — a timing
    delta tells you a solve was slow, this tells you what was fed to it.

    Everything here is measurement. Nothing in it reaches the invoice, the receipt or the cache
    key, and `app.core.canonical` strips the timings that sit beside it.
    """

    #: Atoms and rules in the ground program (`problem.lp`), after clingo's own preprocessing.
    atoms: int = 0
    atoms_aux: int = 0
    bodies: int = 0
    rules: int = 0
    rules_choice: int = 0
    rules_minimize: int = 0
    #: Search effort (`solving.solvers`), not grounding — kept here so one object answers
    #: "was this slow because the program was big, or because the search was hard?".
    choices: int = 0
    conflicts: int = 0
    #: Our side of the same question: how much program text we handed clingo, and how many of
    #: those lines were injected facts rather than the fixed encoding.
    program_bytes: int = 0
    fact_lines: int = 0


class OptimizationResult(BaseModel):
    billed: list[str] = Field(default_factory=list)
    dropped: list[BlockedCode] = Field(default_factory=list)
    factors: list[FactorDecision] = Field(default_factory=list)
    analogs: list[AnalogDecision] = Field(default_factory=list)
    total_punkte: int = 0
    objective: list[int] = Field(default_factory=list)
    models_enumerated: int = 0
    solver_status: str = ""
    #: Wall-clock spent inside the solver, and whether the hard timeout cut it short.
    solve_ms: float = 0.0
    #: Wall-clock spent building the injected facts and grounding the program — everything before
    #: search begins. Separated from `solve_ms` because the two have different remedies: grounding
    #: is fixed by narrowing rules, search by better constraints or a different objective.
    build_ms: float = 0.0
    ground_ms: float = 0.0
    #: Size of the ground program the search ran on. `None` when clingo reported no statistics.
    grounding: GroundingStats | None = None
    timed_out: bool = False
    warnings: list[Warning_] = Field(default_factory=list)
    missing_documentation: list[MissingDocumentation] = Field(default_factory=list)

    def factor_for(self, ziffer: str) -> Decimal | None:
        for decision in self.factors:
            if decision.ziffer == ziffer:
                return decision.factor
        return None
