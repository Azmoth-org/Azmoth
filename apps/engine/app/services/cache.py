"""Content-addressed result cache.

The key is a SHA-256 over everything that can change an answer:

    catalog_version + catalog_sha256      the fee schedule that was loaded
    rules_version + rules_hash            the rule tables, hashed, not merely versioned
    logic_version                         SHA-256 of goae_rules.dl + goae_optimize.lp
    solver_version + rules_engine_version clingo and Soufflé
    policy fingerprint                    UNVERIFIED_RULE_POLICY, BASE_FACTOR_POLICY, mode
    canonical facts                       the normalised clinical input

Nothing measured is in the key, so two identical requests hit; and editing one cell of one rule CSV
misses, because the CSVs are hashed. A cache that could serve a result computed under a different
rule set would be a compliance defect, not a performance one.

The backend is a small in-memory LRU. `CacheBackend` is the seam a Redis implementation drops into:
values are JSON-serialisable dicts, keys are hex digests, and nothing here assumes one process.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.canonical import sha256_of


class CacheBackend(Protocol):
    """Replace with Redis by implementing these three methods."""

    def get(self, key: str) -> dict | None: ...

    def set(self, key: str, value: dict) -> None: ...

    def clear(self) -> None: ...

    def __len__(self) -> int: ...


class InMemoryLRU:
    """Thread-safe bounded LRU. Adequate for one process; not shared between workers."""

    def __init__(self, max_entries: int = 256) -> None:
        self._max = max(1, max_entries)
        self._data: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict | None:
        with self._lock:
            value = self._data.get(key)
            if value is None:
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


def cache_key(
    *,
    catalog_version: str,
    catalog_sha256: str,
    rules_version: str,
    rules_hash: str,
    logic_version: str,
    solver_version: str,
    rules_engine_version: str,
    policy: dict[str, str],
    facts: Any,
) -> str:
    return sha256_of(
        {
            "v": 1,  # key format version, so a change here cannot collide with old entries
            "catalog_version": catalog_version,
            "catalog_sha256": catalog_sha256,
            "rules_version": rules_version,
            "rules_hash": rules_hash,
            "logic_version": logic_version,
            "solver_version": solver_version,
            "rules_engine_version": rules_engine_version,
            "policy": policy,
            "facts": facts,
        }
    )


def entry(
    *,
    solver_result: Any,
    proof_atoms: list[dict] | list[str],
    warnings: list[dict],
    rule_coverage: dict,
    receipt_hash: str,
    missing_documentation: list[dict] | None = None,
) -> dict:
    """One cache value. Exactly the fields the brief requires the cache to store."""
    return {
        "solver_result": solver_result,
        "proof_atoms": list(proof_atoms),
        "warnings": list(warnings),
        "rule_coverage": rule_coverage,
        "missing_documentation": list(missing_documentation or []),
        "receipt_hash": receipt_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


class ResultCache:
    """`CACHE_ENABLED=false` makes every operation a no-op, so callers need no branches."""

    def __init__(self, backend: CacheBackend | None = None, *, enabled: bool = True) -> None:
        self.backend: CacheBackend = backend or InMemoryLRU()
        self.enabled = enabled

    def get(self, key: str) -> dict | None:
        return self.backend.get(key) if self.enabled else None

    def set(self, key: str, value: dict) -> None:
        if self.enabled:
            self.backend.set(key, value)

    def clear(self) -> None:
        self.backend.clear()

    def __len__(self) -> int:
        return len(self.backend)
