#!/usr/bin/env python3
"""
DrugTree ETL Pipeline
Extracts approved drugs from ClinicalMol_hier compound_master_table.tsv,
enriches with ATC codes from KEGG Drug API, and generates JSON for backend.

Usage:
    python drug_etl.py --input /path/to/compound_master_table.tsv --output ../../../data/drugs.json
"""

import json
import re
import time
from collections import defaultdict
from pathlib import Path
import argparse
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CLINICALMOL_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_DRUG_NAME_LOOKUP = CLINICALMOL_PROCESSED_DIR / "kegg_drug_inchikeys.tsv"
DEFAULT_COMPOUND_NAME_LOOKUP = CLINICALMOL_PROCESSED_DIR / "kegg_compound_inchikeys.tsv"


# ATC Category mappings (Level 1)
ATC_CATEGORIES = {
    "A": "Alimentary Tract & Metabolism",
    "B": "Blood & Blood-forming Organs",
    "C": "Cardiovascular System",
    "D": "Dermatologicals",
    "G": "Genito-urinary System & Sex Hormones",
    "H": "Systemic Hormonal Preparations",
    "J": "Anti-infectives for Systemic Use",
    "L": "Antineoplastic & Immunomodulating Agents",
    "M": "Musculo-skeletal System",
    "N": "Nervous System",
    "P": "Antiparasitic Products, Insecticides & Repellents",
    "R": "Respiratory System",
    "S": "Sensory Organs",
    "V": "Various",
}

ATC_TO_BODY_REGIONS = {
    "A": [
        "stomach_upper_gi",
        "intestine_colorectal",
        "liver_biliary_pancreas",
        "endocrine_metabolic",
    ],
    "B": ["blood_immune"],
    "C": ["heart_vascular", "blood_immune"],
    "D": ["skin"],
    "G": ["kidney_urinary", "reproductive_breast"],
    "H": ["endocrine_metabolic"],
    "J": ["lung_respiratory", "systemic_multiorgan"],
    "L": ["blood_immune", "systemic_multiorgan"],
    "M": ["bone_joint_muscle"],
    "N": ["brain_cns"],
    "P": ["intestine_colorectal", "systemic_multiorgan"],
    "R": ["lung_respiratory"],
    "S": ["eye_ear"],
    "V": ["systemic_multiorgan"],
}

BODY_REGION_RULES = [
    (("brain", "cns", "nerve", "spinal", "mening", "pituitary", "head"), "brain_cns"),
    (("eye", "ear", "retina", "cornea"), "eye_ear"),
    (("lung", "bronch", "airway", "respir"), "lung_respiratory"),
    (("heart", "vascular", "arter", "vein", "cardio", "coronary"), "heart_vascular"),
    (("bone marrow", "marrow", "blood", "immune", "lymph", "spleen"), "blood_immune"),
    (("esophagus", "stomach", "duodenum", "upper gi", "gastric"), "stomach_upper_gi"),
    (("intestine", "colon", "rect", "bowel", "colorectal"), "intestine_colorectal"),
    (("liver", "biliary", "gall", "pancrea"), "liver_biliary_pancreas"),
    (
        ("thyroid", "adrenal", "endocrine", "metabolic", "diabetes", "adipose"),
        "endocrine_metabolic",
    ),
    (("kidney", "bladder", "urinary", "renal"), "kidney_urinary"),
    (
        ("breast", "ovary", "uter", "cervix", "prostate", "testis", "reproductive"),
        "reproductive_breast",
    ),
    (("bone", "joint", "muscle", "skeletal"), "bone_joint_muscle"),
    (("skin", "derm", "hair", "nail"), "skin"),
]


class KEGGDrugClient:
    """Client for fetching ATC codes from KEGG Drug API"""

    BASE_URL = "https://rest.kegg.jp"

    def __init__(self, cache_file: Optional[str] = None):
        self.cache = {}
        self.cache_file = cache_file
        if cache_file and Path(cache_file).exists():
            with open(cache_file, "r") as f:
                self.cache = json.load(f)

    def get_drug_info(self, kegg_drug_id: str) -> Optional[Dict[str, Any]]:
        """Fetch drug information from KEGG Drug API"""
        if kegg_drug_id in self.cache:
            return self.cache[kegg_drug_id]

        try:
            url = f"{self.BASE_URL}/get/{kegg_drug_id}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Parse KEGG flat file format
            info = self._parse_kegg_entry(response.text)

            # Cache result
            self.cache[kegg_drug_id] = info

            # Rate limiting
            time.sleep(0.5)

            return info
        except Exception as e:
            print(f"Error fetching {kegg_drug_id}: {e}")
            return None

    def _parse_kegg_entry(self, entry_text: str) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "atc_codes": [],
            "atc_category": None,
            "indication": None,
            "targets": [],
            "company": None,
            "class": None,
            "year_approved": None,
            "name": None,
        }

        current_field = None
        current_value = []

        for line in entry_text.split("\n"):
            if not line.strip():
                continue

            # Check if this is a new field
            if len(line) > 12 and line[0] != " ":
                # Save previous field
                if current_field and current_value:
                    self._process_field(current_field, "\n".join(current_value), info)

                # Start new field
                current_field = line[:12].strip()
                current_value = [line[12:].strip()]
            elif current_field:
                # Continuation of previous field
                current_value.append(line.strip())

        # Process last field
        if current_field and current_value:
            self._process_field(current_field, "\n".join(current_value), info)

        # Set ATC category from first ATC code
        if info["atc_codes"]:
            info["atc_category"] = info["atc_codes"][0][0]  # First letter

        return info

    def _process_field(self, field: str, value: str, info: Dict[str, Any]) -> None:
        if field == "NAME":
            info["name"] = value.split("\n")[0].split(";")[0].strip()
        elif field == "ATC":
            atc_codes = re.findall(r"[A-Z]\d{2}[A-Z]{2}\d{2}", value)
            info["atc_codes"].extend(atc_codes)
        elif field == "REMARK":
            if "Adopted" in value or "approved" in value.lower():
                years = re.findall(r"\b(19|20)\d{2}\b", value)
                if years and not info["year_approved"]:
                    info["year_approved"] = int(years[-1])
        elif field == "COMMENT":
            if not info["indication"]:
                info["indication"] = value.split("\n")[0][:200]
        elif field == "DBLINKS":
            pass

    def save_cache(self):
        """Save cache to file"""
        if self.cache_file:
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f, indent=2)


def generate_drug_id(name: str) -> Optional[str]:
    """Generate a URL-friendly drug ID from name"""
    # Take first name if multiple
    if pd.isna(name):
        return None
    name = str(name).split(",")[0].strip()
    # Convert to lowercase, replace spaces with hyphens
    drug_id = re.sub(r"[^a-zA-Z0-9\s-]", "", name.lower())
    drug_id = re.sub(r"[\s]+", "-", drug_id)
    return drug_id.strip("-")


def dedupe_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    deduped = []
    for value in values:
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def normalize_kegg_name(name: str) -> str:
    value = re.sub(r"\s+", " ", str(name or "")).strip(" ;")
    value = re.sub(r"\s*\((?:USAN|INN|JAN|USP|JP\d*|TN)\)$", "", value)
    return value.strip()


def parse_kegg_metadata(raw_text: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "primary_name": None,
        "synonyms": [],
        "targets": [],
        "disease_ids": [],
        "atc_codes": [],
        "class_name": None,
        "companies": [],
        "year_approved": None,
    }

    if not raw_text:
        return metadata

    sections: Dict[str, List[str]] = defaultdict(list)
    current_field: Optional[str] = None

    known_fields = {
        "ENTRY",
        "NAME",
        "PRODUCT",
        "FORMULA",
        "EXACT_MASS",
        "MOL_WEIGHT",
        "CLASS",
        "REMARK",
        "EFFICACY",
        "COMMENT",
        "TARGET",
        "DISEASE",
        "BRITE",
        "DBLINKS",
        "PATHWAY",
        "METABOLISM",
        "INTERACTION",
        "STR_MAP",
        "SEQUENCE",
    }

    for raw_line in str(raw_text).splitlines():
        if not raw_line.strip():
            continue
        candidate_field = raw_line[:12].strip()
        if candidate_field in known_fields:
            current_field = candidate_field
            sections[current_field].append(raw_line[12:].strip())
            continue
        if current_field:
            sections[current_field].append(raw_line.strip())

    names = [normalize_kegg_name(value) for value in sections.get("NAME", [])]
    names = [value for value in names if value]
    if names:
        metadata["primary_name"] = names[0]
        metadata["synonyms"] = dedupe_preserve_order(sections.get("NAME", []))

    target_values: List[str] = []
    for value in sections.get("TARGET", []):
        target_name = value.split("[")[0].strip()
        if target_name:
            target_values.append(target_name)
    metadata["targets"] = dedupe_preserve_order(target_values)

    disease_ids = []
    for value in sections.get("DISEASE", []):
        disease_ids.extend(re.findall(r"\[DS:([^\]]+)\]", value))
    metadata["disease_ids"] = dedupe_preserve_order(disease_ids)

    atc_codes = []
    search_space = sections.get("REMARK", []) + sections.get("BRITE", [])
    for value in search_space:
        atc_codes.extend(re.findall(r"\b[A-Z]\d{2}[A-Z]{2}\d{2}\b", value))
    metadata["atc_codes"] = dedupe_preserve_order(atc_codes)

    class_candidates = []
    for value in sections.get("CLASS", []):
        cleaned = re.sub(r"^[A-Z]{2}\d+\s+", "", value).strip()
        if cleaned:
            class_candidates.append(cleaned)
    if class_candidates:
        metadata["class_name"] = class_candidates[-1]

    companies = []
    for value in sections.get("PRODUCT", []):
        match = re.search(r"\(([^()]+)\)\s*$", value)
        if match:
            companies.append(match.group(1).strip())
    metadata["companies"] = dedupe_preserve_order(companies)

    return metadata


def normalize_chembl_metadata(
    molecule_payload: Optional[Dict[str, Any]],
    mechanisms_payload: Optional[List[Dict[str, Any]]],
    indications_payload: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    synonyms = []
    for synonym in (molecule_payload or {}).get("molecule_synonyms", []):
        value = synonym.get("molecule_synonym") if isinstance(synonym, dict) else None
        if value:
            synonyms.append(value)

    targets = []
    class_name = None
    for mechanism in mechanisms_payload or []:
        target_name = mechanism.get("target_pref_name")
        if target_name:
            targets.append(target_name)
        if not class_name and mechanism.get("mechanism_of_action"):
            class_name = mechanism["mechanism_of_action"]

    disease_ids = []
    for indication in indications_payload or []:
        disease_id = indication.get("mesh_id") or indication.get("efo_id")
        if disease_id:
            disease_ids.append(disease_id)

    return {
        "targets": dedupe_preserve_order(targets),
        "synonyms": dedupe_preserve_order(synonyms),
        "class_name": class_name,
        "disease_ids": dedupe_preserve_order(disease_ids),
    }


def normalize_fda_metadata(
    approvals_payload: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    year_approved = None
    company = None

    for approval in approvals_payload or []:
        approval_date = str(approval.get("approval_date") or "")
        if approval_date and approval_date[:4].isdigit():
            candidate = int(approval_date[:4])
            year_approved = (
                candidate if year_approved is None else min(year_approved, candidate)
            )
        sponsor = approval.get("sponsor")
        if sponsor and not company:
            company = sponsor.strip()

    return {"year_approved": year_approved, "company": company}


def is_placeholder_atc_code(atc_code: Optional[str]) -> bool:
    return bool(atc_code and re.fullmatch(r"[A-Z]99XX99", atc_code))


def merge_drug_metadata(
    drug: Dict[str, Any],
    kegg_metadata: Optional[Dict[str, Any]] = None,
    chembl_metadata: Optional[Dict[str, Any]] = None,
    fda_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged = dict(drug)
    kegg_metadata = kegg_metadata or {}
    chembl_metadata = chembl_metadata or {}
    fda_metadata = fda_metadata or {}

    merged["targets"] = dedupe_preserve_order(
        (merged.get("targets") or [])
        + (kegg_metadata.get("targets") or [])
        + (chembl_metadata.get("targets") or [])
    )
    merged["synonyms"] = dedupe_preserve_order(
        (merged.get("synonyms") or [])
        + (kegg_metadata.get("synonyms") or [])
        + (chembl_metadata.get("synonyms") or [])
    )

    if not merged.get("class"):
        merged["class"] = kegg_metadata.get("class_name") or chembl_metadata.get(
            "class_name"
        )

    if not merged.get("company"):
        merged["company"] = fda_metadata.get("company")
    if not merged.get("company"):
        companies = kegg_metadata.get("companies") or []
        merged["company"] = companies[0] if companies else None

    if not merged.get("year_approved"):
        merged["year_approved"] = fda_metadata.get(
            "year_approved"
        ) or kegg_metadata.get("year_approved")

    existing_atc = merged.get("atc_code")
    kegg_atc_codes = kegg_metadata.get("atc_codes") or []
    if (not existing_atc or is_placeholder_atc_code(existing_atc)) and kegg_atc_codes:
        merged["atc_code"] = kegg_atc_codes[0]
        merged["atc_category"] = kegg_atc_codes[0][0]

    return merged


def load_kegg_metadata_by_id(kegg_dump_path: Path) -> Dict[str, Dict[str, Any]]:
    if not kegg_dump_path.exists():
        return {}

    table = pd.read_csv(kegg_dump_path, sep="\t", low_memory=False)[
        ["kegg_id", "raw_text"]
    ]
    metadata_by_id: Dict[str, Dict[str, Any]] = {}
    for _, row in table.iterrows():
        raw_kegg_id = row.get("kegg_id")
        kegg_id = (
            str(raw_kegg_id).strip()
            if raw_kegg_id is not None and pd.notna(raw_kegg_id)
            else ""
        )
        if not kegg_id:
            continue
        metadata_by_id[kegg_id] = parse_kegg_metadata(str(row.get("raw_text") or ""))
    return metadata_by_id


def enrich_drugs_with_kegg_metadata(
    drugs: List[Dict[str, Any]], metadata_by_kegg_id: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    enriched = []
    for drug in drugs:
        kegg_id_value = drug.get("kegg_id")
        kegg_metadata = {}
        if isinstance(kegg_id_value, str):
            kegg_metadata = metadata_by_kegg_id.get(kegg_id_value, {})
        enriched.append(merge_drug_metadata(drug, kegg_metadata=kegg_metadata))
    return enriched


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


def transform_drug(
    row: pd.Series,
    kegg_client: Optional[KEGGDrugClient],
    local_name_lookups: Optional[Dict[str, Dict[str, str]]] = None,
) -> Optional[Dict[str, Any]]:
    """Transform a compound row to DrugTree drug format"""

    # Extract primary name and synonyms (with KEGG fallback)
    primary_name, synonyms = extract_drug_names(
        row, kegg_client, local_name_lookups=local_name_lookups
    )
    if not primary_name:
        return None

    drug_id = generate_drug_id(primary_name)
    if not drug_id:
        return None

    # Get SMILES
    smiles = row.get("canonical_smiles")
    if smiles is None or pd.isna(smiles):
        return None

    # Get InChIKey
    inchikey = row.get("inchikey")
    if inchikey is None or pd.isna(inchikey):
        return None

    # Initialize drug object
    molecular_weight_value = row.get("molecular_weight")
    molecular_weight = (
        float(molecular_weight_value)
        if molecular_weight_value is not None and not pd.isna(molecular_weight_value)
        else 0.0
    )

    kegg_id_value = row.get("kegg_drug_id")
    kegg_id = (
        str(kegg_id_value).strip()
        if kegg_id_value is not None
        and pd.notna(kegg_id_value)
        and str(kegg_id_value).strip()
        else None
    )

    drug: Dict[str, Any] = {
        "id": drug_id,
        "name": primary_name,
        "smiles": str(smiles),
        "inchikey": str(inchikey),
        "atc_code": None,
        "atc_category": None,
        "molecular_weight": molecular_weight,
        "phase": "IV",  # Approved drugs are Phase IV
        "year_approved": None,
        "generation": 1,
        "indication": None,
        "targets": [],
        "company": None,
        "synonyms": synonyms,
        "class": None,
        "clinical_trials": [],
        "kegg_id": kegg_id,
    }

    # Try to get ATC code from KEGG Drug
    kegg_drug_id = row.get("kegg_drug_id")
    if (
        kegg_drug_id is not None
        and pd.notna(kegg_drug_id)
        and str(kegg_drug_id).strip()
        and kegg_client is not None
    ):
        kegg_info = kegg_client.get_drug_info(str(kegg_drug_id))
        if kegg_info:
            drug["atc_codes"] = kegg_info.get("atc_codes", [])
            if drug["atc_codes"]:
                drug["atc_code"] = drug["atc_codes"][0]
                drug["atc_category"] = drug["atc_code"][0]

            if kegg_info.get("indication"):
                drug["indication"] = kegg_info["indication"]

            if kegg_info.get("year_approved"):
                drug["year_approved"] = kegg_info["year_approved"]

    if not drug["atc_code"]:
        indication = str(row.get("trialbench_outcomes", ""))
        category, atc_code = infer_atc_from_indication(indication)
        if category:
            drug["atc_code"] = atc_code
            drug["atc_category"] = category

    if not drug["atc_code"]:
        tissues = str(row.get("tissues_union", ""))
        category, atc_code = infer_atc_from_tissue(tissues)
        if category:
            drug["atc_code"] = atc_code
            drug["atc_category"] = category

    if not drug["atc_category"]:
        drug["atc_code"] = "V99XX99"
        drug["atc_category"] = "V"

    body_region, secondary_body_regions = infer_body_regions(
        row, str(drug["atc_category"])
    )
    drug["body_region"] = body_region
    drug["secondary_body_regions"] = secondary_body_regions

    # Estimate generation
    drug["generation"] = estimate_generation(
        drug["year_approved"] if isinstance(drug["year_approved"], int) else None
    )

    # Extract phase from trialbench_phases
    phases_str = str(row.get("trialbench_phases") or "")
    if phases_str and phases_str != "nan":
        phases = [p.strip() for p in phases_str.split(",")]
        if "Phase III" in phases or "Phase IV" in phases:
            drug["phase"] = "IV"
        elif "Phase II" in phases:
            drug["phase"] = "II"
        elif "Phase I" in phases:
            drug["phase"] = "I"

    nct_ids = str(row.get("trialbench_nct_ids") or "")
    if nct_ids and nct_ids != "nan":
        drug["clinical_trials"] = [
            trial.strip() for trial in nct_ids.split(",") if trial.strip()
        ]

    # Extract indication from trialbench_outcomes
    outcomes_str = str(row.get("trialbench_outcomes") or "")
    if outcomes_str and outcomes_str != "nan" and not drug["indication"]:
        # Take first outcome as indication
        outcomes = [o.strip() for o in outcomes_str.split(",")]
        if outcomes:
            drug["indication"] = outcomes[0][:200]  # Limit length

    return drug


def main():
    parser = argparse.ArgumentParser(description="DrugTree ETL Pipeline")
    parser.add_argument(
        "--input", "-i", required=True, help="Input compound_master_table.tsv file"
    )
    parser.add_argument("--output", "-o", required=True, help="Output JSON file")
    parser.add_argument(
        "--limit", "-l", type=int, help="Limit number of drugs (for testing)"
    )
    parser.add_argument(
        "--no-kegg",
        action="store_true",
        help="Skip KEGG API calls (faster, less accurate)",
    )
    parser.add_argument(
        "--cache", default="kegg_cache.json", help="KEGG API cache file"
    )
    parser.add_argument(
        "--drug-name-lookup",
        default=str(DEFAULT_DRUG_NAME_LOOKUP),
        help="Local KEGG drug TSV with names",
    )
    parser.add_argument(
        "--compound-name-lookup",
        default=str(DEFAULT_COMPOUND_NAME_LOOKUP),
        help="Local KEGG compound TSV with names",
    )

    args = parser.parse_args()

    print(f"Loading compound master table from {args.input}...")
    df = pd.read_csv(args.input, sep="\t")

    # Filter to approved drugs only
    print(f"Total compounds: {len(df)}")
    approved_df = df[df["approval_status"] == "approved"]
    print(f"Approved drugs: {len(approved_df)}")

    if args.limit:
        approved_df = approved_df.head(args.limit)
        print(f"Processing first {args.limit} drugs")

    # Initialize KEGG client
    kegg_client = None if args.no_kegg else KEGGDrugClient(cache_file=args.cache)
    local_name_lookups = load_local_name_lookups(
        Path(args.drug_name_lookup), Path(args.compound_name_lookup)
    )

    # Transform drugs
    drugs = []
    skipped = 0

    print("Transforming drugs...")
    for idx, row in tqdm(approved_df.iterrows(), total=len(approved_df)):
        try:
            drug = transform_drug(
                row, kegg_client, local_name_lookups=local_name_lookups
            )
            if drug:
                drugs.append(drug)
            else:
                skipped += 1
        except Exception as e:
            print(f"\nError processing row {idx}: {e}")
            skipped += 1

    print(f"\nTransformed {len(drugs)} drugs, skipped {skipped}")
    drugs = ensure_unique_drug_ids(drugs)
    drugs.sort(key=lambda item: item["name"].lower())

    # Save KEGG cache
    if kegg_client:
        kegg_client.save_cache()

    # Count by ATC category
    print("\nDrugs by ATC category:")
    atc_counts = {}
    for drug in drugs:
        cat = drug["atc_category"]
        atc_counts[cat] = atc_counts.get(cat, 0) + 1

    for cat in sorted(atc_counts.keys()):
        print(
            f"  {cat} ({ATC_CATEGORIES.get(cat, 'Unknown'):40s}): {atc_counts[cat]:4d}"
        )

    # Save to JSON
    output_data = {
        "drugs": drugs,
        "metadata": {
            "total_drugs": len(drugs),
            "atc_categories": atc_counts,
            "source": "ClinicalMol_hier compound_master_table.tsv",
            "kegg_enriched": not args.no_kegg,
            "local_name_enriched": True,
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(drugs)} drugs to {output_path}")
    print(f"Cache saved to {args.cache}")


if __name__ == "__main__":
    main()
