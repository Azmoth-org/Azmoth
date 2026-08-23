"""Canonical GOÄ catalog access. The loader lives in `catalog_loader`; import from here.

`load_catalog(catalog_version=...)` is the temporal route — one catalog edition per directory
under `data/catalogs/`. See `catalog_loader` for what routing does and does not guarantee.
"""

from app.catalog.catalog_loader import (
    ALLOWED_PROVENANCE,
    ALLOWED_RULE_COVERAGE,
    Catalog,
    CatalogError,
    CatalogNotFoundError,
    CatalogSource,
    FactorBand,
    Ziffer,
    available_catalog_versions,
    catalog_files,
    load_catalog,
    resolve_catalog_dir,
)

__all__ = [
    "ALLOWED_PROVENANCE",
    "ALLOWED_RULE_COVERAGE",
    "Catalog",
    "CatalogError",
    "CatalogNotFoundError",
    "CatalogSource",
    "FactorBand",
    "Ziffer",
    "available_catalog_versions",
    "catalog_files",
    "load_catalog",
    "resolve_catalog_dir",
]
