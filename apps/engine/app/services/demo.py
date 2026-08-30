"""The public demo: one committed synthetic delivery, audited and cached.

This module exists to make a *public, unauthenticated* audit possible without creating an upload
endpoint. That distinction is the whole design, so it is worth stating plainly before the code:

**Nothing here reads caller input.** `demo_report()` takes no bytes, no filename, no query
parameter — it audits one file whose path is a constant in this module. There is therefore no
request a visitor can construct that causes this service to process *their* data, which is what
keeps `/api/v1/demo/audit` outside the reach of GDPR Art. 9 and § 203 StGB entirely. A public
endpoint that accepted a file would be a medical-data processor open to the internet; this one is
a fixed document served by a solver. `docs/compliance/PRIVATE_DATA_WARNING.md` is the reason that
distinction has to be structural rather than a policy somebody remembers.

**The delivery is asserted synthetic on every load, not trusted to be.** `assert_synthetic` refuses
a fixture flagged `echtdaten="true"` *regardless of* `PADNEXT_ALLOW_REAL_DATA`. The audit path
already refuses real data (`app.padnext.audit.RealDataRefused`), but that refusal is switchable by
an operator who has a lawful basis for a **private** deployment, and this endpoint is public. The
two are different questions and this is the one place they diverge, so the guard is separate.

## Why the report is cached

The audit is deterministic: the same delivery, catalog, rule tables and logic programs produce the
same verdicts and the same `receipt_hash` — that property is pinned by the golden-snapshot tests
and is what `receipt_hash` means. So the report is a pure function of state that does not change
while the process runs, and computing it once is not an optimisation with a correctness cost.

It does close a real hole, though. A public endpoint that spawned a Soufflé subprocess per request
would be a denial-of-service vector reachable without a credential, and the engine's own rate
limiter counts per API key — a demo visitor has none. With the report memoised, a request is a
serialisation of an object that is already in memory, and there is nothing left to exhaust.

The key includes the fixture's `mtime` and size so that a developer editing the file under a
bind mount sees their edit, and the catalog, rules, logic and schema policy so that a test that
swaps the pipeline is not answered from another pipeline's cache.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.padnext import audit_delivery, read_delivery
from app.schemas import PadnextAuditReport

log = logging.getLogger(__name__)

#: The bundled nine-error delivery. Committed, synthetic, and the same file the pilot demo guide
#: and `docs/api/PARTNER_API.md` quote their numbers from — so the public demo, the sales script
#: and the API documentation cannot come to show three different reports.
DEMO_DELIVERY_FILENAME = "00004711_20260726_ADL_000001_padx.xml"


class DemoUnavailable(RuntimeError):
    """The demo fixture is missing or is not synthetic. A 503, never a 500 with a stack trace.

    Both causes are deployment faults rather than caller faults: an image built without `logic/`,
    or a fixture somebody replaced. The public endpoint says so in a sentence and stays up for
    every other route.
    """


def demo_delivery_path(settings: Settings | None = None) -> Path:
    """Where the bundled delivery lives. Derived from `LOGIC_DIR`, never from a request."""
    return (settings or get_settings()).cases_dir / "padnext" / DEMO_DELIVERY_FILENAME


def assert_synthetic(delivery: Any) -> None:
    """Refuse to serve anything flagged as production data, whatever the deployment allows.

    `audit_delivery` performs the same check and can be switched off with
    `PADNEXT_ALLOW_REAL_DATA=1`, which exists so that a *private* deployment with a lawful basis
    can process real deliveries deliberately. This endpoint is public and anonymous, so that
    switch must not reach it: a deployment that turns real data on for its own authenticated
    users has not thereby decided to publish one on the open internet.
    """
    if delivery.echtdaten is True:
        raise DemoUnavailable(
            f"The bundled demo delivery {DEMO_DELIVERY_FILENAME} is flagged as production data "
            "(auftrag/@echtdaten). The public demo serves synthetic data only and will not serve "
            "it, regardless of PADNEXT_ALLOW_REAL_DATA."
        )


@dataclass(frozen=True)
class _CacheKey:
    """Everything that could change the report, so that nothing else has to be reasoned about."""

    path: str
    mtime_ns: int
    size: int
    catalog_version: str
    logic_version: str
    schema_policy: str
    enforced_rules: int


_lock = threading.Lock()
_cached: tuple[_CacheKey, PadnextAuditReport] | None = None


def demo_report(pipeline: Any, settings: Settings | None = None) -> PadnextAuditReport:
    """The audited demo delivery. Computed once per process, then served from memory.

    `pipeline` is passed in rather than imported so this stays testable without a running app and
    so the caller owns engine construction — the same reasoning `audit_delivery` gives for taking
    `souffle_run` as an argument.
    """
    global _cached

    settings = settings or get_settings()
    path = demo_delivery_path(settings)

    try:
        stat = path.stat()
    except OSError as exc:
        raise DemoUnavailable(
            f"The bundled demo delivery is not readable at {path}. The engine image copies "
            "`logic/` (see apps/engine/Dockerfile); an image built without it cannot serve the "
            "public demo."
        ) from exc

    key = _CacheKey(
        path=str(path),
        mtime_ns=stat.st_mtime_ns,
        size=stat.st_size,
        catalog_version=pipeline.catalog.catalog_version,
        logic_version=settings.logic_version,
        schema_policy=str(settings.padnext_schema_policy),
        enforced_rules=len(pipeline.rules.exclusions),
    )

    with _lock:
        if _cached is not None and _cached[0] == key:
            return _cached[1]

    delivery, read_findings = read_delivery(
        path.read_bytes(), source_name=DEMO_DELIVERY_FILENAME
    )
    assert_synthetic(delivery)

    report = audit_delivery(
        delivery,
        catalog=pipeline.catalog,
        rules=pipeline.rules,
        souffle_run=pipeline.souffle.run,
        read_findings=read_findings,
        settings=settings,
    )

    with _lock:
        _cached = (key, report)

    log.info(
        "demo report computed: %d positions, %d findings, coverage=%.4f, receipt=%s",
        len(report.positions),
        len(report.findings),
        report.coverage_ratio,
        report.receipt_hash[:12],
    )
    return report


def reset_demo_cache() -> None:
    """Drop the memo. For tests, and for a reload that changes the catalog under a running process."""
    global _cached
    with _lock:
        _cached = None


__all__ = [
    "DEMO_DELIVERY_FILENAME",
    "DemoUnavailable",
    "assert_synthetic",
    "demo_delivery_path",
    "demo_report",
    "reset_demo_cache",
]
