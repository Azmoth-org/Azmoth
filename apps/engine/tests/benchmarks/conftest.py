"""The threshold machinery the three benchmarks in this package share.

## Why thresholds rather than `--benchmark-compare`

pytest-benchmark ships its own regression detection: `--benchmark-autosave` writes a JSON per run
and `--benchmark-compare-fail=median:20%` fails against a saved one. That is the better tool when
the saved run and the current run happen on the *same* machine, and it is the wrong one here. The
saved JSON records `machine_info`, and pytest-benchmark itself warns when it differs — because a
median measured on a developer laptop says nothing about a shared CI runner. Committing a baseline
JSON would therefore either be ignored (compare across machines, get noise) or be per-machine (and
then nobody's laptop has one).

So the baseline is a *number in a document* — `docs/performance_baselines.md` — and the gate is an
explicit threshold pair per benchmark, scaled for the machine. That keeps the reviewable artefact
in git as prose a human can argue with, rather than as a binary blob whose provenance is a
hostname.

## Soft and hard

Two thresholds, because a performance change has two different meanings:

- **soft** (+20% over baseline) — *tell someone*. Warns and prints a section at the end of the run,
  and the run still passes. A 20% move is inside the range a busy machine can produce on its own,
  so failing on it would train people to re-run the build until it goes green, which is worse than
  not measuring at all.
- **hard** (+100% over baseline) — *fail*. Nothing legitimate makes this engine twice as slow. At
  this point the build stops and names the number.

## `PerformanceRegressionWarning` is not a `UserWarning`, deliberately

`pytest.ini` carries `filterwarnings = ignore::UserWarning`. A soft breach raised as a
`UserWarning` — the obvious choice, and what `warnings.warn` does by default — would be swallowed
before anybody saw it, and the soft threshold would silently do nothing. Subclassing `Warning`
directly keeps it out of that filter. The terminal summary below is the belt to that braces: it
prints unconditionally, so a soft breach is visible even to a reader who does not read warning
summaries.

## The scale factor

`BENCHMARK_THRESHOLD_SCALE` multiplies both thresholds. It exists because the baselines were
measured on one documented machine (see the doc) and CI runs on a shared runner inside Docker,
where two Soufflé subprocess spawns per solve — 72% of a solve, per
`docs/performance_baseline.md` — cost whatever the host's neighbours leave over. Unset means 1.0,
which is the reference machine and the meaningful gate. CI sets it explicitly, and the value it
sets is provisional until enough uploaded artefacts exist to state a CI baseline of its own.
"""

from __future__ import annotations

import os
import warnings

import pytest

#: Soft breaches, collected across the session so `pytest_terminal_summary` can print them
#: together. Module-level rather than a fixture because the hook runs after every fixture is torn
#: down, and a list that has to survive that cannot live in one.
_SOFT_BREACHES: list[str] = []


class PerformanceRegressionWarning(Warning):
    """A benchmark exceeded its soft threshold. See this module's docstring for why not `UserWarning`."""


def threshold_scale() -> float:
    """`BENCHMARK_THRESHOLD_SCALE`, or 1.0 — the reference machine.

    A value that does not parse is a configuration mistake, not a reason to fall back to 1.0 and
    fail a build the operator thought they had loosened. It raises.
    """
    raw = os.getenv("BENCHMARK_THRESHOLD_SCALE", "").strip()
    if not raw:
        return 1.0
    try:
        scale = float(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"BENCHMARK_THRESHOLD_SCALE={raw!r} is not a number. Unset it for the reference "
            "machine (1.0), or set a float."
        ) from exc
    if scale <= 0:
        raise RuntimeError(f"BENCHMARK_THRESHOLD_SCALE={raw!r} must be positive.")
    return scale


def check_thresholds(
    benchmark,
    *,
    what: str,
    baseline_ms: float,
    soft_ms: float,
    hard_ms: float,
) -> float:
    """Record the thresholds on the benchmark and gate its median against them.

    Call this immediately after `benchmark.pedantic(...)`. Returns the observed median in
    milliseconds so a caller can assert something further about it.

    `extra_info` is populated *before* either branch fires, so the JSON artefact a failing CI run
    uploads still says what the test was measuring against. A gate whose output only exists when it
    passes cannot be used to work out why it failed.
    """
    scale = threshold_scale()
    soft, hard = soft_ms * scale, hard_ms * scale
    median_ms = benchmark.stats.stats.median * 1000.0

    benchmark.extra_info.update(
        {
            "what": what,
            "baseline_ms": baseline_ms,
            "soft_threshold_ms": round(soft, 3),
            "hard_threshold_ms": round(hard, 3),
            "threshold_scale": scale,
            "median_ms": round(median_ms, 3),
            "pct_over_baseline": round((median_ms / baseline_ms - 1.0) * 100.0, 1),
            "soft_breached": median_ms > soft,
            "hard_breached": median_ms > hard,
        }
    )

    context = (
        f"{what}: median {median_ms:.1f} ms against a {baseline_ms:.1f} ms baseline "
        f"({median_ms / baseline_ms:.2f}x)"
    )
    if scale != 1.0:
        context += f", thresholds scaled x{scale:g} by BENCHMARK_THRESHOLD_SCALE"

    if median_ms > hard:
        pytest.fail(
            f"HARD performance threshold exceeded — {context}. "
            f"The hard limit is {hard:.1f} ms (baseline +100%). Nothing legitimate makes this "
            f"twice as slow: find what changed, or re-measure the baseline and update "
            f"docs/performance_baselines.md in the same commit as the change that moved it.",
            pytrace=False,
        )

    if median_ms > soft:
        message = (
            f"SOFT performance threshold exceeded — {context}. "
            f"The soft limit is {soft:.1f} ms (baseline +20%); the hard limit is {hard:.1f} ms. "
            f"Not a failure. Worth a look before it becomes one."
        )
        _SOFT_BREACHES.append(message)
        warnings.warn(message, PerformanceRegressionWarning, stacklevel=2)

    return median_ms


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Print every soft breach in its own section at the end of the run.

    The warning above is already raised, but a warning competes with every other warning in the
    summary and `-q` hides plenty. A soft threshold that nobody reads is the same as no soft
    threshold, so this prints unconditionally and in yellow.
    """
    if not _SOFT_BREACHES:
        return
    terminalreporter.section("performance: soft thresholds exceeded", yellow=True, bold=True)
    for message in _SOFT_BREACHES:
        terminalreporter.write_line(f"  {message}", yellow=True)
    terminalreporter.write_line(
        "  Baselines and the threshold rationale: docs/performance_baselines.md", yellow=True
    )
