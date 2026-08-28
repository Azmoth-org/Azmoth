"""Do the solvers actually solve? — a liveness probe, not a version string.

`GET /api/v1/health` used to answer "is the Soufflé binary on `PATH`" and "what does
`clingo.__version__` say". Both of those are true of a container in which nothing can be solved: a
`souffle` binary with a broken shared-library link is on `PATH` and dies on `exec`; a host that has
run out of process slots resolves the binary and cannot spawn it; the Python `clingo` wheel imports
and reports its version whether or not its native grounder can ground anything. Each of those
presents identically to the old check — `souffle_available: true`, a version, `status: "ok"` — and
then fails on the first real request, which is the *worst* moment to discover it.

So each solver is asked to answer one trivial question that exercises the whole path it would use
for a real one:

    clingo   `1 { a(1..n) } 1.` grounded and solved in-process, with `n` passed as a constant —
             the same `Control` → `add` → `ground` → `solve` sequence a coding run uses, and it must
             produce exactly one model. A version string proves none of that.
    souffle  a two-line Datalog program written to a temp directory and run through the real
             binary, reading back the relation it printed. That is a process spawn, an interpreter
             run and a file read: everything `SouffleEngine.run` does except the size of the input.

## The results are cached, and the TTL is the interesting decision

The Soufflé probe costs an interpreter start — tens to a few hundred milliseconds, dominated by
process creation rather than by the two facts it derives. That is nothing per request and something
per *caller*: the Docker healthcheck asks every 30 s, the dashboard's System Health card asks on
every render, and a page that renders it twice would otherwise spawn two Soufflé processes to learn
the same thing.

`PROBE_TTL_SECONDS` is deliberately shorter than the healthcheck interval, so a supervisor polling
on its own schedule never reads a result cached by somebody else's request — the point of a
healthcheck is that it reflects *now*, and a cache that outlived its interval would report a solver
as healthy for a full cycle after it stopped being. Within a burst of page renders the cache holds,
which is the case it exists for.

The cache stores failures too, and for the same length of time. A solver that is broken is broken
for reasons that do not clear inside ten seconds — a missing library, a wrong binary, a host under
memory pressure — and re-running a probe that just failed, on every request, turns one broken
dependency into a second load problem.

## Nothing here raises

A probe is a diagnostic, and a diagnostic that can take down the endpoint reporting it is worse than
no diagnostic. Every failure — a missing binary, a non-zero exit, a timeout, an unexpected exception
from the `clingo` extension — becomes a `SolverProbe` with a status and a one-line reason. The
caller decides what that means for the service's overall status; this module only reports.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

#: How long a probe result is reused. See the module docstring — shorter than the 30 s Docker
#: healthcheck interval on purpose, so a supervisor's poll is never answered from a page render's
#: cache.
PROBE_TTL_SECONDS = 10.0

#: The ceiling on a probe subprocess. Generous relative to what the program needs (a trivial Datalog
#: program evaluates in single-digit milliseconds once the interpreter is up) and deliberately far
#: below the 60 s `SOUFFLE_TIMEOUT_S` a real run gets: a health check that can hang for a minute is
#: one an orchestrator will kill before it answers, and "the probe timed out" is itself the finding.
PROBE_TIMEOUT_SECONDS = 10.0

#: The ASP program the Clingo probe solves. A choice rule with an exact cardinality bound, so there
#: is precisely one answer set and "got a model" is a real assertion rather than "did not crash".
#: `n` arrives as a constant via `Control(["-c", "n=1"])`, which is what makes this exercise
#: constant substitution as well as grounding.
CLINGO_PROBE_PROGRAM = "1 { a(1..n) } 1."

#: The Datalog program the Soufflé probe runs. No input facts, so nothing depends on a fact
#: directory being written correctly — a rule with a constant body, and the output the probe reads
#: back. Two lines, because the failure being tested for is "the process cannot run", not "the
#: language works".
SOUFFLE_PROBE_PROGRAM = """.decl probe(x:number)
.output probe
probe(1).
"""


@dataclass(frozen=True, slots=True)
class SolverProbe:
    """What one solver answered, and how long it took to answer it.

    `status` is three-valued rather than a boolean because the three cases call for different
    actions. `ok` — it solved. `unavailable` — it is not installed here, which is a deployment that
    was built wrong and will not fix itself. `failed` — it is installed and did not produce the
    right answer, which is the case the old availability check could not see at all and the one most
    worth waking somebody for.
    """

    status: str
    probe_time_ms: float
    version: str = ""
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _ms_since(started: float) -> float:
    """Elapsed milliseconds, rounded to two places.

    `perf_counter` rather than `time.time`: this measures a duration, and a wall clock that steps
    (NTP, a suspend/resume) would produce a negative or absurd figure in a field somebody graphs.
    Rounded because the third decimal of a millisecond is noise from the measurement itself.
    """
    return round((time.perf_counter() - started) * 1000, 2)


def probe_clingo(settings: Settings | None = None) -> SolverProbe:
    """Ground and solve a one-line program in-process. `ok` only if exactly one model came back."""
    del settings  # Signature symmetry with `probe_souffle`; Clingo reads no configuration here.
    started = time.perf_counter()
    try:
        import clingo

        # `-c n=1` rather than a literal in the program text: constant substitution is part of what
        # a real solve does, and a probe that skipped it would pass on a grounder that could not.
        control = clingo.Control(["-c", "n=1"])
        control.add("base", [], CLINGO_PROBE_PROGRAM)
        control.ground([("base", [])])

        models = 0
        with control.solve(yield_=True) as handle:
            for _ in handle:
                models += 1

        elapsed = _ms_since(started)
        if models != 1:
            return SolverProbe(
                status="failed",
                probe_time_ms=elapsed,
                version=clingo.__version__,
                detail=(
                    f"the probe program has exactly one answer set and the solver returned "
                    f"{models}. The grounder or the solver is not behaving as its version claims."
                ),
            )
        return SolverProbe(status="ok", probe_time_ms=elapsed, version=clingo.__version__)
    except ImportError as exc:
        return SolverProbe(
            status="unavailable",
            probe_time_ms=_ms_since(started),
            detail=f"the clingo Python module is not importable: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 - a diagnostic must not be able to fail its endpoint
        # Bare `Exception` on purpose: `clingo` is a native extension and the interesting failures
        # here come out of C++ as types this module has no reason to enumerate. What matters is
        # that the health endpoint answers.
        log.warning("clingo probe failed: %s", exc)
        return SolverProbe(
            status="failed",
            probe_time_ms=_ms_since(started),
            detail=f"{type(exc).__name__}: {exc}",
        )


def probe_souffle(settings: Settings | None = None) -> SolverProbe:
    """Run a two-line Datalog program through the real binary and read its output back.

    `unavailable` when the binary is not on `PATH` — that is a deployment problem, not a failure —
    and `failed` for everything after that: a spawn the host refused, a non-zero exit, a timeout, or
    an output file that does not contain what the program derives. The last of those is the case a
    `--version` check cannot reach and the reason this writes a program at all.
    """
    settings = settings or get_settings()
    started = time.perf_counter()

    binary = shutil.which(settings.souffle_bin)
    if binary is None:
        return SolverProbe(
            status="unavailable",
            probe_time_ms=_ms_since(started),
            detail=(
                f"binary {settings.souffle_bin!r} is not on PATH. /solve and /padnext/audit cannot "
                "answer without it — install it or set SOUFFLE_BIN."
            ),
        )

    try:
        with tempfile.TemporaryDirectory(prefix="goae_probe_") as workdir:
            root = Path(workdir)
            program = root / "probe.dl"
            program.write_text(SOUFFLE_PROBE_PROGRAM, encoding="utf-8")

            proc = subprocess.run(
                [settings.souffle_bin, "-D", str(root), str(program)],
                capture_output=True,
                text=True,
                timeout=PROBE_TIMEOUT_SECONDS,
            )
            if proc.returncode != 0:
                return SolverProbe(
                    status="failed",
                    probe_time_ms=_ms_since(started),
                    detail=(
                        f"exit {proc.returncode}: "
                        f"{(proc.stderr or proc.stdout or '').strip()[:200] or 'no output'}"
                    ),
                )

            # The interpreter writes `<relation>.csv` into `-D`. Reading it is what turns "the
            # process exited zero" into "the program was evaluated and produced its conclusion".
            output = root / "probe.csv"
            derived = output.read_text(encoding="utf-8").strip() if output.is_file() else ""
            if derived != "1":
                return SolverProbe(
                    status="failed",
                    probe_time_ms=_ms_since(started),
                    detail=(
                        "the probe program derives probe(1) and the output relation held "
                        f"{derived!r}. The binary runs but is not evaluating correctly."
                    ),
                )

        return SolverProbe(
            status="ok", probe_time_ms=_ms_since(started), version=_souffle_version(settings)
        )
    except subprocess.TimeoutExpired:
        return SolverProbe(
            status="failed",
            probe_time_ms=_ms_since(started),
            detail=(
                f"the probe program did not finish inside {PROBE_TIMEOUT_SECONDS}s. It derives one "
                "fact, so this is the process not starting rather than the program being slow."
            ),
        )
    except OSError as exc:
        return SolverProbe(
            status="failed",
            probe_time_ms=_ms_since(started),
            detail=(
                f"the binary is on PATH and could not be run: {exc}. Usually a broken dynamic link "
                "or a host that has no process slots left."
            ),
        )
    except Exception as exc:  # noqa: BLE001 - see `probe_clingo`
        log.warning("souffle probe failed: %s", exc)
        return SolverProbe(
            status="failed", probe_time_ms=_ms_since(started), detail=f"{type(exc).__name__}: {exc}"
        )


def _souffle_version(settings: Settings) -> str:
    """`souffle --version`, or `""`. Never raises — a probe that solved is `ok` without a version."""
    try:
        proc = subprocess.run(
            [settings.souffle_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in proc.stdout.splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return ""


# ----------------------------------------------------------------------------------------------
# the cache
# ----------------------------------------------------------------------------------------------
#
# A dict rather than `functools.lru_cache`, because what is wanted is a TTL and `lru_cache` has no
# concept of one — the usual workaround (a rounded timestamp in the key) makes the cache expire on a
# wall-clock boundary rather than after an interval, so a probe run at 09:59.999 is thrown away a
# millisecond later. Two entries, one per solver; no lock, because the worst a race can do is run a
# probe twice and store the newer answer.

_cache: dict[str, tuple[float, SolverProbe]] = {}


def probe_solvers(
    settings: Settings | None = None, *, force: bool = False
) -> dict[str, SolverProbe]:
    """Both probes, cached for `PROBE_TTL_SECONDS`. `force=True` for a test that must not be cached.

    Keyed by solver name and not by settings: `SOUFFLE_BIN` is read once per process from the
    environment, so two calls in one process cannot disagree about which binary they meant.
    """
    settings = settings or get_settings()
    return {
        "clingo": _cached("clingo", lambda: probe_clingo(settings), force=force),
        "souffle": _cached("souffle", lambda: probe_souffle(settings), force=force),
    }


def _cached(name: str, run, *, force: bool) -> SolverProbe:
    now = time.monotonic()
    if not force:
        entry = _cache.get(name)
        if entry is not None and now - entry[0] < PROBE_TTL_SECONDS:
            return entry[1]
    result = run()
    _cache[name] = (now, result)
    return result


def reset_probe_cache() -> None:
    """Forget every cached probe. For tests that change `SOUFFLE_BIN` between cases."""
    _cache.clear()


__all__ = [
    "CLINGO_PROBE_PROGRAM",
    "PROBE_TIMEOUT_SECONDS",
    "PROBE_TTL_SECONDS",
    "SOUFFLE_PROBE_PROGRAM",
    "SolverProbe",
    "probe_clingo",
    "probe_solvers",
    "probe_souffle",
    "reset_probe_cache",
]
