"""
DrugTree - Pydantic Models for Drug Data

Defines the data schema for drugs, matching the frontend DrugTreeApp expectations.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class DrugBase(BaseModel):
    """Base drug model with common fields"""

    id: str = Field(..., description="Unique drug identifier (e.g., 'atorvastatin')")
    name: str = Field(..., description="Drug name")
    smiles: Optional[str] = Field(
        None, description="SMILES notation for molecular structure"
    )
    inchikey: Optional[str] = Field(None, description="InChIKey identifier")


class Drug(DrugBase):
    """Full drug model with all metadata"""

    atc_code: str = Field(..., description="WHO ATC code (e.g., 'C10AA05')")
    atc_category: str = Field(..., description="ATC Level 1 category code (e.g., 'C')")
    molecular_weight: Optional[float] = Field(
        None, description="Molecular weight in Daltons"
    )
    phase: Optional[str] = Field(None, description="Clinical trial phase (I/II/III/IV)")
    year_approved: Optional[int] = Field(None, description="Year of FDA approval")
    generation: Optional[int] = Field(None, description="Drug generation (1, 2, 3...)")
    indication: Optional[str] = Field(None, description="Therapeutic indication")
    targets: List[str] = Field(default_factory=list, description="Drug targets")
    company: Optional[str] = Field(None, description="Pharmaceutical company")
    synonyms: List[str] = Field(
        default_factory=list, description="Drug synonyms/brand names"
    )
    class_name: Optional[str] = Field(
        None, alias="class", description="Drug class (e.g., 'Statin')"
    )

    parent_drugs: List[str] = Field(default_factory=list, description="Parent drug IDs")
    clinical_trials: List[str] = Field(
        default_factory=list, description="Clinical trial NCT IDs"
    )

    # Body region fields - consolidated to avoid duplication
    body_region: Optional[str] = Field(
        None, description="Primary ontology-aligned body region"
    )
    body_regions: Optional[List[str]] = Field(
        None,
        description="All body regions where this drug is active (aggregated from ontology mapping)",
    )
    secondary_body_regions: List[str] = Field(
        default_factory=list,
        description="Secondary body regions where this drug is active",
    )

    public_summary: Optional[str] = Field(
        None, description="Short public-facing treatment summary"
    )

    # Additional fields from KEGG/PubChem
    kegg_id: Optional[str] = Field(None, description="KEGG Drug ID (e.g., 'D00496')")
    pubchem_cid: Optional[int] = Field(None, description="PubChem Compound ID")
    drugbank_id: Optional[str] = Field(None, description="DrugBank ID")

    class Config:
        populate_by_name = True


class DrugSummary(DrugBase):
    """Lightweight drug model for list views"""

    atc_code: str
    atc_category: str
    indication: Optional[str] = None
    class_name: Optional[str] = Field(None, alias="class")

    class Config:
        populate_by_name = True


class DrugListResponse(BaseModel):
    """Response model for drug list endpoint"""

    total: int
    drugs: List[Drug]


class DrugFilterParams(BaseModel):
    """Query parameters for filtering drugs"""

    category: Optional[str] = Field(None, description="Filter by ATC category (A-V)")
    search: Optional[str] = Field(
        None, description="Search query (name, target, class)"
    )
    phase: Optional[str] = Field(
        None, description="Filter by clinical phase (I/II/III/IV)"
    )
    limit: int = Field(100, ge=1, le=1000, description="Max results to return")
    offset: int = Field(0, ge=0, le=1000, description="Pagination offset")


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = "ok"
    version: str = "1.0.0"
    drugs_count: int = Field(..., description="Total drugs in database")
