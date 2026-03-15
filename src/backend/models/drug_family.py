"""
DrugTree - Drug Family Model

Defines the schema for drug families, representing groups of drugs that share
common characteristics (target, mechanism, scaffold, or program lineage).

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 1)
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class FamilyBasis(str, Enum):
    """Basis for drug family grouping"""

    target = "target"
    mechanism = "mechanism"
    scaffold = "scaffold"
    program_lineage = "program_lineage"


class DrugFamily(BaseModel):
    """
    Drug family model representing a group of related drugs.

    Families enable:
    - Multi-membership (drug can belong to multiple families)
    - Genealogy tracking (which families evolved from others)
    - Cross-ATC navigation (families can span therapeutic areas)
    """

    family_id: str = Field(
        ..., description="Unique family identifier (e.g., 'statin', 'sglt2-inhibitor')"
    )
    label: str = Field(
        ...,
        description="Human-readable family name (e.g., 'HMG-CoA Reductase Inhibitors')",
    )
    family_basis: FamilyBasis = Field(
        ...,
        description="Basis for family grouping (target/mechanism/scaffold/program_lineage)",
    )
    prototype_drug_id: str = Field(
        ...,
        description="Drug ID of the prototype/first-in-class drug (e.g., 'lovastatin')",
    )
    member_drug_ids: List[str] = Field(
        default_factory=list,
        description="List of drug IDs belonging to this family",
    )
    representative_target_ids: List[str] = Field(
        default_factory=list,
        description="List of target IDs (UniProt/ChEMBL) this family targets",
    )
    schema_version: str = Field(
        default="1.1.0",
        description="Schema version for migration support",
        pattern=r"^\d+\.\d+\.\d+$",
    )

    description: Optional[str] = Field(
        None, description="Brief description of the drug family"
    )
    atc_codes: List[str] = Field(
        default_factory=list,
        description="ATC codes associated with this family",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "family_id": "statin",
                "label": "HMG-CoA Reductase Inhibitors",
                "family_basis": "mechanism",
                "prototype_drug_id": "lovastatin",
                "member_drug_ids": [
                    "lovastatin",
                    "simvastatin",
                    "atorvastatin",
                    "rosuvastatin",
                ],
                "representative_target_ids": ["P04035"],
                "schema_version": "1.0.0",
                "description": "Statins lower cholesterol by inhibiting HMG-CoA reductase",
                "atc_codes": ["C10AA"],
            }
        }
    )


class DrugFamilyListResponse(BaseModel):
    """Response model for family list endpoint"""

    total: int
    families: List[DrugFamily]
