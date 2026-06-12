"""Shared data models and constants for ATC enrichment."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DRUGS_FILE = DATA_DIR / "drugs.json"
DEFAULT_REPORTS_DIR = DATA_DIR / "reports"

KEGG_DBLINK_FIELD_MAP = {
    "PubChem": "pubchem_cid",
    "PubChem Compound": "pubchem_cid",
    "DrugBank": "drugbank_id",
    "ChEMBL": "chembl_id",
}


@dataclass
class ATCResolution:
    atc_code: Optional[str]
    atc_category: Optional[str]
    source: str
    confidence: float
    method: str
    external_ids: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DrugEnrichmentOutcome:
    drug_id: str
    status: str
    source: str
    method: str
    atc_code: Optional[str]
    external_ids_recovered: Dict[str, Any] = field(default_factory=dict)
