"""
DrugTree - Drugs Router

REST API endpoints for drug data, lineage, and disease hierarchy.
"""

from typing import Any, Dict, List, Optional

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..models.drug import Drug, DrugListResponse, DrugFilterParams
from ..models.lineage import LineageEdge
from ..services.graph_index import get_graph_index, GraphIndex
from ..services.tree_builder import TreeBuilder, GenealogyTree

# Path to drug data
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
FRONTEND_DATA_DIR = Path(__file__).parent.parent.parent / "frontend" / "data"
DRUGS_FILE = FRONTEND_DATA_DIR / "drugs.json"
DRUGS_FULL_FILE = FRONTEND_DATA_DIR / "drugs-full.json"
BODY_ONTOLOGY_FILE = DATA_DIR / "ontology" / "body_ontology.json"


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


def load_drugs() -> List[Drug]:
    """Load drugs from JSON file"""
    try:
        with open(DRUGS_FILE, "r") as f:
            data = json.load(f)
            # Handle both formats: array or {"drugs": [...]}
            drugs_list = data if isinstance(data, list) else data.get("drugs", [])
            return [Drug(**drug) for drug in drugs_list]
    except FileNotFoundError:
        with open(DRUGS_FULL_FILE, "r") as f:
            data = json.load(f)
            drugs_list = data if isinstance(data, list) else data.get("drugs", [])
            return [Drug(**drug) for drug in drugs_list]
    except Exception as e:
        print(f"Error loading drugs: {e}")
        return []


def load_drugs_full() -> List[Dict[str, Any]]:
    try:
        with open(DRUGS_FULL_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading drugs-full.json: {e}")
        return []


def load_body_ontology() -> Dict[str, Any]:
    try:
        with open(BODY_ONTOLOGY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading body ontology: {e}")
        return {}


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
    limit: int = 100,
    offset: int = 0,
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
        search_lower = search.lower()
        filtered_drugs = [
            d
            for d in filtered_drugs
            if search_lower in d.name.lower()
            or any(search_lower in str(t).lower() for t in (d.targets or []))
            or (d.class_name and search_lower in d.class_name.lower())
            or any(search_lower in str(s).lower() for s in (d.synonyms or []))
        ]

    # Apply pagination
    total = len(filtered_drugs)
    paginated_drugs = filtered_drugs[offset : offset + limit]

    return DrugListResponse(total=total, drugs=paginated_drugs)


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
async def get_drugs_by_category(category: str):
    """
    Get all drugs in a specific ATC category.

    - **category**: ATC category code (A-V)
    """
    drugs = load_drugs()
    filtered = [d for d in drugs if d.atc_category == category.upper()]

    return DrugListResponse(total=len(filtered), drugs=filtered)


@router.get("/drugs/search/{query}", response_model=DrugListResponse)
async def search_drugs(query: str):
    """
    Search drugs by name, target, class, or synonyms.

    - **query**: Search query string
    """
    drugs = load_drugs()
    query_lower = query.lower()

    filtered = [
        d
        for d in drugs
        if query_lower in d.name.lower()
        or any(query_lower in str(t).lower() for t in (d.targets or []))
        or (d.class_name and query_lower in d.class_name.lower())
        or any(query_lower in str(s).lower() for s in (d.synonyms or []))
        or (d.indication and query_lower in d.indication.lower())
    ]

    return DrugListResponse(total=len(filtered), drugs=filtered)


@router.get("/categories")
async def list_categories():
    """
    List all ATC categories with drug counts.
    """
    drugs = load_drugs()

    categories = {}
    for drug in drugs:
        cat = drug.atc_category
        if cat:
            categories[cat] = categories.get(cat, 0) + 1

    return {
        "categories": [
            {"code": code, "count": count} for code, count in sorted(categories.items())
        ]
    }


@router.get("/stats")
async def get_statistics():
    """
    Get drug database statistics.
    """
    drugs = load_drugs()

    categories = {}
    phases = {}
    companies = set()
    targets = set()

    for drug in drugs:
        # Count by category
        if drug.atc_category:
            categories[drug.atc_category] = categories.get(drug.atc_category, 0) + 1

        # Count by phase
        if drug.phase:
            phases[drug.phase] = phases.get(drug.phase, 0) + 1

        # Unique companies
        if drug.company:
            companies.add(drug.company)

        # Unique targets
        if drug.targets:
            targets.update(drug.targets)

    return {
        "total_drugs": len(drugs),
        "categories": categories,
        "phases": phases,
        "unique_companies": len(companies),
        "unique_targets": len(targets),
    }


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
async def get_disease_tree(disease_id: str):
    """
    Get body region and drugs for a specific disease.

    Returns the disease details, associated body region, and drugs
    that treat conditions related to this disease.

    - **disease_id**: Disease identifier (e.g., 'hypertension', 'type_2_diabetes')
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
        drugs=matching_drugs[:20],
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


@router.get("/graph/stats")
async def get_graph_statistics():
    """Get statistics about the drug graph index."""
    graph_index = get_graph_index()

    return {
        "stats": graph_index.stats,
        "families": graph_index.get_all_families()[:10],
    }
