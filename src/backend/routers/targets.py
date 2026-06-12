"""
DrugTree - Targets Router

REST API endpoints for protein target data stored in SQLite.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["targets"])
DB_PATH = Path(__file__).resolve().parents[3] / "drugtree.db"

TARGET_COLUMNS = """
    id,
    symbol,
    name,
    modality,
    disease_ids,
    uniprot_id,
    hgnc_id,
    entrez_id,
    ensembl_gene_id,
    gene_type,
    pathway_ids,
    druggability,
    is_validated_target
"""

TARGET_DETAIL_QUERY = f"""
    WITH target AS (
        SELECT {TARGET_COLUMNS}
        FROM targets
        WHERE id = ?
    )
    SELECT
        0 AS row_sort,
        0 AS sort_1,
        '' AS sort_2,
        '' AS sort_3,
        'target' AS row_kind,
        target.id,
        target.symbol,
        target.name,
        target.modality,
        target.disease_ids,
        target.uniprot_id,
        target.hgnc_id,
        target.entrez_id,
        target.ensembl_gene_id,
        target.gene_type,
        target.pathway_ids,
        target.druggability,
        target.is_validated_target,
        NULL AS drug_id,
        NULL AS drug_name,
        NULL AS interaction_type,
        NULL AS mechanism_of_action,
        NULL AS drug_confidence,
        NULL AS associated_disease_id,
        NULL AS disease_name,
        NULL AS association_score,
        NULL AS evidence_type,
        NULL AS disease_confidence,
        NULL AS source_name,
        NULL AS source_id,
        NULL AS source_url
    FROM target
    UNION ALL
    SELECT
        1 AS row_sort,
        -COALESCE(drug_target_edges.confidence, 0) AS sort_1,
        COALESCE(drugs.name, drug_target_edges.drug_id) AS sort_2,
        '' AS sort_3,
        'drug' AS row_kind,
        target.id,
        target.symbol,
        target.name,
        target.modality,
        target.disease_ids,
        target.uniprot_id,
        target.hgnc_id,
        target.entrez_id,
        target.ensembl_gene_id,
        target.gene_type,
        target.pathway_ids,
        target.druggability,
        target.is_validated_target,
        drug_target_edges.drug_id,
        COALESCE(drugs.name, drug_target_edges.drug_id) AS drug_name,
        drug_target_edges.interaction_type,
        drug_target_edges.mechanism_of_action,
        drug_target_edges.confidence AS drug_confidence,
        NULL AS associated_disease_id,
        NULL AS disease_name,
        NULL AS association_score,
        NULL AS evidence_type,
        NULL AS disease_confidence,
        NULL AS source_name,
        NULL AS source_id,
        NULL AS source_url
    FROM target
    JOIN drug_target_edges ON drug_target_edges.target_id = target.id
    LEFT JOIN drugs ON drugs.id = drug_target_edges.drug_id
    UNION ALL
    SELECT
        2 AS row_sort,
        -COALESCE(target_disease_edges.confidence, 0) AS sort_1,
        -COALESCE(target_disease_edges.association_score, 0) AS sort_2,
        COALESCE(diseases.canonical_name, target_disease_edges.disease_id) AS sort_3,
        'disease' AS row_kind,
        target.id,
        target.symbol,
        target.name,
        target.modality,
        target.disease_ids,
        target.uniprot_id,
        target.hgnc_id,
        target.entrez_id,
        target.ensembl_gene_id,
        target.gene_type,
        target.pathway_ids,
        target.druggability,
        target.is_validated_target,
        NULL AS drug_id,
        NULL AS drug_name,
        NULL AS interaction_type,
        NULL AS mechanism_of_action,
        NULL AS drug_confidence,
        target_disease_edges.disease_id AS associated_disease_id,
        COALESCE(diseases.canonical_name, target_disease_edges.disease_id) AS disease_name,
        target_disease_edges.association_score,
        target_disease_edges.evidence_type,
        target_disease_edges.confidence AS disease_confidence,
        NULL AS source_name,
        NULL AS source_id,
        NULL AS source_url
    FROM target
    JOIN target_disease_edges ON target_disease_edges.target_id = target.id
    LEFT JOIN diseases ON diseases.id = target_disease_edges.disease_id
    UNION ALL
    SELECT
        3 AS row_sort,
        -COALESCE(target_xrefs.is_primary, 0) AS sort_1,
        target_xrefs.source_name AS sort_2,
        target_xrefs.source_id AS sort_3,
        'xref' AS row_kind,
        target.id,
        target.symbol,
        target.name,
        target.modality,
        target.disease_ids,
        target.uniprot_id,
        target.hgnc_id,
        target.entrez_id,
        target.ensembl_gene_id,
        target.gene_type,
        target.pathway_ids,
        target.druggability,
        target.is_validated_target,
        NULL AS drug_id,
        NULL AS drug_name,
        NULL AS interaction_type,
        NULL AS mechanism_of_action,
        NULL AS drug_confidence,
        NULL AS associated_disease_id,
        NULL AS disease_name,
        NULL AS association_score,
        NULL AS evidence_type,
        NULL AS disease_confidence,
        target_xrefs.source_name,
        target_xrefs.source_id,
        target_xrefs.source_url
    FROM target
    JOIN target_xrefs ON target_xrefs.target_id = target.id
    ORDER BY row_sort, sort_1, sort_2, sort_3
"""


class TargetResponse(BaseModel):
    id: str
    symbol: str
    name: str
    modality: str = "unknown"
    disease_ids: List[str] = Field(default_factory=list)
    uniprot_id: Optional[str] = None
    hgnc_id: Optional[str] = None
    entrez_id: Optional[int] = None
    ensembl_gene_id: Optional[str] = None
    gene_type: str = "protein_coding"
    pathway_ids: List[str] = Field(default_factory=list)
    druggability: str = "unknown"
    is_validated_target: bool = False


class TargetDrugConnection(BaseModel):
    drug_id: str
    drug_name: str
    interaction_type: str = "unknown"
    mechanism_of_action: Optional[str] = None
    confidence: float = 1.0


class TargetDiseaseAssociation(BaseModel):
    disease_id: str
    disease_name: str
    association_score: Optional[float] = None
    evidence_type: Optional[str] = None
    confidence: float = 1.0


class TargetXref(BaseModel):
    source_name: str
    source_id: str
    source_url: Optional[str] = None


class TargetListResponse(BaseModel):
    total: int
    targets: List[TargetResponse] = Field(default_factory=list)


class TargetDetailResponse(TargetResponse):
    drug_connections: List[TargetDrugConnection] = Field(default_factory=list)
    disease_associations: List[TargetDiseaseAssociation] = Field(default_factory=list)
    xrefs: List[TargetXref] = Field(default_factory=list)


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def parse_json_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def build_target_response(row: sqlite3.Row) -> TargetResponse:
    return TargetResponse(
        id=row["id"],
        symbol=row["symbol"],
        name=row["name"],
        modality=row["modality"] or "unknown",
        disease_ids=parse_json_list(row["disease_ids"]),
        uniprot_id=row["uniprot_id"],
        hgnc_id=row["hgnc_id"],
        entrez_id=row["entrez_id"],
        ensembl_gene_id=row["ensembl_gene_id"],
        gene_type=row["gene_type"] or "protein_coding",
        pathway_ids=parse_json_list(row["pathway_ids"]),
        druggability=row["druggability"] or "unknown",
        is_validated_target=bool(row["is_validated_target"]),
    )


def _list_targets_sync(
    search: Optional[str],
    limit: int,
    offset: int,
) -> TargetListResponse:
    try:
        with get_db_connection() as connection:
            params: List[Any] = []
            where_clause = ""

            if search:
                search_term = f"%{search.lower()}%"
                where_clause = "WHERE LOWER(symbol) LIKE ? OR LOWER(name) LIKE ?"
                params.extend([search_term, search_term])

            total = connection.execute(
                f"SELECT COUNT(*) FROM targets {where_clause}", params
            ).fetchone()[0]

            rows = connection.execute(
                f"""
                SELECT {TARGET_COLUMNS}
                FROM targets
                {where_clause}
                ORDER BY symbol, id
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return TargetListResponse(
            total=total,
            targets=[build_target_response(row) for row in rows],
        )
    except sqlite3.Error as exc:
        logger.exception("Failed to load targets")
        raise HTTPException(status_code=500, detail="Failed to load targets") from exc


def _get_target_sync(target_id: str) -> TargetDetailResponse:
    try:
        with get_db_connection() as connection:
            rows = connection.execute(TARGET_DETAIL_QUERY, (target_id,)).fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail=f"Target '{target_id}' not found")

        base_target = build_target_response(rows[0])
        drug_connections = []
        disease_associations = []
        xrefs = []

        for row in rows:
            row_kind = row["row_kind"]
            if row_kind == "drug":
                drug_connections.append(
                    TargetDrugConnection(
                        drug_id=row["drug_id"],
                        drug_name=row["drug_name"],
                        interaction_type=row["interaction_type"] or "unknown",
                        mechanism_of_action=row["mechanism_of_action"],
                        confidence=row["drug_confidence"] or 0.0,
                    )
                )
            elif row_kind == "disease":
                disease_associations.append(
                    TargetDiseaseAssociation(
                        disease_id=row["associated_disease_id"],
                        disease_name=row["disease_name"],
                        association_score=row["association_score"],
                        evidence_type=row["evidence_type"],
                        confidence=row["disease_confidence"] or 0.0,
                    )
                )
            elif row_kind == "xref":
                xrefs.append(
                    TargetXref(
                        source_name=row["source_name"],
                        source_id=row["source_id"],
                        source_url=row["source_url"],
                    )
                )

        return TargetDetailResponse(
            **base_target.model_dump(),
            drug_connections=drug_connections,
            disease_associations=disease_associations,
            xrefs=xrefs,
        )
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        logger.exception("Failed to load target detail for %s", target_id)
        raise HTTPException(status_code=500, detail="Failed to load target") from exc


@router.get("/targets", response_model=TargetListResponse)
async def list_targets(
    search: Annotated[
        Optional[str], Query(description="Search target symbol or name")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 50,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
):
    return await run_in_threadpool(_list_targets_sync, search, limit, offset)


@router.get("/targets/{target_id}", response_model=TargetDetailResponse)
async def get_target(target_id: str):
    return await run_in_threadpool(_get_target_sync, target_id)
