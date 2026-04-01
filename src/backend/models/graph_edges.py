from typing import Optional

from pydantic import BaseModel, Field, computed_field


class DrugTargetEdge(BaseModel):
    id: Optional[int] = None
    drug_id: str
    target_id: str
    interaction_type: str = "unknown"
    mechanism_of_action: Optional[str] = None
    evidence_sources: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    clinical_phase: Optional[str] = None
    retrieved_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def edge_id(self) -> str:
        return f"drug_target:{self.drug_id}:{self.target_id}"


class TargetDiseaseEdge(BaseModel):
    id: Optional[int] = None
    target_id: str
    disease_id: str
    association_score: Optional[float] = None
    evidence_type: str = "genetic_association"
    evidence_sources: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    retrieved_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def edge_id(self) -> str:
        return f"target_disease:{self.target_id}:{self.disease_id}"


class DrugBodyRegionEdge(BaseModel):
    id: Optional[int] = None
    drug_id: str
    body_region: str
    relationship_type: str = "primary"
    system_flag: bool = False
    placement_basis: Optional[str] = None
    evidence_sources: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def edge_id(self) -> str:
        return f"drug_bodyregion:{self.drug_id}:{self.body_region}"


class DrugXref(BaseModel):
    drug_id: str
    source_name: str
    source_id: str
    source_url: Optional[str] = None
    is_primary: bool = False


class TargetXref(BaseModel):
    target_id: str
    source_name: str
    source_id: str
    source_url: Optional[str] = None
    is_primary: bool = False


class EvidenceSource(BaseModel):
    source_name: str
    source_type: str = "database"
    base_url: Optional[str] = None
    version: Optional[str] = None
    license: Optional[str] = None
    last_retrieved: Optional[str] = None
    description: Optional[str] = None
