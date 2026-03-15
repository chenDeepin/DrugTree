"""
DrugTree - Lineage Edge Model

Defines the schema for drug lineage edges, representing evolutionary relationships
between drugs (follow-on compounds, generation successors, resistance branches, etc.).

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 2)
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class EdgeType(str, Enum):
    """Type of lineage relationship between drugs"""

    follow_on = "follow_on"
    generation_successor = "generation_successor"
    resistance_branch = "resistance_branch"
    safety_branch = "safety_branch"
    combination_component = "combination_component"
    prodrug = "prodrug"
    metabolite = "metabolite"
    me_too = "me_too"


class Provenance(str, Enum):
    """Source of lineage edge (precedence: manual > curated > auto)"""

    auto = "auto"
    curated = "curated"
    manual = "manual"


class RationaleTag(str, Enum):
    """Tags explaining generation rationale for drug lineage relationships"""

    first_in_class = "first_in_class"
    me_too = "me_too"
    improved_pk = "improved_pk"
    combination = "combination"
    prodrug = "prodrug"
    metabolite = "metabolite"
    same_target = "same_target"
    similar_scaffold = "similar_scaffold"
    sequential_generation = "sequential_generation"


class LineageEdge(BaseModel):
    """
    Lineage edge representing drug evolution relationship.

    Edges connect drugs in a DAG (directed acyclic graph) where:
    - from_drug_id is the predecessor
    - to_drug_id is the successor
    - Confidence score indicates certainty (0.0-1.0)
    - Score breakdown provides explainability
    """

    edge_id: str = Field(
        ..., description="Unique edge identifier (e.g., 'atorvastatin<-lovastatin')"
    )
    from_drug_id: str = Field(
        ..., description="Predecessor drug ID (earlier in lineage)"
    )
    to_drug_id: str = Field(..., description="Successor drug ID (later in lineage)")
    edge_type: EdgeType = Field(..., description="Type of lineage relationship")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score [0.0-1.0] from hybrid scoring",
    )
    generation_rationale: List[str] = Field(
        default_factory=list,
        description="Tags explaining the generation rationale (e.g., 'first_in_class', 'me_too', 'improved_pk')",
    )
    rationale_tags: List[str] = Field(
        default_factory=list,
        deprecated="Use generation_rationale instead",
        description="DEPRECATED: Use generation_rationale",
    )
    score_breakdown: Dict[str, float] = Field(
        ...,
        description="Explainable score components (chronology, mechanism, scaffold weights)",
    )
    provenance: Provenance = Field(
        default=Provenance.auto,
        description="Source of edge (auto/curated/manual) - determines override precedence",
    )
    explanation: Optional[str] = Field(
        None, description="Human-readable explanation of the relationship"
    )
    schema_version: str = Field(
        default="1.1.0",
        description="Schema version for migration support",
        pattern=r"^\d+\.\d+\.\d+$",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "edge_id": "atorvastatin_to_lovastatin",
                "from_drug_id": "lovastatin",
                "to_drug_id": "atorvastatin",
                "edge_type": "generation_successor",
                "confidence": 0.87,
                "generation_rationale": [
                    "first_in_class",
                    "same_target",
                    "similar_scaffold",
                ],
                "score_breakdown": {
                    "chronology_score": 0.8,
                    "mechanism_score": 0.95,
                    "scaffold_score": 0.85,
                },
                "provenance": "auto",
                "explanation": "Atorvastatin is a 2nd-generation statin derived from lovastatin",
                "schema_version": "1.1.0",
            }
        }
    )


class LineageEdgeListResponse(BaseModel):
    """Response model for edge list endpoint"""

    total: int
    edges: List[LineageEdge]
