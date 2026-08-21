"""Canonical GOÄ catalog access.

The catalog is versioned data with a recorded source and SHA-256, not engine logic. Every
monetary or factor value is a ``Decimal`` from the moment it leaves this module — floats never
touch money or Steigerungsfaktoren.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.config import CATALOG_PATH, OVERRIDES_PATH


class CatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class Ziffer:
    ziffer: str
    official_text: str
    punkte: int
    category: str | None
    section: str | None = None
    section_title: str | None = None
    status: str = "active"
    provenance: str = "illustrative"
    rule_coverage: str = "partial"
    text_quality: str = "ok"
    minderung_exempt: bool = False
    annotations: tuple[str, ...] = ()

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True)
class FactorBand:
    threshold: Decimal
    max: Decimal
    legal_basis: str = ""


@dataclass
class CatalogSource:
    name: str = ""
    publisher: str = ""
    url: str = ""
    retrieved_at: str = ""
    sha256_raw: str = ""
    legal_status: str = ""


ALLOWED_PROVENANCE = {"official", "illustrative", "licensed", "manual_override"}
ALLOWED_RULE_COVERAGE = {"full", "partial", "none"}


@dataclass
class Catalog:
    raw: dict
    path: Path
    ziffern: dict[str, Ziffer] = field(default_factory=dict)
    factor_bands: dict[str, FactorBand] = field(default_factory=dict)
    special_factor_ziffern: dict[str, FactorBand] = field(default_factory=dict)
    source: CatalogSource = field(default_factory=CatalogSource)
    overrides_applied: list[dict] = field(default_factory=list)

    # -- construction ----------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path = CATALOG_PATH, overrides_path: Path = OVERRIDES_PATH) -> Catalog:
        if not path.exists():
            raise CatalogError(
                f"catalog not found at {path}. Build it with:\n"
                "    python scripts/fetch_goae.py && python scripts/import_goae.py"
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        catalog = cls(raw=raw, path=path)
        catalog._build()
        catalog._apply_overrides(overrides_path)
        catalog._validate()
        return catalog

    def _build(self) -> None:
        raw = self.raw
        for entry in raw.get("ziffern", []):
            ziffer = str(entry["ziffer"])
            self.ziffern[ziffer] = Ziffer(
                ziffer=ziffer,
                official_text=entry.get("official_text", ""),
                punkte=int(entry.get("punkte", 0)),
                category=entry.get("category"),
                section=entry.get("section"),
                section_title=entry.get("section_title"),
                status=entry.get("status", "active"),
                provenance=entry.get("provenance", "illustrative"),
                rule_coverage=entry.get("rule_coverage", "partial"),
                text_quality=entry.get("text_quality", "ok"),
                minderung_exempt=bool(entry.get("minderung_exempt", False)),
                annotations=tuple(entry.get("annotations", ())),
            )

        for letter, band in raw.get("factor_bands", {}).items():
            self.factor_bands[letter] = FactorBand(
                threshold=Decimal(str(band["threshold"])),
                max=Decimal(str(band["max"])),
                legal_basis=band.get("legal_basis", ""),
            )
        for ziffer, band in raw.get("special_factor_ziffern", {}).items():
            self.special_factor_ziffern[str(ziffer)] = FactorBand(
                threshold=Decimal(str(band["threshold"])),
                max=Decimal(str(band["max"])),
                legal_basis=band.get("legal_basis", ""),
            )

        src = raw.get("source", {})
        self.source = CatalogSource(
            name=src.get("name", ""),
            publisher=src.get("publisher", ""),
            url=src.get("url", ""),
            retrieved_at=src.get("retrieved_at", ""),
            sha256_raw=src.get("sha256_raw", ""),
            legal_status=src.get("legal_status", ""),
        )

    def _apply_overrides(self, overrides_path: Path) -> None:
        """Manual corrections on top of the imported catalog, each with a reason and a date."""
        if not overrides_path.exists():
            return
        payload = json.loads(overrides_path.read_text(encoding="utf-8"))
        for override in payload.get("overrides", []):
            ziffer = str(override.get("ziffer", ""))
            if ziffer not in self.ziffern:
                continue
            missing = [k for k in ("reason", "source", "verified_at") if not override.get(k)]
            if missing:
                raise CatalogError(
                    f"override for GOÄ {ziffer} is missing required provenance: {missing}"
                )
            current = self.ziffern[ziffer]
            patch = override.get("override", {})
            self.ziffern[ziffer] = Ziffer(
                **{
                    **{f: getattr(current, f) for f in current.__dataclass_fields__},
                    **{k: v for k, v in patch.items() if k in current.__dataclass_fields__},
                    "provenance": "manual_override",
                }
            )
            self.overrides_applied.append(override)

    def _validate(self) -> None:
        if not self.ziffern:
            raise CatalogError(f"catalog at {self.path} contains no Ziffern")
        if not self.factor_bands:
            raise CatalogError(f"catalog at {self.path} declares no factor_bands")
        for ziffer in self.ziffern.values():
            if ziffer.provenance not in ALLOWED_PROVENANCE:
                raise CatalogError(
                    f"GOÄ {ziffer.ziffer}: provenance {ziffer.provenance!r} is not one of "
                    f"{sorted(ALLOWED_PROVENANCE)}"
                )
            if ziffer.rule_coverage not in ALLOWED_RULE_COVERAGE:
                raise CatalogError(
                    f"GOÄ {ziffer.ziffer}: rule_coverage {ziffer.rule_coverage!r} is not one of "
                    f"{sorted(ALLOWED_RULE_COVERAGE)}"
                )

    # -- metadata --------------------------------------------------------------------------

    @property
    def catalog_version(self) -> str:
        return self.raw.get("catalog_version", "unknown")

    @property
    def rules_version(self) -> str:
        return self.raw.get("rules_version", "unknown")

    @property
    def rule_coverage(self) -> str:
        return self.raw.get("coverage", {}).get("rule_coverage", "partial")

    @property
    def coverage(self) -> dict:
        return self.raw.get("coverage", {})

    @property
    def punktwert_cent(self) -> Decimal:
        return Decimal(str(self.raw["punktwert_cent"]))

    @property
    def rounding(self) -> dict:
        return self.raw.get(
            "rounding",
            {"policy": "ROUND_HALF_UP", "unit": "cent", "legal_basis": "§ 5 Abs. 1 Satz 4 GOÄ"},
        )

    def sha256(self) -> str:
        """Digest of the catalog file itself, so a response can be tied to exact data."""
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    # -- lookups ---------------------------------------------------------------------------

    def has(self, ziffer: str) -> bool:
        return ziffer in self.ziffern

    def get(self, ziffer: str) -> Ziffer | None:
        return self.ziffern.get(ziffer)

    def is_active(self, ziffer: str) -> bool:
        entry = self.ziffern.get(ziffer)
        return entry is not None and entry.is_active

    def factor_band(self, ziffer: str) -> FactorBand:
        """§ 5 GOÄ band for a Ziffer.

        Nummer 437 is named individually in § 5 Abs. 4, so a per-Ziffer override takes
        precedence over the Abschnitt band.
        """
        if ziffer in self.special_factor_ziffern:
            return self.special_factor_ziffern[ziffer]
        entry = self.ziffern.get(ziffer)
        if entry and entry.category and entry.category in self.factor_bands:
            return self.factor_bands[entry.category]
        # No resolvable band: fall back to the most restrictive one rather than the most
        # generous, so an unclassified Ziffer cannot silently be charged at 3.5x.
        return min(self.factor_bands.values(), key=lambda b: b.max)

    def minderung_rate(self, setting: str) -> Decimal:
        return Decimal(str(self.raw.get("minderung", {}).get(setting, "0")))

    def minderung_exempt(self, ziffer: str) -> bool:
        entry = self.ziffern.get(ziffer)
        return bool(entry and entry.minderung_exempt)

    def summary(self) -> dict:
        from collections import Counter

        provenance = Counter(z.provenance for z in self.ziffern.values())
        return {
            "catalog_version": self.catalog_version,
            "rules_version": self.rules_version,
            "catalog_sha256": self.sha256(),
            "ziffern": len(self.ziffern),
            "active_ziffern": sum(1 for z in self.ziffern.values() if z.is_active),
            "rule_coverage": self.rule_coverage,
            "provenance_breakdown": dict(provenance),
            "punktwert_cent": str(self.punktwert_cent),
            "rounding": self.rounding,
            "source": {
                "name": self.source.name,
                "publisher": self.source.publisher,
                "url": self.source.url,
                "retrieved_at": self.source.retrieved_at,
                "sha256_raw": self.source.sha256_raw,
                "legal_status": self.source.legal_status,
            },
            "overrides_applied": len(self.overrides_applied),
            "text_quality_flagged": sum(
                1 for z in self.ziffern.values() if z.text_quality != "ok"
            ),
        }


@lru_cache
def load_catalog(path: str | Path = CATALOG_PATH) -> Catalog:
    return Catalog.load(Path(path))
