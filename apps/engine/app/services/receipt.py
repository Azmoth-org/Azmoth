"""Receipts: a SHA-256 that identifies everything that produced a result.

Two responses with the same receipt hash were produced by the same catalog, the same rule tables,
the same logic programs, the same solver versions, the same policy settings and the same input
facts. That is the claim a Rechnungsprüfer can check, and it is what makes "deterministic" a
falsifiable statement rather than an assurance.

What goes in is deliberately narrow: identity of the data and logic, the canonical input, and the
canonical output. What stays out is anything measured — timings, wall-clock stamps, ids — because a
receipt that changed every run would identify nothing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.canonical import canonical, sha256_of


class ReceiptInputs(BaseModel):
    """Everything the receipt hash is computed over. Serialised into the hash in this order."""

    catalog_version: str
    catalog_sha256: str
    rules_version: str
    rules_hash: str
    logic_version: str
    solver_version: str
    rules_engine_version: str
    policy: dict[str, str]
    facts: Any
    output: Any


def receipt_hash(
    *,
    catalog_version: str,
    catalog_sha256: str,
    rules_version: str,
    rules_hash: str,
    logic_version: str,
    solver_version: str,
    rules_engine_version: str = "",
    policy: dict[str, str],
    facts: Any,
    output: Any,
) -> str:
    """SHA-256 over canonicalised identity + input + output."""
    payload = ReceiptInputs(
        catalog_version=catalog_version,
        catalog_sha256=catalog_sha256,
        rules_version=rules_version,
        rules_hash=rules_hash,
        logic_version=logic_version,
        solver_version=solver_version,
        rules_engine_version=rules_engine_version,
        policy=policy,
        facts=canonical(facts),
        output=canonical(output),
    )
    return sha256_of(payload)
