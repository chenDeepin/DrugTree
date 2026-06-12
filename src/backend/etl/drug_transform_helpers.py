"""Drug normalization and classification helpers for the DrugTree ETL."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CLINICALMOL_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_DRUG_NAME_LOOKUP = CLINICALMOL_PROCESSED_DIR / "kegg_drug_inchikeys.tsv"
DEFAULT_COMPOUND_NAME_LOOKUP = CLINICALMOL_PROCESSED_DIR / "kegg_compound_inchikeys.tsv"

try:
    from .drug_metadata import ATC_CATEGORIES, BODY_REGION_RULES, dedupe_preserve_order
except ImportError:  # pragma: no cover - direct script fallback
    from src.backend.etl.drug_metadata import ATC_CATEGORIES, BODY_REGION_RULES, dedupe_preserve_order

def split_trialbench_names(names_str: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []

    for index, character in enumerate(str(names_str)):
        if character == ",":
            previous = names_str[index - 1] if index > 0 else ""
            following = names_str[index + 1] if index + 1 < len(names_str) else ""
            if previous.isdigit() and following.isdigit():
                current.append(character)
                continue

            candidate = "".join(current).strip()
            if candidate:
                parts.append(candidate)
            current = []
            continue

        current.append(character)

    candidate = "".join(current).strip()
    if candidate:
        parts.append(candidate)

    return parts


def clean_drug_name(raw_name: str) -> Optional[str]:
    def clean_simple_name(candidate: str) -> Optional[str]:
        name = re.sub(r"\s+", " ", str(candidate)).strip(" ,;")
        if not name:
            return None

        lower_name = name.lower()
        blocked_patterns = [
            "placebo",
            "medical care",
            "comparator",
            "active symptom control",
            "treatment a",
            "treatment b",
            "sham comparator",
        ]
        if any(pattern in lower_name for pattern in blocked_patterns):
            return None

        if re.fullmatch(r"\d+(?:\.\d+)?", name):
            return None

        return name

    if pd.isna(raw_name):
        return None

    name = re.sub(r"\s+", " ", str(raw_name)).strip(" ,;")
    if not name:
        return None

    if "/" in name:
        parts = [part.strip() for part in name.split("/") if part.strip()]
        cleaned_parts = [clean_simple_name(part) for part in parts]
        retained_parts = [part for part in cleaned_parts if part]
        if retained_parts and len(retained_parts) < len(parts):
            return "/".join(retained_parts)

    lower_name = name.lower()
    blocked_patterns = [
        "placebo",
        "medical care",
        "comparator",
        "active symptom control",
        "treatment a",
        "treatment b",
        "sham comparator",
    ]
    if any(pattern in lower_name for pattern in blocked_patterns):
        return None

    if re.fullmatch(r"\d+(?:\.\d+)?", name):
        return None

    return name


def load_local_name_lookups(
    drug_lookup_path: Path = DEFAULT_DRUG_NAME_LOOKUP,
    compound_lookup_path: Path = DEFAULT_COMPOUND_NAME_LOOKUP,
) -> Dict[str, Dict[str, str]]:
    lookups = {
        "drug_by_id": {},
        "drug_by_inchikey": {},
        "compound_by_id": {},
        "compound_by_inchikey": {},
    }

    def load_table(path: Path, id_key: str, inchikey_key: str) -> None:
        if not Path(path).exists():
            return

        table = pd.read_csv(path, sep="\t", low_memory=False)[
            ["kegg_id", "inchikey", "name"]
        ]

        for _, row in table.iterrows():
            name = clean_drug_name(str(row.get("name") or ""))
            if not name:
                continue

            kegg_id = row.get("kegg_id")
            if kegg_id is not None and pd.notna(kegg_id):
                lookups[id_key][str(kegg_id).strip()] = name
            inchikey = row.get("inchikey")
            if inchikey is not None and pd.notna(inchikey):
                lookups[inchikey_key][str(inchikey).strip()] = name

    load_table(Path(drug_lookup_path), "drug_by_id", "drug_by_inchikey")
    load_table(Path(compound_lookup_path), "compound_by_id", "compound_by_inchikey")

    return lookups


def get_local_lookup_name(
    row: pd.Series, local_name_lookups: Optional[Dict[str, Dict[str, str]]]
) -> Optional[str]:
    if not local_name_lookups:
        return None

    lookup_candidates = [
        ("drug_by_id", row.get("kegg_drug_id")),
        ("compound_by_id", row.get("kegg_compound_id")),
        ("drug_by_inchikey", row.get("inchikey")),
        ("compound_by_inchikey", row.get("inchikey")),
    ]

    for lookup_name, key in lookup_candidates:
        if key is None or pd.isna(key) or str(key).strip() == "":
            continue
        resolved = local_name_lookups.get(lookup_name, {}).get(str(key).strip())
        if resolved:
            return resolved

    return None


def extract_drug_names(
    row: pd.Series,
    kegg_client: Optional["KEGGDrugClient"] = None,
    local_name_lookups: Optional[Dict[str, Dict[str, str]]] = None,
) -> tuple[Optional[str], List[str]]:
    """Extract primary name and synonyms from drug names

    Priority:
    1. trialbench_drug_names (primary source)
    2. KEGG Drug API (if kegg_client provided and KEGG ID exists)
    3. KEGG Compound API (fallback)
    """
    names_str = str(row.get("trialbench_drug_names", ""))

    if not pd.isna(names_str) and names_str != "nan" and names_str.strip():
        names = dedupe_preserve_order(
            [
                cleaned
                for cleaned in (
                    clean_drug_name(name) for name in split_trialbench_names(names_str)
                )
                if cleaned
            ]
        )
        if names:
            primary_name = names[0]
            synonyms = dedupe_preserve_order(names[1:])[:5]
            return primary_name, synonyms

    local_name = get_local_lookup_name(row, local_name_lookups)
    if local_name:
        return local_name, []

    if kegg_client is not None:
        kegg_drug_id = row.get("kegg_drug_id")
        if (
            kegg_drug_id is not None
            and not pd.isna(kegg_drug_id)
            and str(kegg_drug_id).strip()
        ):
            kegg_data = kegg_client.get_drug_info(str(kegg_drug_id).strip())
            if kegg_data and kegg_data.get("name"):
                return kegg_data["name"], []

        kegg_compound_id = row.get("kegg_compound_id")
        if (
            kegg_compound_id is not None
            and not pd.isna(kegg_compound_id)
            and str(kegg_compound_id).strip()
        ):
            compound_id = str(kegg_compound_id).strip()
            kegg_data = kegg_client.get_drug_info(compound_id)
            if kegg_data and kegg_data.get("name"):
                return kegg_data["name"], []

    return None, []


def estimate_generation(year_approved: Optional[int]) -> int:
    """Estimate drug generation based on approval year"""
    if not year_approved:
        return 1

    if year_approved < 1970:
        return 1
    elif year_approved < 1990:
        return 2
    elif year_approved < 2010:
        return 3
    else:
        return 4


TISSUE_TO_ATC = {
    "liver": "A",
    "stomach": "A",
    "intestine": "A",
    "pancreas": "A",
    "blood": "B",
    "bone_marrow": "B",
    "heart": "C",
    "artery": "C",
    "vein": "C",
    "skin": "D",
    "kidney": "G",
    "bladder": "G",
    "prostate": "G",
    "ovary": "G",
    "testis": "G",
    "thyroid": "H",
    "adrenal": "H",
    "pituitary": "H",
    "infection": "J",
    "immune": "L",
    "muscle": "M",
    "bone": "M",
    "joint": "M",
    "brain": "N",
    "nerve": "N",
    "spinal_cord": "N",
    "lung": "R",
    "bronchus": "R",
    "eye": "S",
    "ear": "S",
    "head": "N",
    "hormone": "H",
    "parasite": "P",
}


def infer_atc_from_tissue(tissues_str: str) -> tuple[Optional[str], Optional[str]]:
    if pd.isna(tissues_str) or not tissues_str:
        return None, None
    tissues_lower = str(tissues_str).lower()
    for tissue, atc_cat in TISSUE_TO_ATC.items():
        if tissue in tissues_lower:
            return atc_cat, f"{atc_cat}99XX99"
    return None, None


def infer_atc_from_indication(indication: str) -> tuple[Optional[str], Optional[str]]:
    if pd.isna(indication):
        return None, None
    indication_lower = str(indication).lower()
    keywords = {
        "A": ["diabetes", "obesity", "acid", "gastric", "ulcer", "bowel"],
        "B": ["coagulation", "clotting", "anemia", "thromb"],
        "C": ["cardiac", "hypertension", "blood pressure", "cholesterol", "lipid"],
        "D": ["dermat", "acne", "eczema", "psoriasis"],
        "G": ["urolog", "gynec", "erectile"],
        "H": ["thyroid", "corticosteroid", "insulin"],
        "J": ["antibiot", "antiviral", "antifungal", "bacteria"],
        "L": ["cancer", "tumor", "oncolog", "chemotherap", "leukemia"],
        "M": ["muscle", "bone", "joint", "arthritis", "osteopor"],
        "N": ["depress", "anxiety", "epilepsy", "parkinson", "alzheimer"],
        "P": ["malaria", "anthelmint"],
        "R": ["asthma", "cough", "bronch"],
        "S": ["ophthalm", "otic"],
        "V": ["vitamin", "nutrient", "contrast"],
    }
    for category, kw_list in keywords.items():
        for kw in kw_list:
            if kw in indication_lower:
                return category, f"{category}99XX99"
    return None, None


def parse_json_object(value: Any) -> Dict[str, Any]:
    if pd.isna(value) or not value:
        return {}

    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return {}


def infer_region_from_text(text: str) -> Optional[str]:
    lowered = str(text or "").lower()

    def matches(keyword: str) -> bool:
        if " " in keyword:
            return keyword in lowered
        return re.search(rf"\b{re.escape(keyword)}\b", lowered) is not None

    for keywords, region_id in BODY_REGION_RULES:
        if any(matches(keyword) for keyword in keywords):
            return region_id
    return None


def infer_body_regions(
    row: pd.Series, atc_category: Optional[str]
) -> tuple[str, List[str]]:
    region_scores: Dict[str, float] = {}

    tissue_scores = parse_json_object(row.get("tissue_scores"))
    for tissue_name, score in tissue_scores.items():
        region_id = infer_region_from_text(tissue_name)
        if region_id:
            region_scores[region_id] = max(
                region_scores.get(region_id, 0), float(score)
            )

    if not region_scores:
        tissues_union = str(row.get("tissues_union", ""))
        tissues = [part.strip() for part in tissues_union.split(",") if part.strip()]
        for rank, tissue_name in enumerate(tissues[::-1], start=1):
            region_id = infer_region_from_text(tissue_name)
            if region_id:
                region_scores[region_id] = max(
                    region_scores.get(region_id, 0), float(rank)
                )

    if not region_scores:
        region_id = infer_region_from_text(str(row.get("trialbench_outcomes") or ""))
        if region_id:
            region_scores[region_id] = 1.0

    if not region_scores:
        fallback_regions = ATC_TO_BODY_REGIONS.get(
            atc_category or "V", ["systemic_multiorgan"]
        )
        return fallback_regions[0], fallback_regions[1:]

    ordered_regions = [
        region_id
        for region_id, _ in sorted(
            region_scores.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return ordered_regions[0], ordered_regions[1:]


def ensure_unique_drug_ids(drugs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    used_ids: set[str] = set()

    for drug in drugs:
        base_id = drug["id"]
        seen = counts.get(base_id, 0)
        counts[base_id] = seen + 1
        if seen == 0 and base_id not in used_ids:
            used_ids.add(base_id)
            continue

        suffix_parts = [
            str(drug.get("kegg_id") or "").lower(),
            str(drug.get("inchikey") or "").lower(),
            str(seen + 1),
        ]
        suffix_parts = [part for part in suffix_parts if part]

        candidate_id = base_id
        for suffix in suffix_parts:
            candidate_id = f"{candidate_id}-{suffix}"
            if candidate_id not in used_ids:
                break

        while candidate_id in used_ids:
            candidate_id = f"{candidate_id}-{counts[base_id]}"

        drug["id"] = candidate_id
        used_ids.add(candidate_id)

    return drugs
