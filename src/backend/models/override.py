"""
DrugTree - Manual Override Model

Defines the schema for manual curation overrides, allowing human curators to
modify auto-generated lineage edges with explicit control.

Precedence Contract: manual > curated_rule > auto_rule > fallback

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 3)
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from .version import CURRENT_SCHEMA_VERSION


class OverrideAction(str, Enum):
    """Action to apply to a lineage edge or drug"""

    force_include = "force_include"
    force_exclude = "force_exclude"
    promote_edge = "promote_edge"
    demote_edge = "demote_edge"


class ManualOverride(BaseModel):
    """
    Manual override for curation control.

    Enables human curators to:
    - Force include/exclude drugs from families
    - Promote or demote edge confidence
    - Add rationale for auditing
    """

    override_id: str = Field(
        ..., description="Unique override identifier (e.g., 'override-001')"
    )
    drug_id: str = Field(..., description="Drug ID this override applies to")
    action: OverrideAction = Field(
        ...,
        description="Override action (force_include/force_exclude/promote_edge/demote_edge)",
    )
    target_edge_id: Optional[str] = Field(
        None,
        description="Edge ID to promote/demote (required for promote_edge/demote_edge actions)",
    )
    rationale: str = Field(
        ..., description="Human-readable explanation for this override"
    )
    curator: Optional[str] = Field(
        None, description="Curator identifier (e.g., 'curator@company.com')"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this override was created",
    )
    schema_version: str = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="Schema version for migration tracking",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "override_id": "override-001",
                "drug_id": "pitavastatin",
                "action": "promote_edge",
                "target_edge_id": "pitavastatin<-atorvastatin",
                "rationale": "Pitavastatin shows superior lipid-lowering in clinical trials vs atorvastatin",
                "curator": "curator@drugtree.org",
                "timestamp": "2024-03-15T10:30:00Z",
            }
        }
    )


class ManualOverrideListResponse(BaseModel):
    """Response model for override list endpoint"""

    total: int
    overrides: list[ManualOverride]
