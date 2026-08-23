"""Canonical GOÄ catalog access, and the temporal routing that chooses which catalog.

The catalog is versioned data with a recorded source and SHA-256, not engine logic. Every
monetary or factor value is a ``Decimal`` from the moment it leaves this module — floats never
touch money or Steigerungsfaktoren.

**Temporal routing.** A fee schedule is not a constant: a 2019 invoice was written under the 2019
catalog and has to be audited against it, not against today's. So there is not one catalog on disk
but one directory per edition under ``data/catalogs/``, and a caller names the edition it wants:

    load_catalog()                                    # DEFAULT_CATALOG_VERSION — the real snapshot
    load_catalog(catalog_version="goae_1996")         # data/catalogs/goae_1996/
    load_catalog(catalog_version="goae_2026_current") # data/catalogs/goae_2026_current/

The whole of the routing is ``resolve_catalog_dir``: a validated directory name joined onto
``CATALOGS_DIR``. Nothing else in the engine knows about editions — the pipeline, the solvers and
the PADnext audit are all handed a `Catalog` object and never ask where it came from.

Two rules keep routing honest:

**An unknown edition is an error, never a silent fallback.** ``CatalogNotFoundError`` names the
edition asked for and lists the ones that exist. Falling back to the default would answer a
question about 2019 with 2026 money, which is exactly the failure this module exists to prevent.
It subclasses both ``CatalogError`` and ``ValueError``, so existing ``except CatalogError`` handlers
still catch it and a caller may treat a bad edition name as the bad argument it is.

**Which edition was loaded reaches the receipt.** Not through this module — through the data. Each
catalog file declares its own ``catalog_version`` and hashes to its own SHA-256, and
``app.services.receipt`` covers both, so the same invoice audited under two editions cannot produce
one receipt hash. ``routed_version`` (the directory) is recorded beside ``catalog_version`` (what
the file says it is) so a mismatch between the two is visible; ``tests/test_multi_catalog.py``
asserts that every shipped edition is distinct under both.

**Not every edition is real data.** ``goae_current`` is the official snapshot; the era directories
beside it are synthetic fixtures (see ``data/catalogs/README.md``). Those declare
``"synthetic": true``, and loading one logs a warning naming it, so a fixture cannot quietly end up
under a real invoice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.config import (
    CATALOG_FILENAME,
    CATALOGS_DIR,
    DEFAULT_CATALOG_VERSION,
    OVERRIDES_FILENAME,
)

log = logging.getLogger(__name__)


class CatalogError(RuntimeError):
    pass


class CatalogNotFoundError(CatalogError, ValueError):
    """The requested edition is not on disk, or its name could not be a directory name.

    Both bases are deliberate: it is a ``CatalogError`` so every existing handler around catalog
    loading keeps working, and a ``ValueError`` because a caller passing `catalog_version="goae_1800"`
    passed a bad argument — a route handler can map it to a 400 without importing this module.
    """


#: A catalog edition is a single directory name and nothing else. Anything with a separator, a
#: `..`, or a leading dot is refused before it touches the filesystem — the edition may one day
#: arrive as a query parameter, and `../../etc` must not resolve to a path at all.
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def available_catalog_versions(catalogs_dir: Path | None = None) -> tuple[str, ...]:
    """Every edition actually on disk: directory names that hold a catalog file, sorted.

    Read fresh rather than cached — a fixture written by
    `scripts/make_temporal_fixtures.py` while the process is running must become visible.
    """
    root = catalogs_dir or CATALOGS_DIR
    if not root.is_dir():
        return ()
    return tuple(
        sorted(child.name for child in root.iterdir() if (child / CATALOG_FILENAME).is_file())
    )


def resolve_catalog_dir(
    catalog_version: str | None = None, *, catalogs_dir: Path | None = None
) -> Path:
    """Temporal routing, in full: an edition name becomes `data/catalogs/{edition}/`.

    `None` (and `""`) mean `DEFAULT_CATALOG_VERSION`, so a caller that has no opinion about the
    era gets the shipped default rather than an error.

    Raises `CatalogNotFoundError` — which is also a `ValueError` — when the name is not a plain
    directory name, when the directory is absent, and when it is present but holds no catalog
    file. The last case is worth separating: a half-populated edition directory is a likelier
    mistake than a typo, and a message that said "no such edition" would send the reader looking
    for a spelling error that is not there.
    """
    root = catalogs_dir or CATALOGS_DIR
    version = (catalog_version or DEFAULT_CATALOG_VERSION).strip()

    if not _VERSION_RE.match(version):
        raise CatalogNotFoundError(
            f"catalog_version {catalog_version!r} is not a valid catalog edition name. Expected a "
            f"single directory name under {root} such as {DEFAULT_CATALOG_VERSION!r}; "
            f"available: {list(available_catalog_versions(root))}"
        )

    directory = root / version
    if not directory.is_dir():
        available = list(available_catalog_versions(root))
        # No editions at all is a different problem from a wrong edition name: the data was never
        # built. Say so, rather than listing an empty set and leaving the reader to infer it.
        hint = (
            "No catalog is present at all. Build one with:\n"
            "    python scripts/fetch_goae.py && python scripts/import_goae.py\n"
            "and the synthetic era fixtures with:\n"
            "    python scripts/make_temporal_fixtures.py"
            if not available
            else (
                f"An unknown edition is refused rather than falling back to "
                f"{DEFAULT_CATALOG_VERSION!r}: answering a question about one era with another "
                "era's money is the error this refusal exists to prevent."
            )
        )
        raise CatalogNotFoundError(
            f"no catalog edition {version!r} in {root}. Available: {available}. {hint}"
        )
    if not (directory / CATALOG_FILENAME).is_file():
        raise CatalogNotFoundError(
            f"catalog edition {version!r} exists at {directory} but holds no {CATALOG_FILENAME}. "
            "Build it (scripts/import_goae.py for the official snapshot, "
            "scripts/make_temporal_fixtures.py for the synthetic eras) or remove the directory."
        )
    return directory


def catalog_files(
    catalog_version: str | None = None, *, catalogs_dir: Path | None = None
) -> tuple[Path, Path]:
    """`(catalog file, overrides file)` for one edition. The overrides file need not exist."""
    directory = resolve_catalog_dir(catalog_version, catalogs_dir=catalogs_dir)
    return directory / CATALOG_FILENAME, directory / OVERRIDES_FILENAME


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
    #: The edition this was routed to — the directory name under `data/catalogs/`, i.e. the
    #: `catalog_version` argument a caller passed. Distinct from the `catalog_version` *property*
    #: below, which is the version the file itself declares and which the receipt records. They
    #: are two different claims ("where we looked" and "what we found"), and keeping both is what
    #: makes a mislabelled edition directory detectable.
    routed_version: str = ""
    ziffern: dict[str, Ziffer] = field(default_factory=dict)
    factor_bands: dict[str, FactorBand] = field(default_factory=dict)
    special_factor_ziffern: dict[str, FactorBand] = field(default_factory=dict)
    source: CatalogSource = field(default_factory=CatalogSource)
    overrides_applied: list[dict] = field(default_factory=list)

    # -- construction ----------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        path: Path | None = None,
        overrides_path: Path | None = None,
        *,
        catalog_version: str | None = None,
        catalogs_dir: Path | None = None,
    ) -> Catalog:
        """Load one edition, either by name (routed) or by explicit file path (legacy).

        `catalog_version` is the temporal route: the edition's directory decides both files, so a
        catalog can never be read with another edition's overrides applied on top of it. Passing
        `path` instead stays supported because callers already hold `settings.catalog_path`, and
        passing both is refused rather than silently resolved — the two could disagree.
        """
        if catalog_version and path is not None:
            raise CatalogError(
                f"load(): pass either catalog_version={catalog_version!r} or path={path}, not "
                "both — a routed edition decides its own file, and two answers to 'which catalog' "
                "is exactly the ambiguity routing removes."
            )

        if catalog_version or path is None:
            directory = resolve_catalog_dir(catalog_version, catalogs_dir=catalogs_dir)
            path = directory / CATALOG_FILENAME
            overrides_path = overrides_path or directory / OVERRIDES_FILENAME
            routed = directory.name
        else:
            overrides_path = overrides_path or path.parent / OVERRIDES_FILENAME
            # Not authoritative the way a routed name is — it is read back off the path — but it is
            # the edition a reader of a `Catalog` needs, and the layout guarantees it.
            routed = path.parent.name

        if not path.exists():
            raise CatalogError(
                f"catalog not found at {path}. Build it with:\n"
                "    python scripts/fetch_goae.py && python scripts/import_goae.py"
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        catalog = cls(raw=raw, path=path, routed_version=routed)
        catalog._build()
        catalog._apply_overrides(overrides_path)
        catalog._validate()
        if catalog.is_synthetic:
            log.warning(
                "loaded SYNTHETIC catalog edition %r (%s): %d positions, not the official GOÄ. "
                "Fixture data must not be used to bill or to audit a real invoice.",
                catalog.routed_version,
                catalog.catalog_version,
                len(catalog.ziffern),
            )
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
        """What the file declares it is. This is the string the receipt hash covers."""
        return self.raw.get("catalog_version", "unknown")

    @property
    def is_synthetic(self) -> bool:
        """Fixture data rather than a published fee schedule.

        Set by `scripts/make_temporal_fixtures.py`; absent from the official snapshot, so the
        default is "this is real" only for files that carry no opinion — which is why the fixtures
        are the ones that have to say so.
        """
        return bool(self.raw.get("synthetic", False))

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
def load_catalog(
    path: str | Path | None = None,
    *,
    catalog_version: str | None = None,
    catalogs_dir: str | Path | None = None,
) -> Catalog:
    """The process-wide, cached way to get a catalog. One parsed copy per edition.

        load_catalog()                              # DEFAULT_CATALOG_VERSION
        load_catalog(catalog_version="goae_1996")   # the 1996 edition
        load_catalog(settings.catalog_path)         # an explicit file, as before

    Cached per distinct argument tuple, so two editions coexist in one process — which is what
    lets a test, or a batch auditing invoices from several years, hold both at once. `Catalog` is
    treated as read-only by every consumer; `apply_rule_reviews` rebuilds the rule store, never
    the catalog.
    """
    return Catalog.load(
        Path(path) if path is not None else None,
        catalog_version=catalog_version,
        catalogs_dir=Path(catalogs_dir) if catalogs_dir is not None else None,
    )
