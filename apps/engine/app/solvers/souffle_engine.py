"""Soufflé wrapper: run the Datalog program and read its conclusions back.

The program itself is `logic/datalog/goae_rules.dl` in the monorepo, resolved through
`settings.datalog_path` (`LOGIC_DIR`) rather than shipped inside this package: it is declarative
legal reasoning, reviewable without reading Python.

Soufflé runs in interpreter mode (no C++ toolchain needed at runtime) over a temporary fact
directory. Every failure mode — binary missing, non-zero exit, unreadable output — raises with
the inputs that caused it. A rules engine that silently returns "nothing is chargeable" is far
worse than one that crashes.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

from app.bridge.entity_to_ziffer import BridgeResult
from app.catalog import Catalog, load_catalog
from app.config import Settings, get_settings
from app.core.retry import retry_transient
from app.errors import RulesEngineUnavailable
from app.schemas import (
    BlockedCode,
    ClinicalExtraction,
    Conflict,
    ProofStep,
    RulesResult,
    Warning_,
)
from app.solvers.souffle_facts import read_relation, unscale, write_fact_files
from app.rules.rule_store import RuleStore, load_rules

log = logging.getLogger(__name__)

BLOCK_EXPLANATIONS = {
    "exclusion": "GOÄ {by} schließt GOÄ {z} aus – nicht nebeneinander berechnungsfähig.",
    "zielleistung": (
        "GOÄ {z} ist methodisch notwendiger Bestandteil der Zielleistung GOÄ {by} und daher "
        "nicht gesondert berechnungsfähig (§ 4 Abs. 2a GOÄ)."
    ),
    "less_specific": (
        "Für dieselbe dokumentierte Leistung existiert die spezifischere Position GOÄ {by}; "
        "die allgemeinere GOÄ {z} tritt zurück."
    ),
    "unknown_ziffer": "GOÄ {z} ist im geladenen Katalog nicht enthalten.",
    "inactive_ziffer": "GOÄ {z} ist im geladenen Katalog nicht als aktiv geführt.",
    "conflict_lost": (
        "GOÄ {z} konkurriert wechselseitig mit GOÄ {by}; der Optimierer hat GOÄ {by} gewählt."
    ),
}


#: Attempts at *starting* the process, total. Not attempts at evaluating the program — see
#: `SouffleEngine._spawn` for why a non-zero exit and a timeout are never retried.
SPAWN_ATTEMPTS = 3
SPAWN_RETRY_BASE_DELAY_SECONDS = 0.5


class SouffleError(RulesEngineUnavailable, RuntimeError):
    """The rules engine could not be run, or ran and failed. `503 RULES_ENGINE_UNAVAILABLE`.

    503 with a `Retry-After` rather than 500, because from the caller's side this is the service
    being unable to answer rather than the request being wrong — and one of the two common causes
    (the process could not be started under memory pressure) genuinely does clear on its own.

    `stderr` and the fact dump stay on the exception for the log and are deliberately kept out of
    `details`: the facts are the patient's encounter, and an error body is the last place they
    should appear.
    """

    def __init__(self, message: str, *, stderr: str = "", fact_dump: str = "") -> None:
        super().__init__(message, details={"engine": "souffle"})
        self.stderr = stderr
        self.fact_dump = fact_dump


class SouffleEngine:
    def __init__(
        self,
        settings: Settings | None = None,
        catalog: Catalog | None = None,
        rules: RuleStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.catalog = catalog or load_catalog()
        self.rules = rules or load_rules()

    # -- availability ----------------------------------------------------------------------

    @property
    def binary(self) -> str | None:
        return shutil.which(self.settings.souffle_bin)

    def available(self) -> bool:
        return self.binary is not None

    def version(self) -> str:
        if not self.available():
            return ""
        try:
            proc = subprocess.run(
                [self.settings.souffle_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        for line in proc.stdout.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return ""

    # -- the subprocess --------------------------------------------------------------------

    @retry_transient(
        transient=(OSError,),
        attempts=SPAWN_ATTEMPTS,
        base_delay=SPAWN_RETRY_BASE_DELAY_SECONDS,
        description="souffle spawn",
    )
    def _spawn(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        """Start Soufflé, retrying only the failure that is worth retrying.

        `OSError` from `subprocess.run` is the host refusing to create a process — `ENOMEM`,
        `EAGAIN` from a full process table, a transiently unavailable filesystem. That clears on
        its own often enough to be worth two more attempts a second apart.

        Nothing else is retried, and the two exclusions are deliberate. A **non-zero exit** means
        the program ran and rejected its input: the same facts through the same Datalog will fail
        the same way, so retrying is three times the work for one answer. A **timeout** is even
        worse to retry — `SOUFFLE_TIMEOUT_S` is 60 s, so two more attempts would hold the request
        open for three minutes before failing anyway. Both leave on the first attempt.
        """
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=self.settings.souffle_timeout_s
        )

    # -- main entry point ------------------------------------------------------------------

    def run(
        self,
        extraction: ClinicalExtraction,
        bridge: BridgeResult,
        *,
        proposed_factors: dict[str, Decimal] | None = None,
        keep_workdir: Path | None = None,
    ) -> RulesResult:
        if not self.available():
            raise SouffleError(
                f"Soufflé binary '{self.settings.souffle_bin}' not found on PATH. Install it "
                "(see README), set SOUFFLE_BIN, or use: docker compose up"
            )

        workdir_ctx: tempfile.TemporaryDirectory | None = None
        if keep_workdir is not None:
            keep_workdir.mkdir(parents=True, exist_ok=True)
            workdir = keep_workdir
        else:
            workdir_ctx = tempfile.TemporaryDirectory(prefix="goae_souffle_")
            workdir = Path(workdir_ctx.name)

        try:
            fact_dir, out_dir = workdir / "facts", workdir / "out"
            out_dir.mkdir(parents=True, exist_ok=True)
            counts = write_fact_files(
                fact_dir, self.catalog, self.rules, bridge, extraction, proposed_factors
            )
            log.debug("souffle facts: %s", counts)

            program = self.settings.datalog_path
            if not program.is_file():
                raise SouffleError(
                    f"Datalog program not found at {program}. It lives in the monorepo's "
                    "logic/datalog/ directory; set LOGIC_DIR if it is elsewhere."
                )
            cmd = [
                self.settings.souffle_bin,
                "-F", str(fact_dir),
                "-D", str(out_dir),
                str(program),
            ]
            try:
                proc = self._spawn(cmd)
            except subprocess.TimeoutExpired as exc:
                raise SouffleError(
                    f"Soufflé timed out after {self.settings.souffle_timeout_s}s",
                    fact_dump=self._dump_facts(fact_dir),
                ) from exc
            except OSError as exc:
                raise SouffleError(
                    f"Soufflé could not be started after {SPAWN_ATTEMPTS} attempts: {exc}. The "
                    "binary is present, so this is the process itself failing to launch — most "
                    "often memory pressure or a process-table limit on the host.",
                    fact_dump=self._dump_facts(fact_dir),
                ) from exc

            if proc.returncode != 0:
                raise SouffleError(
                    f"Soufflé exited with code {proc.returncode}. Command: {' '.join(cmd)}",
                    stderr=proc.stderr,
                    fact_dump=self._dump_facts(fact_dir),
                )

            return self._parse(out_dir, bridge, proc.stdout + proc.stderr)
        finally:
            if workdir_ctx is not None:
                workdir_ctx.cleanup()

    @staticmethod
    def _dump_facts(fact_dir: Path) -> str:
        """Fact files contain only Ziffern, rule ids and clinical entity *types* — no free text
        from the record — so they are safe to surface in an error."""
        chunks = []
        for path in sorted(fact_dir.glob("*.facts")):
            chunks.append(f"--- {path.name} ---\n{path.read_text(encoding='utf-8')}")
        return "\n".join(chunks)

    # -- output parsing --------------------------------------------------------------------

    def _parse(self, out_dir: Path, bridge: BridgeResult, stdout: str) -> RulesResult:
        result = RulesResult(
            proposed=list(bridge.candidates),
            analog_requests=list(bridge.analog_requests),
            warnings=list(bridge.warnings),
            souffle_stdout=stdout.strip(),
        )

        def official(ziffer: str) -> str:
            entry = self.catalog.get(ziffer)
            return entry.official_text if entry else ""

        result.billable = sorted({row[0] for row in read_relation(out_dir, "billable")})
        result.arbitration_candidates = sorted(
            {row[0] for row in read_relation(out_dir, "needs_arbitration")}
        )

        blocked: list[BlockedCode] = []
        for reason, relation in (
            ("less_specific", "blocked_less_specific"),
            ("zielleistung", "blocked_zielleistung"),
            ("exclusion", "blocked_exclusion"),
        ):
            for row in read_relation(out_dir, relation):
                ziffer, by = row[0], row[1]
                rule_id = row[2] if len(row) > 2 else ""
                rule = self.rules.rule_by_id(rule_id)
                blocked.append(
                    BlockedCode(
                        ziffer=ziffer,
                        official_text=official(ziffer),
                        reason=reason,  # type: ignore[arg-type]
                        detail=f"blocked_by:{by}",
                        blocked_by=by,
                        rule_id=rule_id,
                        legal_basis=rule.legal_basis if rule else "",
                        explanation=BLOCK_EXPLANATIONS[reason].format(z=ziffer, by=by),
                    )
                )

        for reason, relation in (
            ("unknown_ziffer", "unknown_ziffer"),
            ("inactive_ziffer", "inactive_ziffer"),
        ):
            for row in read_relation(out_dir, relation):
                ziffer = row[0]
                blocked.append(
                    BlockedCode(
                        ziffer=ziffer,
                        official_text=official(ziffer),
                        reason=reason,  # type: ignore[arg-type]
                        detail=reason,
                        explanation=BLOCK_EXPLANATIONS[reason].format(z=ziffer, by=""),
                    )
                )
                result.warnings.append(
                    Warning_(
                        type=reason,
                        ziffer=ziffer,
                        severity="error",
                        message=(
                            f"GOÄ {ziffer} wurde vorgeschlagen, ist im Katalog "
                            f"{self.catalog.catalog_version} aber nicht verwendbar."
                        ),
                    )
                )

        result.blocked = sorted(blocked, key=lambda b: (b.ziffer, b.reason, b.blocked_by or ""))

        result.conflicts = [
            Conflict(
                ziffer_a=row[0],
                ziffer_b=row[1],
                rule_id=row[2] if len(row) > 2 else "",
                legal_basis=(
                    r.legal_basis
                    if (r := self.rules.rule_by_id(row[2] if len(row) > 2 else "")) is not None
                    else ""
                ),
            )
            for row in sorted(read_relation(out_dir, "conflict"))
        ]

        for row in sorted(read_relation(out_dir, "proof")):
            rule_id = row[3] if len(row) > 3 else ""
            rule = self.rules.rule_by_id(rule_id)
            result.proof.append(
                ProofStep(
                    ziffer=row[0],
                    rule=row[1],
                    detail=row[2] if len(row) > 2 else "",
                    rule_id=rule_id,
                    legal_basis=rule.legal_basis if rule else "",
                )
            )

        for row in read_relation(out_dir, "exclusion_chain_warning"):
            result.warnings.append(
                Warning_(
                    type="exclusion_chain_detected",
                    severity="warning",
                    message=(
                        f"Ausschluss-Kette erkannt: GOÄ {row[2]} → GOÄ {row[1]} → GOÄ {row[0]}. "
                        "Die Schichtung der Regeln deckt nur eine Ebene ab; bitte manuell prüfen."
                    ),
                )
            )

        for row in read_relation(out_dir, "invalid_factor"):
            result.factor_invalid.append(row[0])
            result.warnings.append(
                Warning_(
                    type="factor_above_hoechstsatz",
                    ziffer=row[0],
                    severity="error",
                    legal_basis="§ 5 Abs. 1, § 2 GOÄ",
                    message=(
                        f"GOÄ {row[0]}: Faktor {unscale(row[1])} überschreitet den Höchstsatz "
                        f"{unscale(row[2])}."
                    ),
                )
            )

        for row in read_relation(out_dir, "invalid_factor_cap"):
            result.factor_invalid.append(row[0])
            rule = self.rules.rule_by_id(row[3] if len(row) > 3 else "")
            result.warnings.append(
                Warning_(
                    type="factor_above_leistungslegende_cap",
                    ziffer=row[0],
                    severity="error",
                    rule_id=row[3] if len(row) > 3 else "",
                    legal_basis=rule.legal_basis if rule else "",
                    message=(
                        f"GOÄ {row[0]}: Faktor {unscale(row[1])} überschreitet den in der "
                        f"Leistungslegende festgelegten Höchstwert {unscale(row[2])}."
                    ),
                )
            )

        result.factor_needs_justification = sorted(
            {row[0] for row in read_relation(out_dir, "needs_justification")}
        )
        return result
