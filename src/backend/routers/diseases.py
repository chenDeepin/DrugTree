"""
DrugTree - Diseases Router

REST API endpoints for disease universe data.
"""

import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..models.disease import (
    Disease,
    DiseaseListResponse,
    DiseaseFilterParams,
    DiseaseSummary,
    Target,
    TargetListResponse,
    DrugDiseaseEdge,
    DrugDiseaseEdgeListResponse,
    RegionalApproval,
    RegionalApprovalListResponse,
    DiseaseUniverseStats,
    PrevalenceTier,
    EvidenceLevel,
)

router = APIRouter(prefix="/api/v1", tags=["diseases"])

DATA_DIR = Path(__file__).parent.parent.parent / "frontend" / "data"
DISEASES_FILE = DATA_DIR / "diseases.json"
BODY_ONTOLOGY_FILE = (
    Path(__file__).parent.parent.parent.parent
    / "data"
    / "ontology"
    / "body_ontology.json"
)


def load_diseases() -> List[Disease]:
    if not DISEASES_FILE.exists():
        return []
    with open(DISEASES_FILE, "r") as f:
        data = json.load(f)
        return [Disease(**d) for d in data.get("diseases", [])]


def save_diseases(diseases: List[Disease]) -> None:
    DISEASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DISEASES_FILE, "w") as f:
        json.dump({"diseases": [d.model_dump() for d in diseases]}, f, indent=2)


def load_body_ontology() -> dict:
    if not BODY_ONTOLOGY_FILE.exists():
        return {}
    with open(BODY_ONTOLOGY_FILE, "r") as f:
        return json.load(f)


@router.get("/diseases", response_model=DiseaseListResponse)
async def list_diseases(
    region: Optional[str] = Query(None, description="Filter by body region ID"),
    orphan_only: bool = Query(False, description="Show only orphan diseases"),
    has_approved_drugs: Optional[bool] = Query(
        None, description="Filter by approved drug availability"
    ),
    search: Optional[str] = Query(None, description="Search in name, synonyms"),
    prevalence_tier: Optional[PrevalenceTier] = Query(
        None, description="Filter by prevalence tier"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    diseases = load_diseases()
    filtered = diseases

    if region:
        filtered = [d for d in filtered if d.body_region == region]

    if orphan_only:
        filtered = [d for d in filtered if d.orphan_flag]

    if has_approved_drugs is not None:
        if has_approved_drugs:
            filtered = [d for d in filtered if d.approved_drug_count > 0]
        else:
            filtered = [d for d in filtered if d.approved_drug_count == 0]

    if prevalence_tier:
        filtered = [d for d in filtered if d.prevalence_tier == prevalence_tier.value]

    if search:
        search_lower = search.lower()
        filtered = [
            d
            for d in filtered
            if search_lower in d.canonical_name.lower()
            or any(search_lower in str(s).lower() for s in d.synonyms)
        ]

    total = len(filtered)
    paginated = filtered[offset : offset + limit]
    return DiseaseListResponse(total=total, diseases=paginated)


@router.get("/diseases/orphan", response_model=DiseaseListResponse)
async def get_orphan_diseases(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    diseases = load_diseases()
    orphan = [d for d in diseases if d.orphan_flag]
    total = len(orphan)
    paginated = orphan[offset : offset + limit]
    return DiseaseListResponse(total=total, diseases=paginated)


@router.get("/diseases/stats", response_model=DiseaseUniverseStats)
async def get_disease_stats():
    diseases = load_diseases()
    ontology = load_body_ontology()

    by_region = {}
    by_prevalence = {}

    for d in diseases:
        by_region[d.body_region] = by_region.get(d.body_region, 0) + 1
        tier = d.prevalence_tier
        by_prevalence[tier] = by_prevalence.get(tier, 0) + 1

    return DiseaseUniverseStats(
        total_diseases=len(diseases),
        orphan_diseases=sum(1 for d in diseases if d.orphan_flag),
        total_targets=sum(d.target_count for d in diseases),
        total_approved_drugs=sum(d.approved_drug_count for d in diseases),
        total_clinical_drugs=sum(d.clinical_drug_count for d in diseases),
        diseases_by_region=by_region,
        diseases_by_prevalence=by_prevalence,
    )


@router.get("/diseases/search/{query}", response_model=DiseaseListResponse)
async def search_diseases(query: str):
    diseases = load_diseases()
    query_lower = query.lower()
    filtered = [
        d
        for d in diseases
        if query_lower in d.canonical_name.lower()
        or any(query_lower in str(s).lower() for s in d.synonyms)
        or (d.mechanism_summary and query_lower in d.mechanism_summary.lower())
    ]
    return DiseaseListResponse(total=len(filtered), diseases=filtered)


@router.get("/diseases/{disease_id}", response_model=Disease)
async def get_disease(disease_id: str):
    diseases = load_diseases()
    for disease in diseases:
        if disease.id == disease_id:
            return disease
    raise HTTPException(status_code=404, detail=f"Disease '{disease_id}' not found")


@router.get("/diseases/region/{region}", response_model=DiseaseListResponse)
async def get_diseases_by_region(region: str):
    diseases = load_diseases()
    filtered = [d for d in diseases if d.body_region == region]
    return DiseaseListResponse(total=len(filtered), diseases=filtered)
