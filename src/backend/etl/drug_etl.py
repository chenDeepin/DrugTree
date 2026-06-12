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
import asyncio
from collections import defaultdict
from pathlib import Path
import argparse
from typing import Any, Dict, List, Optional

import pandas as pd
import httpx
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CLINICALMOL_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_DRUG_NAME_LOOKUP = CLINICALMOL_PROCESSED_DIR / "kegg_drug_inchikeys.tsv"
DEFAULT_COMPOUND_NAME_LOOKUP = CLINICALMOL_PROCESSED_DIR / "kegg_compound_inchikeys.tsv"



try:
    from .drug_metadata import *
    from .drug_transform_helpers import *
except ImportError:  # pragma: no cover - direct script fallback
    from src.backend.etl.drug_metadata import *
    from src.backend.etl.drug_transform_helpers import *

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
