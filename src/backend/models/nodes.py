"""
DrugTree - Graph Node Models

Node models with type discrimination for unified graph queries.
Each node type has a namespaced full_id for collision-free identification.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, computed_field


class DiseaseNode(BaseModel):
    """Disease node for graph queries"""

    id: str = Field(..., description="Unique disease identifier (e.g., 'glioma')")
    node_type: Literal["disease"] = Field(
        default="disease", description="Node type discriminator"
    )
    canonical_name: str = Field(..., description="Canonical disease name")
    body_region: Optional[str] = Field(None, description="Primary body region ID")

    @computed_field  # type: ignore[misc]
    @property
    def full_id(self) -> str:
        return f"disease:{self.id}"


class TargetNode(BaseModel):
    """Target node for graph queries"""

    id: str = Field(..., description="Unique target identifier (e.g., 'EGFR')")
    node_type: Literal["target"] = Field(
        default="target", description="Node type discriminator"
    )
    symbol: str = Field(..., description="Gene/protein symbol")
    name: Optional[str] = Field(None, description="Full target name")
    disease_ids: List[str] = Field(
        default_factory=list, description="Associated disease IDs"
    )

    @computed_field  # type: ignore[misc]
    @property
    def full_id(self) -> str:
        return f"target:{self.id}"


class ClusterNode(BaseModel):
    """Cluster node for drug family groupings"""

    id: str = Field(..., description="Unique cluster identifier (e.g., 'statins')")
    node_type: Literal["cluster"] = Field(
        default="cluster", description="Node type discriminator"
    )
    label: str = Field(..., description="Human-readable cluster label")
    member_drug_ids: List[str] = Field(
        default_factory=list, description="Drug IDs in this cluster"
    )

    @computed_field  # type: ignore[misc]
    @property
    def full_id(self) -> str:
        return f"cluster:{self.id}"
