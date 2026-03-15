"""
DrugTree - Pydantic Models for Disease Universe

Defines schemas for diseases, targets, drug-disease edges, and regional approvals.
Supports the Disease Universe feature: disease → target → molecule exploration.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class PrevalenceTier(str, Enum):
    """Disease prevalence classification"""

    ULTRA_RARE = "ultra_rare"  # < 10K patients globally
    RARE = "rare"  # 10K-100K patients globally
    UNCOMMON = "uncommon"  # 100K-1M patients globally
    COMMON = "common"  # > 1M patients globally
    UNKNOWN = "unknown"


class EvidenceLevel(str, Enum):
    """Evidence strength for drug-disease relationships"""

    APPROVED = "approved"  # Regulatory approval
    PHASE_III = "phase_iii"  # Phase III clinical trial
    PHASE_II = "phase_ii"  # Phase II clinical trial
    PHASE_I = "phase_i"  # Phase I clinical trial
    PRECLINICAL = "preclinical"  # Preclinical data only
    HYPOTHESIZED = "hypothesized"  # Computational/biological hypothesis
    UNKNOWN = "unknown"


class IndicationType(str, Enum):
    """Type of drug-disease indication"""

    PRIMARY = "primary"  # Primary approved indication
    ADJUVANT = "adjuvant"  # Used with primary treatment
    NEOADJUVANT = "neoadjuvant"  # Before primary treatment
    MAINTENANCE = "maintenance"  # Long-term disease control
    PALLIATIVE = "palliative"  # Symptom relief
    OFF_LABEL = "off_label"  # Off-label use with evidence
    INVESTIGATIONAL = "investigational"  # Under investigation


class Region(str, Enum):
    """Regulatory regions (v1: FDA only)"""

    FDA = "FDA"  # United States


class ApprovalStatus(str, Enum):
    """Regulatory approval status"""

    APPROVED = "approved"
    APPROVED_WITH_WARNINGS = "approved_with_warnings"
    UNDER_REVIEW = "under_review"
    WITHDRAWN = "withdrawn"
    NOT_SUBMITTED = "not_submitted"


class Modality(str, Enum):
    """Target modality"""

    INHIBITOR = "inhibitor"
    ACTIVATOR = "activator"
    AGONIST = "agonist"
    ANTAGONIST = "antagonist"
    MODULATOR = "modulator"
    BLOCKER = "blocker"
    UNKNOWN = "unknown"


# =============================================================================
# DISEASE MODELS
# =============================================================================


class DiseaseBase(BaseModel):
    """Base disease model with common fields"""

    id: str = Field(..., description="Unique disease identifier (e.g., 'glioma')")
    canonical_name: str = Field(
        ..., description="Canonical disease name (e.g., 'Glioma')"
    )
    synonyms: List[str] = Field(
        default_factory=list, description="Alternative names and synonyms"
    )


class Disease(DiseaseBase):
    """Full disease model with all metadata"""

    # Anatomy mapping (from body_ontology.json)
    body_region: str = Field(
        ..., description="Primary body region ID (e.g., 'brain_cns')"
    )
    anatomy_nodes: List[str] = Field(
        default_factory=list, description="Specific anatomy nodes within region"
    )

    # Orphan disease flags
    orphan_flag: bool = Field(False, description="True if ultra-rare or rare disease")
    prevalence_tier: PrevalenceTier = Field(
        PrevalenceTier.UNKNOWN, description="Prevalence classification"
    )
    prevalence_count: Optional[int] = Field(
        None, description="Estimated patient count globally"
    )

    # Evidence and mechanism
    evidence_level: EvidenceLevel = Field(
        EvidenceLevel.UNKNOWN, description="Overall evidence strength"
    )
    mechanism_summary: Optional[str] = Field(
        None, description="2-3 sentence mechanism explanation (no medical advice)"
    )
    mechanism_citation: Optional[str] = Field(
        None, description="Citation for mechanism (DOI/PMID)"
    )

    # Target and drug counts
    target_count: int = Field(0, description="Number of associated targets")
    approved_drug_count: int = Field(0, description="Number of approved drugs")
    clinical_drug_count: int = Field(
        0, description="Number of drugs in clinical trials"
    )

    # External IDs
    mondo_id: Optional[str] = Field(None, description="MONDO ontology ID")
    doid_id: Optional[str] = Field(None, description="Disease Ontology ID")
    icd10_code: Optional[str] = Field(None, description="ICD-10 code")

    class Config:
        use_enum_values = True


class DiseaseSummary(DiseaseBase):
    """Lightweight disease model for list views"""

    body_region: str
    orphan_flag: bool = False
    prevalence_tier: PrevalenceTier = PrevalenceTier.UNKNOWN
    approved_drug_count: int = 0

    class Config:
        use_enum_values = True


class DiseaseListResponse(BaseModel):
    """Response model for disease list endpoint"""

    total: int = Field(..., description="Total number of diseases matching query")
    diseases: List[Disease] = Field(..., description="List of diseases")


class DiseaseFilterParams(BaseModel):
    """Query parameters for filtering diseases"""

    region: Optional[str] = Field(None, description="Filter by body region ID")
    orphan_only: bool = Field(False, description="Show only orphan diseases")
    has_approved_drugs: Optional[bool] = Field(
        None, description="Filter by approved drug availability"
    )
    search: Optional[str] = Field(None, description="Search query (name, synonyms)")
    prevalence_tier: Optional[PrevalenceTier] = Field(
        None, description="Filter by prevalence tier"
    )
    limit: int = Field(100, ge=1, le=1000, description="Max results to return")
    offset: int = Field(0, ge=0, description="Pagination offset")


# =============================================================================
# TARGET MODELS
# =============================================================================


class TargetBase(BaseModel):
    """Base target model"""

    id: str = Field(..., description="Unique target identifier (e.g., 'EGFR')")
    symbol: str = Field(..., description="Gene/protein symbol")
    name: str = Field(..., description="Full target name")


class Target(TargetBase):
    """Full target model with all metadata"""

    modality: Modality = Field(Modality.UNKNOWN, description="Target modality")
    disease_ids: List[str] = Field(
        default_factory=list, description="Associated disease IDs"
    )

    # External IDs
    uniprot_id: Optional[str] = Field(None, description="UniProt ID")
    hgnc_id: Optional[str] = Field(None, description="HGNC gene ID")
    entrez_id: Optional[int] = Field(None, description="Entrez Gene ID")

    class Config:
        use_enum_values = True


class TargetListResponse(BaseModel):
    """Response model for target list endpoint"""

    total: int = Field(..., description="Total number of targets matching query")
    targets: List[Target] = Field(..., description="List of targets")


# =============================================================================
# DRUG-DISEASE EDGE MODELS
# =============================================================================


class DrugDiseaseEdgeBase(BaseModel):
    """Base drug-disease relationship model"""

    drug_id: str = Field(..., description="Drug ID")
    disease_id: str = Field(..., description="Disease ID")


class DrugDiseaseEdge(DrugDiseaseEdgeBase):
    """Full drug-disease relationship with evidence"""

    indication_type: IndicationType = Field(
        IndicationType.PRIMARY, description="Type of indication"
    )
    evidence_source: str = Field(
        ..., description="Evidence source (e.g., 'FDA', 'NCT123456')"
    )
    evidence_level: EvidenceLevel = Field(
        EvidenceLevel.UNKNOWN, description="Evidence strength"
    )
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score (0-1)")
    phase_context: Optional[str] = Field(
        None, description="Clinical trial phase context"
    )

    class Config:
        use_enum_values = True


class DrugDiseaseEdgeListResponse(BaseModel):
    """Response model for drug-disease edges"""

    total: int = Field(..., description="Total number of edges matching query")
    edges: List[DrugDiseaseEdge] = Field(..., description="List of drug-disease edges")


# =============================================================================
# REGIONAL APPROVAL MODELS
# =============================================================================


class RegionalApprovalBase(BaseModel):
    """Base regional approval model"""

    drug_id: str = Field(..., description="Drug ID")
    region: Region = Field(..., description="Regulatory region")


class RegionalApproval(RegionalApprovalBase):
    """Full regional approval status"""

    status: ApprovalStatus = Field(
        ApprovalStatus.NOT_SUBMITTED, description="Approval status"
    )
    approval_date: Optional[str] = Field(None, description="Approval date (ISO 8601)")
    label_source: Optional[str] = Field(None, description="Source URL for label info")

    class Config:
        use_enum_values = True


class RegionalApprovalListResponse(BaseModel):
    """Response model for regional approvals"""

    total: int = Field(..., description="Total number of approvals")
    approvals: List[RegionalApproval] = Field(..., description="List of approvals")


# =============================================================================
# DISEASE UNIVERSE STATS
# =============================================================================


class DiseaseUniverseStats(BaseModel):
    """Statistics for the Disease Universe"""

    total_diseases: int = Field(..., description="Total diseases in database")
    orphan_diseases: int = Field(..., description="Orphan disease count")
    total_targets: int = Field(..., description="Total targets")
    total_approved_drugs: int = Field(..., description="Total approved drugs")
    total_clinical_drugs: int = Field(..., description="Total drugs in clinical trials")
    diseases_by_region: dict = Field(
        default_factory=dict, description="Disease counts by body region"
    )
    diseases_by_prevalence: dict = Field(
        default_factory=dict, description="Disease counts by prevalence tier"
    )
