"""
DrugTree - Diseases Router

REST API endpoints for disease universe data.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..models.disease import (
    Disease,
    DrugDiseaseEdge,
    DrugDiseaseEdgeListResponse,
    DiseaseListResponse,
    RegionalApproval,
    RegionalApprovalListResponse,
    DiseaseUniverseStats,
    PrevalenceTier,
    Region,
    ApprovalStatus,
)
from ..models.drug import Drug, DrugListResponse
from ..services.data_snapshot import get_data_snapshot_service

router = APIRouter(prefix="/api/v1", tags=["diseases"])
snapshot_service = get_data_snapshot_service()


def load_diseases() -> List[Disease]:
    snapshot = snapshot_service.get_snapshot()
    return [Disease(**disease) for disease in snapshot.diseases]


def save_diseases(diseases: List[Disease]) -> None:
    diseases_path = snapshot_service.data_dir / "diseases.json"
    diseases_path.parent.mkdir(parents=True, exist_ok=True)
    diseases_path.write_text(
        json.dumps({"diseases": [d.model_dump() for d in diseases]}, indent=2),
        encoding="utf-8",
    )
    snapshot_service.refresh()


def load_body_ontology() -> dict:
    snapshot = snapshot_service.get_snapshot()
    return snapshot.body_ontology


def load_disease_drug_edges() -> List[DrugDiseaseEdge]:
    snapshot = snapshot_service.get_snapshot()
    return [DrugDiseaseEdge(**edge) for edge in snapshot.disease_drug_edges]


def load_drugs() -> List[dict]:
    snapshot = snapshot_service.get_snapshot()
    return snapshot.drugs


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


@router.get("/diseases/edges", response_model=DrugDiseaseEdgeListResponse)
async def list_disease_drug_edges(
    disease_id: Optional[str] = Query(None, description="Filter by disease ID"),
    drug_id: Optional[str] = Query(None, description="Filter by drug ID"),
    limit: int = Query(1000, ge=1, le=50000),
    offset: int = Query(0, ge=0),
):
    edges = load_disease_drug_edges()

    if disease_id:
        edges = [edge for edge in edges if edge.disease_id == disease_id]
    if drug_id:
        edges = [edge for edge in edges if edge.drug_id == drug_id]

    total = len(edges)
    paginated = edges[offset : offset + limit]
    return DrugDiseaseEdgeListResponse(total=total, edges=paginated)


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


@router.get("/diseases/{disease_id}/drugs", response_model=DrugListResponse)
async def get_drugs_for_disease(disease_id: str):
    diseases = load_diseases()
    disease = None
    for d in diseases:
        if d.id == disease_id:
            disease = d
            break

    if not disease:
        raise HTTPException(status_code=404, detail=f"Disease '{disease_id}' not found")

    edges = load_disease_drug_edges()
    edge_drug_ids = [edge.drug_id for edge in edges if edge.disease_id == disease_id]
    if not edge_drug_ids:
        return DrugListResponse(total=0, drugs=[])

    drugs_by_id = {drug["id"]: drug for drug in load_drugs()}
    matching_drugs = [
        Drug(**drugs_by_id[drug_id])
        for drug_id in edge_drug_ids
        if drug_id in drugs_by_id
    ]

    return DrugListResponse(total=len(matching_drugs), drugs=matching_drugs)


@router.get("/targets/{target_id}/drugs", response_model=DrugListResponse)
async def get_drugs_for_target(target_id: str):
    drugs = load_drugs()
    target_lower = target_id.lower()

    matching_drugs = []
    for drug in drugs:
        drug_targets = drug.get("targets", [])
        for target in drug_targets:
            if target_lower in target.lower():
                matching_drugs.append(Drug(**drug))
                break

    return DrugListResponse(total=len(matching_drugs), drugs=matching_drugs)


@router.get("/approvals", response_model=RegionalApprovalListResponse)
async def list_approvals(
    drug_id: Optional[str] = Query(None, description="Filter by drug ID"),
    region: Optional[str] = Query(
        None, description="Filter by region (FDA, EMA, etc.)"
    ),
    status: Optional[str] = Query(None, description="Filter by approval status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    drugs = load_drugs()
    approvals = []

    for drug in drugs:
        drug_id_val = drug.get("id", "")
        year_approved = drug.get("year_approved")
        phase = drug.get("phase", "")

        if year_approved and phase == "IV":
            approval = RegionalApproval(
                drug_id=drug_id_val,
                region=Region.FDA,
                status=ApprovalStatus.APPROVED,
                approval_date=str(year_approved),
                label_source=None,
            )
            approvals.append(approval)

    if drug_id:
        approvals = [a for a in approvals if a.drug_id == drug_id]
    if region:
        approvals = [a for a in approvals if a.region.value == region.upper()]
    if status:
        approvals = [a for a in approvals if a.status.value == status.lower()]

    total = len(approvals)
    paginated = approvals[offset : offset + limit]
    return RegionalApprovalListResponse(total=total, approvals=paginated)


@router.get("/approvals/{drug_id}", response_model=RegionalApprovalListResponse)
async def get_approvals_for_drug(drug_id: str):
    drugs = load_drugs()
    drug_found = False
    year_approved = None
    phase = None

    for drug in drugs:
        if drug.get("id") == drug_id:
            drug_found = True
            year_approved = drug.get("year_approved")
            phase = drug.get("phase", "")
            break

    if not drug_found:
        raise HTTPException(status_code=404, detail=f"Drug '{drug_id}' not found")

    approvals = []
    if year_approved and phase == "IV":
        approval = RegionalApproval(
            drug_id=drug_id,
            region=Region.FDA,
            status=ApprovalStatus.APPROVED,
            approval_date=str(year_approved),
            label_source=None,
        )
        approvals.append(approval)

    return RegionalApprovalListResponse(total=len(approvals), approvals=approvals)
