"""
DrugTree - Drugs Router

REST API endpoints for drug data, lineage, and disease hierarchy.
"""

import json
from typing import Annotated, Any, Dict, List, Optional

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..models.drug import Drug, DrugListResponse, DrugFilterParams
from ..models.drug_family import DrugFamily, DrugFamilyListResponse
from ..models.lineage import LineageEdge, LineageEdgeListResponse
from ..services.graph_index import GraphIndex, get_graph_index
from ..services.data_snapshot import get_data_snapshot_service
from ..services.tree_builder import GenealogyTree, TreeBuilder

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
snapshot_service = get_data_snapshot_service()
DRUGS_FILE = DATA_DIR / "drugs.json"


class TreeNodeResponse(BaseModel):
    """Response model for a tree node."""

    id: str = Field(..., description="Drug ID")
    name: str = Field(..., description="Drug name")
    depth: int = Field(..., description="Depth in tree (0 = root)")
    children: List["TreeNodeResponse"] = Field(
        default_factory=list, description="Child nodes (predecessors)"
    )
    parent_ids: List[str] = Field(
        default_factory=list, description="All parent drug IDs"
    )
    primary_parent_id: Optional[str] = Field(None, description="Primary parent drug ID")


class TreeLinkResponse(BaseModel):
    """Response model for a tree link."""

    source: str = Field(..., description="Source drug ID (predecessor)")
    target: str = Field(..., description="Target drug ID (successor)")
    confidence: float = Field(..., description="Confidence score (0.0-1.0)")
    edge_type: str = Field(..., description="Type of relationship")
    is_cross_link: bool = Field(
        default=False, description="True for multi-parent relationships"
    )


class TreeStatisticsResponse(BaseModel):
    """Response model for tree statistics."""

    total_nodes: int = Field(..., description="Total nodes in tree")
    total_generations: int = Field(..., description="Number of generations")
    total_links: int = Field(..., description="Primary links count")
    total_cross_links: int = Field(..., description="Cross-links count")
    avg_confidence: float = Field(..., description="Average confidence score")


class LineageResponse(BaseModel):
    """Response model for lineage endpoint."""

    drug_id: str = Field(..., description="Drug ID for this lineage")
    drug_name: str = Field(..., description="Drug name")
    tree: Dict[str, Any] = Field(
        ..., description="Tree structure with root, nodes, links, cross_links"
    )
    statistics: TreeStatisticsResponse = Field(..., description="Tree statistics")


class DiseaseNodeResponse(BaseModel):
    """Response model for disease node in hierarchy."""

    id: str = Field(..., description="Disease ID")
    display_name: str = Field(..., description="Human-readable name")
    region: str = Field(..., description="Body region ID")
    nodes: List[str] = Field(
        default_factory=list, description="Anatomical nodes affected"
    )


class BodyRegionResponse(BaseModel):
    """Response model for body region."""

    id: str = Field(..., description="Region ID")
    display_name: str = Field(..., description="Human-readable name")
    icon: str = Field(..., description="Emoji icon")
    description: str = Field(..., description="Region description")
    internal_nodes: List[str] = Field(
        default_factory=list, description="Internal anatomical nodes"
    )
    diseases: List[DiseaseNodeResponse] = Field(
        default_factory=list, description="Diseases in this region"
    )


class DiseaseTreeResponse(BaseModel):
    """Response model for disease tree endpoint."""

    disease_id: str = Field(..., description="Disease ID")
    disease: Optional[DiseaseNodeResponse] = Field(None, description="Disease details")
    region: Optional[BodyRegionResponse] = Field(
        None, description="Body region details"
    )
    drugs: List[Dict[str, Any]] = Field(
        default_factory=list, description="Drugs for this disease"
    )
    total: int = Field(0, description="Total matching drugs before pagination")
    limit: int = Field(20, description="Requested result limit")
    offset: int = Field(0, description="Requested result offset")


def load_drugs() -> List[Drug]:
    snapshot = snapshot_service.get_snapshot()
    return [Drug(**drug) for drug in snapshot.drugs]


def load_drugs_full() -> List[Dict[str, Any]]:
    snapshot = snapshot_service.get_snapshot()
    return snapshot.drugs


def load_body_ontology() -> Dict[str, Any]:
    snapshot = snapshot_service.get_snapshot()
    return snapshot.body_ontology


def matches_drug_search(drug: Any, query: str) -> bool:
    query_lower = query.lower()
    if isinstance(drug, dict):
        name = str(drug.get("name") or "")
        targets = drug.get("targets") or []
        class_name = drug.get("class") or drug.get("class_name")
        synonyms = drug.get("synonyms") or []
        company = drug.get("company")
        indication = drug.get("indication")
    else:
        name = drug.name
        targets = drug.targets or []
        class_name = drug.class_name
        synonyms = drug.synonyms or []
        company = drug.company
        indication = drug.indication
    return (
        query_lower in name.lower()
        or any(query_lower in str(target).lower() for target in targets)
        or (class_name is not None and query_lower in str(class_name).lower())
        or any(query_lower in str(synonym).lower() for synonym in synonyms)
        or (company is not None and query_lower in str(company).lower())
        or (indication is not None and query_lower in str(indication).lower())
    )


def get_drug_atc_category(drug: Any) -> Optional[str]:
    if isinstance(drug, dict):
        category = drug.get("atc_category")
    else:
        category = drug.atc_category
    return str(category) if category else None


def save_drugs(drugs: List[Drug]):
    """Save drugs to JSON file"""
    try:
        with open(DRUGS_FILE, "w") as f:
            json.dump({"drugs": [drug.model_dump() for drug in drugs]}, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving drugs: {e}")
        return False


router = APIRouter(prefix="/api/v1", tags=["drugs"])


@router.get("/drugs", response_model=DrugListResponse)
async def list_drugs(
    category: Optional[str] = None,
    search: Optional[str] = None,
    phase: Optional[str] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
):
    """
    List all drugs with optional filtering.

    - **category**: Filter by ATC category (A-V)
    - **search**: Search in name, targets, class, synonyms
    - **phase**: Filter by clinical phase (I, II, III, IV)
    - **limit**: Max results to return (default 100)
    - **offset**: Pagination offset (default 0)
    """
    drugs = load_drugs()

    # Apply filters
    filtered_drugs = drugs

    if category:
        filtered_drugs = [
            d for d in filtered_drugs if d.atc_category == category.upper()
        ]

    if phase:
        filtered_drugs = [d for d in filtered_drugs if d.phase == phase]

    if search:
        filtered_drugs = [d for d in filtered_drugs if matches_drug_search(d, search)]

    # Apply pagination
    total = len(filtered_drugs)
    paginated_drugs = filtered_drugs[offset : offset + limit]

    return DrugListResponse(total=total, drugs=paginated_drugs)


@router.get("/drugs/search", response_model=DrugListResponse)
async def search_drugs(
    q: Annotated[str, Query(description="Search query text")],
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
):
    """
    Search drugs by name, target, class, or synonyms.

    - **q**: Search query string
    - **limit**: Max results to return (default 100)
    - **offset**: Pagination offset (default 0)
    """
    drugs = load_drugs()
    filtered = [d for d in drugs if matches_drug_search(d, q)]
    return DrugListResponse(total=len(filtered), drugs=filtered[offset : offset + limit])


async def search_drugs_query(q: str, limit: int = 100, offset: int = 0):
    return await search_drugs(q=q, limit=limit, offset=offset)


@router.get("/drugs/{drug_id}", response_model=Drug)
async def get_drug(drug_id: str):
    """
    Get a specific drug by ID.

    - **drug_id**: Unique drug identifier (e.g., 'atorvastatin')
    """
    drugs = load_drugs()

    for drug in drugs:
        if drug.id == drug_id:
            return drug

    raise HTTPException(status_code=404, detail=f"Drug '{drug_id}' not found")


@router.get("/drugs/category/{category}", response_model=DrugListResponse)
async def get_drugs_by_category(
    category: str,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
):
    """
    Get all drugs in a specific ATC category.

    - **category**: ATC category code (A-V)
    - **limit**: Max results to return (default 100)
    - **offset**: Pagination offset (default 0)
    """
    drugs = load_drugs()
    filtered = [d for d in drugs if get_drug_atc_category(d) == category.upper()]

    return DrugListResponse(total=len(filtered), drugs=filtered[offset : offset + limit])


@router.get("/lineage/{drug_id}", response_model=LineageResponse)
async def get_drug_lineage(drug_id: str, threshold: float = 0.5):
    """
    Get genealogy tree for a drug showing its evolutionary history.

    The tree shows how a drug was derived from earlier drugs:
    - Root = the target drug
    - Children = predecessor drugs (drugs it was derived from)
    - Cross-links = secondary parent relationships (multi-parent drugs)

    - **drug_id**: Drug identifier (e.g., 'atorvastatin')
    - **threshold**: Minimum confidence to include edge (default 0.5)
    """
    graph_index = get_graph_index()

    node = graph_index.get_node(drug_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Drug '{drug_id}' not found")

    all_edges = graph_index.get_all_edges()

    if not all_edges:
        raise HTTPException(
            status_code=400, detail=f"Drug '{drug_id}' has no lineage data available"
        )

    builder = TreeBuilder()

    try:
        tree = builder.build_genealogy_tree(drug_id, all_edges, threshold=threshold)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def tree_node_to_dict(tn) -> Dict[str, Any]:
        return {
            "id": tn.id,
            "name": tn.name,
            "depth": tn.depth,
            "children": [tree_node_to_dict(child) for child in tn.children],
            "parent_ids": tn.parent_ids,
            "primary_parent_id": tn.primary_parent_id,
        }

    tree_dict = {
        "root": tree_node_to_dict(tree.root),
        "nodes": [{"id": n.id, "name": n.name, "depth": n.depth} for n in tree.nodes],
        "links": [
            {
                "source": link.source,
                "target": link.target,
                "confidence": link.confidence,
                "edge_type": link.edge_type,
                "is_cross_link": link.is_cross_link,
            }
            for link in tree.links
        ],
        "cross_links": [
            {
                "source": link.source,
                "target": link.target,
                "confidence": link.confidence,
                "edge_type": link.edge_type,
                "is_cross_link": link.is_cross_link,
            }
            for link in tree.cross_links
        ],
    }

    stats = builder.get_tree_statistics(tree)

    return LineageResponse(
        drug_id=drug_id,
        drug_name=node.name,
        tree=tree_dict,
        statistics=TreeStatisticsResponse(
            total_nodes=stats["total_nodes"],
            total_generations=stats["total_generations"],
            total_links=stats["total_links"],
            total_cross_links=stats["total_cross_links"],
            avg_confidence=stats["avg_confidence"],
        ),
    )


@router.get("/tree/disease/{disease_id}", response_model=DiseaseTreeResponse)
async def get_disease_tree(
    disease_id: str,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Max associated drugs to return")
    ] = 20,
    offset: Annotated[int, Query(ge=0, description="Associated drug offset")] = 0,
):
    """
    Get body region and drugs for a specific disease.

    Returns the disease details, associated body region, and drugs
    that treat conditions related to this disease.

    - **disease_id**: Disease identifier (e.g., 'hypertension', 'type_2_diabetes')
    - **limit**: Max associated drugs to return (default 20, capped at 100)
    - **offset**: Associated drug offset (default 0)
    """
    ontology = load_body_ontology()

    if not ontology:
        raise HTTPException(status_code=500, detail="Body ontology not loaded")

    disease_to_anatomy = ontology.get("disease_to_anatomy", {})
    visible_regions = ontology.get("visible_regions", [])
    internal_ontology = ontology.get("internal_ontology", {})

    disease_entry = disease_to_anatomy.get(disease_id)
    if not disease_entry:
        raise HTTPException(
            status_code=404, detail=f"Disease '{disease_id}' not found in ontology"
        )

    region_id = disease_entry.get("region")
    anatomical_nodes = disease_entry.get("nodes", [])

    disease_response = DiseaseNodeResponse(
        id=disease_id,
        display_name=disease_id.replace("_", " ").title(),
        region=region_id,
        nodes=anatomical_nodes,
    )

    region_response = None
    for region in visible_regions:
        if region["id"] == region_id:
            region_diseases = []
            for d_id, d_entry in disease_to_anatomy.items():
                if d_entry.get("region") == region_id:
                    region_diseases.append(
                        DiseaseNodeResponse(
                            id=d_id,
                            display_name=d_id.replace("_", " ").title(),
                            region=region_id,
                            nodes=d_entry.get("nodes", []),
                        )
                    )

            region_response = BodyRegionResponse(
                id=region["id"],
                display_name=region["display_name"],
                icon=region["icon"],
                description=region["description"],
                internal_nodes=region["internal_nodes"],
                diseases=region_diseases,
            )
            break

    drugs_data = load_drugs_full()

    disease_keywords = disease_id.replace("_", " ").lower().split()
    disease_name = disease_id.replace("_", " ")

    matching_drugs = []
    for drug in drugs_data:
        indication = (drug.get("indication") or "").lower()
        targets = drug.get("targets") or []
        targets_str = " ".join(str(t) for t in targets).lower()

        if disease_name.lower() in indication:
            matching_drugs.append(drug)
        elif any(kw in indication or kw in targets_str for kw in disease_keywords):
            matching_drugs.append(drug)

    return DiseaseTreeResponse(
        disease_id=disease_id,
        disease=disease_response,
        region=region_response,
        drugs=matching_drugs[offset : offset + limit],
        total=len(matching_drugs),
        limit=limit,
        offset=offset,
    )


@router.get("/regions")
async def list_body_regions():
    """List all body regions from the ontology."""
    ontology = load_body_ontology()

    if not ontology:
        raise HTTPException(status_code=500, detail="Body ontology not loaded")

    visible_regions = ontology.get("visible_regions", [])

    return {
        "regions": [
            {
                "id": region["id"],
                "display_name": region["display_name"],
                "icon": region["icon"],
                "description": region["description"],
            }
            for region in visible_regions
        ]
    }


@router.get("/families", response_model=DrugFamilyListResponse)
async def list_families(
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
):
    """
    List all drug families from the graph index.

    Families are groups of drugs sharing a common target, mechanism, or scaffold.
    Computed from processed lineage data in ``data/processed/drug_families.json``.

    - **limit**: Max results (default 100)
    - **offset**: Pagination offset (default 0)
    """
    graph_index = get_graph_index()

    family_ids = graph_index.get_all_families()
    total = len(family_ids)
    page = family_ids[offset : offset + limit]

    families = []
    for fid in page:
        fam = graph_index.get_family(fid)
        if fam:
            families.append(fam)

    return DrugFamilyListResponse(total=total, families=families)


@router.get("/families/{family_id}", response_model=DrugFamily)
async def get_family(family_id: str):
    """
    Get a specific drug family by ID.

    - **family_id**: Family identifier (e.g., 'target_h__k__atpase_72250c9c')
    """
    graph_index = get_graph_index()

    family = graph_index.get_family(family_id)
    if not family:
        raise HTTPException(status_code=404, detail=f"Family '{family_id}' not found")

    return family


@router.get("/lineages", response_model=LineageEdgeListResponse)
async def list_lineages(
    drug_id: Optional[str] = None,
    edge_type: Optional[str] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
):
    """
    List all lineage edges from the graph index.

    Lineage edges represent evolutionary relationships between drugs
    (follow-on, generation successor, resistance branch, etc.).

    - **drug_id**: Filter to edges involving a specific drug
    - **edge_type**: Filter by edge type (follow_on, generation_successor, etc.)
    - **limit**: Max results (default 100)
    - **offset**: Pagination offset (default 0)
    """
    graph_index = get_graph_index()

    all_edges = graph_index.get_all_edges()

    if drug_id:
        all_edges = [
            e for e in all_edges if e.from_drug_id == drug_id or e.to_drug_id == drug_id
        ]

    if edge_type:
        all_edges = [e for e in all_edges if e.edge_type == edge_type]

    total = len(all_edges)
    paginated = all_edges[offset : offset + limit]

    return LineageEdgeListResponse(total=total, edges=paginated)


@router.get("/graph/stats")
async def get_graph_statistics():
    """Get statistics about the drug graph index."""
    graph_index = get_graph_index()

    return {
        "stats": graph_index.stats,
        "families": graph_index.get_all_families()[:10],
    }
