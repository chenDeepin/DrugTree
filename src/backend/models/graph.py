from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class GraphNodeType(str, Enum):
    drug = "drug"
    disease = "disease"
    target = "target"
    cluster = "cluster"


class GraphEdgeType(str, Enum):
    lineage = "lineage"
    disease_drug = "disease_drug"
    drug_target = "drug_target"
    family_member = "family_member"


class Evidence(BaseModel):
    source: str = Field(..., description="Evidence source identifier")
    source_type: Literal["literature", "database", "curated", "inferred"] = "inferred"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    description: Optional[str] = None
    url: Optional[str] = None


class GraphNodeRef(BaseModel):
    node_id: str = Field(
        ..., description="Namespaced node ID (e.g., 'drug:atorvastatin')"
    )
    node_type: GraphNodeType
    label: str = Field(..., description="Human-readable label")
    extra: dict[str, object] = Field(default_factory=dict)


class GraphEdgeRef(BaseModel):
    edge_id: str
    edge_type: GraphEdgeType
    source_id: str
    target_id: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    extra: dict[str, object] = Field(default_factory=dict)


class NeighborhoodResult(BaseModel):
    center_node: GraphNodeRef
    edges: list[GraphEdgeRef]
    neighbor_nodes: list[GraphNodeRef]
    max_hops_reached: int = 1


class SubgraphResult(BaseModel):
    nodes: list[GraphNodeRef]
    edges: list[GraphEdgeRef]
    total_nodes: int
    total_edges: int
