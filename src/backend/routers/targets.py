"""
DrugTree - Targets Router

REST API endpoints for protein target data stored in SQLite.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

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


@router.get("/targets", response_model=TargetListResponse)
async def list_targets(
    search: Optional[str] = Query(None, description="Search target symbol or name"),
    limit: int = Query(50, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
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


@router.get("/targets/{target_id}", response_model=TargetDetailResponse)
async def get_target(target_id: str):
    try:
        with get_db_connection() as connection:
            target_row = connection.execute(
                f"SELECT {TARGET_COLUMNS} FROM targets WHERE id = ?",
                (target_id,),
            ).fetchone()

            if target_row is None:
                raise HTTPException(
                    status_code=404, detail=f"Target '{target_id}' not found"
                )

            drug_rows = connection.execute(
                """
                SELECT
                    drug_target_edges.drug_id,
                    COALESCE(drugs.name, drug_target_edges.drug_id) AS drug_name,
                    drug_target_edges.interaction_type,
                    drug_target_edges.mechanism_of_action,
                    drug_target_edges.confidence
                FROM drug_target_edges
                LEFT JOIN drugs ON drugs.id = drug_target_edges.drug_id
                WHERE drug_target_edges.target_id = ?
                ORDER BY drug_target_edges.confidence DESC, drug_name ASC
                """,
                (target_id,),
            ).fetchall()

            disease_rows = connection.execute(
                """
                SELECT
                    target_disease_edges.disease_id,
                    COALESCE(diseases.canonical_name, target_disease_edges.disease_id) AS disease_name,
                    target_disease_edges.association_score,
                    target_disease_edges.evidence_type,
                    target_disease_edges.confidence
                FROM target_disease_edges
                LEFT JOIN diseases ON diseases.id = target_disease_edges.disease_id
                WHERE target_disease_edges.target_id = ?
                ORDER BY target_disease_edges.confidence DESC,
                         target_disease_edges.association_score DESC,
                         disease_name ASC
                """,
                (target_id,),
            ).fetchall()

            xref_rows = connection.execute(
                """
                SELECT source_name, source_id, source_url
                FROM target_xrefs
                WHERE target_id = ?
                ORDER BY is_primary DESC, source_name ASC, source_id ASC
                """,
                (target_id,),
            ).fetchall()

        base_target = build_target_response(target_row)
        return TargetDetailResponse(
            **base_target.model_dump(),
            drug_connections=[
                TargetDrugConnection(
                    drug_id=row["drug_id"],
                    drug_name=row["drug_name"],
                    interaction_type=row["interaction_type"] or "unknown",
                    mechanism_of_action=row["mechanism_of_action"],
                    confidence=row["confidence"] or 0.0,
                )
                for row in drug_rows
            ],
            disease_associations=[
                TargetDiseaseAssociation(
                    disease_id=row["disease_id"],
                    disease_name=row["disease_name"],
                    association_score=row["association_score"],
                    evidence_type=row["evidence_type"],
                    confidence=row["confidence"] or 0.0,
                )
                for row in disease_rows
            ],
            xrefs=[
                TargetXref(
                    source_name=row["source_name"],
                    source_id=row["source_id"],
                    source_url=row["source_url"],
                )
                for row in xref_rows
            ],
        )
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        logger.exception("Failed to load target detail for %s", target_id)
        raise HTTPException(status_code=500, detail="Failed to load target") from exc
