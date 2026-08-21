"""Canonical GOÄ catalog access. The loader lives in `catalog_loader`; import from here."""

from app.catalog.catalog_loader import (
    ALLOWED_PROVENANCE,
    ALLOWED_RULE_COVERAGE,
    Catalog,
    CatalogError,
    CatalogSource,
    FactorBand,
    Ziffer,
    load_catalog,
)

__all__ = [
    "ALLOWED_PROVENANCE",
    "ALLOWED_RULE_COVERAGE",
    "Catalog",
    "CatalogError",
    "CatalogSource",
    "FactorBand",
    "Ziffer",
    "load_catalog",
]
