"""Catalog provenance, one position, and the vocabulary the bridge can actually map."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import pipeline
from app.schemas import CatalogResponse, VocabularyResponse, ZifferResponse

router = APIRouter(tags=["catalog"])


@router.get("/catalog", response_model=CatalogResponse)
def catalog() -> CatalogResponse:
    """Provenance and coverage — deliberately not the full 2000-entry dump.

    The warnings are not decoration: rule coverage is `partial`, most exclusion rules were
    machine-extracted and are unverified, and no Zielleistung pairs are loaded at all. Publishing
    that is the difference between a defensible tool and one that overclaims.
    """
    p = pipeline()
    summary = p.catalog.summary()
    rules = p.rules.summary()
    coverage = p.rule_coverage()
    warnings: list[str] = []

    if p.catalog.rule_coverage != "full":
        warnings.append(
            f"Rule coverage is '{p.catalog.rule_coverage}'. Exclusion and Zielleistung rules "
            "were extracted from the fee schedule's prose automatically and are incomplete."
        )
    if rules["unverified_rules_not_enforced"]:
        warnings.append(
            f"{rules['unverified_rules_not_enforced']} rules are unverified and are NOT "
            f"enforced under policy '{rules['policy_for_unverified_rules']}'. They warn only."
        )
    if not p.rules.zielleistung:
        warnings.append(
            "No Zielleistung rules are loaded; invoices are not checked against § 4 Abs. 2a "
            "beyond the rules present."
        )
    if summary["text_quality_flagged"]:
        warnings.append(
            f"{summary['text_quality_flagged']} Ziffern have a service text flagged as possibly "
            "truncated by the importer."
        )

    return CatalogResponse.model_validate(
        {
            **summary,
            "imported_rules": rules,
            "rule_coverage_detail": coverage,
            "coverage_detail": p.catalog.coverage,
            "warnings": warnings,
        }
    )


@router.get("/catalog/ziffer/{ziffer}", response_model=ZifferResponse)
def catalog_ziffer(ziffer: str) -> ZifferResponse:
    p = pipeline()
    entry = p.catalog.get(ziffer)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unknown_ziffer",
                "message": f"GOÄ {ziffer} is not in catalog {p.catalog.catalog_version}.",
            },
        )
    band = p.catalog.factor_band(ziffer)
    cap = p.rules.factor_cap(ziffer)
    return ZifferResponse.model_validate(
        {
            "ziffer": entry.ziffer,
            "official_text": entry.official_text,
            "punkte": entry.punkte,
            "category": entry.category,
            "section": entry.section,
            "section_title": entry.section_title,
            "status": entry.status,
            "provenance": entry.provenance,
            "rule_coverage": entry.rule_coverage,
            "text_quality": entry.text_quality,
            "minderung_exempt": entry.minderung_exempt,
            "factor_band": {
                "threshold": str(band.threshold),
                "max": str(band.max),
                "legal_basis": band.legal_basis,
            },
            "factor_cap": (
                {"max_factor": str(cap.max_factor), "rule_id": cap.rule_id, "quote": cap.quote}
                if cap
                else None
            ),
            "annotations": list(entry.annotations),
            "exclusions_enforced": [
                {
                    "excludes": r.to_ziffer,
                    "direction": r.direction,
                    "rule_id": r.rule_id,
                    "legal_basis": r.legal_basis,
                    "verified": r.verified,
                }
                for r in p.rules.exclusions
                if r.from_ziffer == ziffer
            ],
        }
    )


@router.get("/vocabulary", response_model=VocabularyResponse)
def vocabulary() -> dict:
    """Exactly the clinical vocabulary the bridge can map, for a UI to offer as pickers.

    Generated from `data/mappings/entity_to_ziffer.csv`, so it cannot drift from what the engine
    actually understands. This is what lets a form stop asking users to type identifiers like
    `vollstaendige_untersuchung_organsystem` — a typo there produces an `unmapped_entity` warning
    and the service is silently not charged.
    """
    from app.bridge.vocabulary import build_vocabulary

    p = pipeline()
    return build_vocabulary(p.catalog, p.rules)
