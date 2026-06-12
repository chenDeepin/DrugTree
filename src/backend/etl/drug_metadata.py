"""Drug metadata enrichment helpers for the DrugTree ETL."""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

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

    async def get_drug_info_async(self, kegg_drug_id: str) -> Optional[Dict[str, Any]]:
        """Fetch drug information from KEGG Drug API"""
        if kegg_drug_id in self.cache:
            return self.cache[kegg_drug_id]

        try:
            url = f"{self.BASE_URL}/get/{kegg_drug_id}"
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
            response.raise_for_status()

            # Parse KEGG flat file format
            info = self._parse_kegg_entry(response.text)

            # Cache result
            self.cache[kegg_drug_id] = info

            # Rate limiting
            await asyncio.sleep(0.5)

            return info
        except Exception as e:
            print(f"Error fetching {kegg_drug_id}: {e}")
            return None

    def get_drug_info(self, kegg_drug_id: str) -> Optional[Dict[str, Any]]:
        """Compatibility wrapper for legacy synchronous ETL call sites."""
        return asyncio.run(self.get_drug_info_async(kegg_drug_id))

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
