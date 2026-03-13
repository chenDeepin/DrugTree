#!/usr/bin/env python3
"""
DrugTree ETL Pipeline
Extracts approved drugs from ClinicalMol_hier compound_master_table.tsv,
enriches with ATC codes from KEGG Drug API, and generates JSON for backend.

Usage:
    python drug_etl.py --input /path/to/compound_master_table.tsv --output ../frontend/data/drugs-expanded.json
"""

import pandas as pd
import json
import re
import requests
import time
from typing import Optional, Dict, List
from pathlib import Path
import argparse
from tqdm import tqdm

CLINICALMOL_PROCESSED_DIR = Path(
    "/media/chen/Machine_Disk/Python script/ClinicalMol_hier/data/processed"
)
DEFAULT_DRUG_NAME_LOOKUP = CLINICALMOL_PROCESSED_DIR / "kegg_drug_inchikeys.tsv"
DEFAULT_COMPOUND_NAME_LOOKUP = (
    CLINICALMOL_PROCESSED_DIR / "kegg_compound_inchikeys.tsv"
)


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
    (("thyroid", "adrenal", "endocrine", "metabolic", "diabetes", "adipose"), "endocrine_metabolic"),
    (("kidney", "bladder", "urinary", "renal"), "kidney_urinary"),
    (("breast", "ovary", "uter", "cervix", "prostate", "testis", "reproductive"), "reproductive_breast"),
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

    def get_drug_info(self, kegg_drug_id: str) -> Optional[Dict]:
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

    def _parse_kegg_entry(self, entry_text: str) -> Dict:
        info = {
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

    def _process_field(self, field: str, value: str, info: Dict):
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


def generate_drug_id(name: str) -> str:
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

    def load_table(path: Path, id_key: str, inchikey_key: str):
        if not path or not Path(path).exists():
            return

        table = pd.read_csv(
            path,
            sep="\t",
            usecols=["kegg_id", "inchikey", "name"],
            low_memory=False,
        )

        for row in table.itertuples(index=False):
            name = clean_drug_name(row.name)
            if not name:
                continue

            if pd.notna(row.kegg_id):
                lookups[id_key][str(row.kegg_id).strip()] = name
            if pd.notna(row.inchikey):
                lookups[inchikey_key][str(row.inchikey).strip()] = name

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
        if pd.isna(key) or not key:
            continue
        resolved = local_name_lookups.get(lookup_name, {}).get(str(key).strip())
        if resolved:
            return resolved

    return None


def extract_drug_names(
    row: pd.Series,
    kegg_client: Optional["KEGGDrugClient"] = None,
    local_name_lookups: Optional[Dict[str, Dict[str, str]]] = None,
) -> tuple:
    """Extract primary name and synonyms from drug names

    Priority:
    1. trialbench_drug_names (primary source)
    2. KEGG Drug API (if kegg_client provided and KEGG ID exists)
    3. KEGG Compound API (fallback)
    """
    names_str = str(row.get("trialbench_drug_names", ""))

    if not pd.isna(names_str) and names_str != "nan" and names_str.strip():
        names = dedupe_preserve_order(
            [clean_drug_name(name) for name in split_trialbench_names(names_str)]
        )
        if names:
            primary_name = names[0]
            synonyms = dedupe_preserve_order(names[1:])[:5]
            return primary_name, synonyms

    local_name = get_local_lookup_name(row, local_name_lookups)
    if local_name:
        return local_name, []

    if kegg_client:
        kegg_drug_id = row.get("kegg_drug_id")
        if kegg_drug_id and not pd.isna(kegg_drug_id) and str(kegg_drug_id).strip():
            kegg_data = kegg_client.get_drug_info(str(kegg_drug_id).strip())
            if kegg_data and kegg_data.get("name"):
                return kegg_data["name"], []

        kegg_compound_id = row.get("kegg_compound_id")
        if (
            kegg_compound_id
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


def infer_atc_from_tissue(tissues_str: str) -> tuple:
    if pd.isna(tissues_str) or not tissues_str:
        return None, None
    tissues_lower = str(tissues_str).lower()
    for tissue, atc_cat in TISSUE_TO_ATC.items():
        if tissue in tissues_lower:
            return atc_cat, f"{atc_cat}99XX99"
    return None, None


def infer_atc_from_indication(indication: str) -> tuple:
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


def parse_json_object(value: str) -> Dict:
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


def infer_body_regions(row: pd.Series, atc_category: Optional[str]) -> tuple:
    region_scores: Dict[str, float] = {}

    tissue_scores = parse_json_object(row.get("tissue_scores"))
    for tissue_name, score in tissue_scores.items():
        region_id = infer_region_from_text(tissue_name)
        if region_id:
            region_scores[region_id] = max(region_scores.get(region_id, 0), float(score))

    if not region_scores:
        tissues_union = str(row.get("tissues_union", ""))
        tissues = [part.strip() for part in tissues_union.split(",") if part.strip()]
        for rank, tissue_name in enumerate(tissues[::-1], start=1):
            region_id = infer_region_from_text(tissue_name)
            if region_id:
                region_scores[region_id] = max(region_scores.get(region_id, 0), float(rank))

    if not region_scores:
        region_id = infer_region_from_text(row.get("trialbench_outcomes"))
        if region_id:
            region_scores[region_id] = 1.0

    if not region_scores:
        fallback_regions = ATC_TO_BODY_REGIONS.get(atc_category or "V", ["systemic_multiorgan"])
        return fallback_regions[0], fallback_regions[1:]

    ordered_regions = [
        region_id
        for region_id, _ in sorted(
            region_scores.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return ordered_regions[0], ordered_regions[1:]


def ensure_unique_drug_ids(drugs: List[Dict]) -> List[Dict]:
    counts: Dict[str, int] = {}
    used_ids = set()

    for drug in drugs:
        base_id = drug["id"]
        seen = counts.get(base_id, 0)
        counts[base_id] = seen + 1
        if seen == 0 and base_id not in used_ids:
            used_ids.add(base_id)
            continue

        suffix_parts = [
            (drug.get("kegg_id") or "").lower(),
            (drug.get("inchikey") or "").lower(),
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
) -> Optional[Dict]:
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
    if pd.isna(smiles):
        return None

    # Get InChIKey
    inchikey = row.get("inchikey")
    if pd.isna(inchikey):
        return None

    # Initialize drug object
    drug = {
        "id": drug_id,
        "name": primary_name,
        "smiles": str(smiles),
        "inchikey": str(inchikey),
        "atc_code": None,
        "atc_category": None,
        "molecular_weight": float(row.get("molecular_weight", 0))
        if pd.notna(row.get("molecular_weight"))
        else 0,
        "phase": "IV",  # Approved drugs are Phase IV
        "year_approved": None,
        "generation": 1,
        "indication": None,
        "targets": [],
        "company": None,
        "synonyms": synonyms,
        "class": None,
        "clinical_trials": [],
        "kegg_id": str(row.get("kegg_drug_id")).strip()
        if pd.notna(row.get("kegg_drug_id")) and str(row.get("kegg_drug_id")).strip()
        else None,
    }

    # Try to get ATC code from KEGG Drug
    kegg_drug_id = row.get("kegg_drug_id")
    if pd.notna(kegg_drug_id) and kegg_drug_id and kegg_client:
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

    body_region, secondary_body_regions = infer_body_regions(row, drug["atc_category"])
    drug["body_region"] = body_region
    drug["secondary_body_regions"] = secondary_body_regions

    # Estimate generation
    drug["generation"] = estimate_generation(drug["year_approved"])

    # Extract phase from trialbench_phases
    phases_str = str(row.get("trialbench_phases", ""))
    if pd.notna(phases_str) and phases_str != "nan":
        phases = [p.strip() for p in phases_str.split(",")]
        if "Phase III" in phases or "Phase IV" in phases:
            drug["phase"] = "IV"
        elif "Phase II" in phases:
            drug["phase"] = "II"
        elif "Phase I" in phases:
            drug["phase"] = "I"

    nct_ids = str(row.get("trialbench_nct_ids", ""))
    if pd.notna(nct_ids) and nct_ids != "nan":
        drug["clinical_trials"] = [trial.strip() for trial in nct_ids.split(",") if trial.strip()]

    # Extract indication from trialbench_outcomes
    outcomes_str = str(row.get("trialbench_outcomes", ""))
    if pd.notna(outcomes_str) and outcomes_str != "nan" and not drug["indication"]:
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
