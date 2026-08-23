"""Canonical JSON, so two runs that mean the same thing hash the same.

Used by the content-addressed cache and by the receipt hash. Both are only as trustworthy as this
function: a key that changes when nothing meaningful changed makes the cache useless, and a key
that *fails* to change when something meaningful did makes it dangerous.

Rules:

- ``Decimal`` becomes its exact string. Never a float — ``float(Decimal("1.15"))`` is not 1.15.
- dict keys are sorted.
- lists are sorted by their own canonical form, because Datalog and set iteration produce
  order-insensitive collections and an incidental reordering is not a different answer.
- volatile keys (measured timings, wall-clock timestamps, request ids) are removed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

#: Fields that legitimately differ between two identical runs. Anything that decides money, codes
#: or provenance must NEVER be added here — see tests/test_golden_normalization.py, which asserts
#: exactly that in both directions.
VOLATILE_KEYS: frozenset[str] = frozenset(
    {
        "timestamp",
        "created_at",
        "approved_at",
        "generated_at",
        "started_at",
        "finished_at",
        "stage_timings_ms",
        "solve_ms",
        "build_ms",
        "ground_ms",
        "solve_time_ms",
        "total_time_ms",
        "duration_ms",
        "latency_ms",
        "elapsed_ms",
        "request_id",
        "trace_id",
        "correlation_id",
        "run_id",
        "proposal_id",
        "cached",
    }
)


def to_jsonable(value: Any) -> Any:
    """Plain JSON types, with Decimals as exact strings."""
    if isinstance(value, BaseModel):
        return to_jsonable(value.model_dump(mode="python"))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in value]
    return value


def strip_volatile(obj: Any, volatile: frozenset[str] = VOLATILE_KEYS) -> Any:
    if isinstance(obj, dict):
        return {k: strip_volatile(v, volatile) for k, v in obj.items() if k not in volatile}
    if isinstance(obj, list):
        return [strip_volatile(v, volatile) for v in obj]
    return obj


def canonical(obj: Any, *, volatile: frozenset[str] = VOLATILE_KEYS) -> Any:
    """Volatile keys removed, dict keys sorted, lists sorted by canonical form."""
    stripped = strip_volatile(to_jsonable(obj), volatile)

    def sort(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: sort(v) for k, v in sorted(node.items())}
        if isinstance(node, list):
            items = [sort(v) for v in node]
            try:
                return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, default=str))
            except TypeError:  # pragma: no cover - json.dumps handles everything we produce
                return items
        return node

    return sort(stripped)


def canonical_json(obj: Any, *, volatile: frozenset[str] = VOLATILE_KEYS) -> str:
    return json.dumps(
        canonical(obj, volatile=volatile),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def sha256_of(obj: Any, *, volatile: frozenset[str] = VOLATILE_KEYS) -> str:
    return hashlib.sha256(canonical_json(obj, volatile=volatile).encode("utf-8")).hexdigest()
