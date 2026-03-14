#!/usr/bin/env python3
"""Fetch ATC codes from ChEMBL API with checkpointing support."""

import json
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DRUGS_FILE = PROJECT_ROOT / "src/frontend/data/drugs.json"
OUTPUT_FILE = PROJECT_ROOT / "src/frontend/data/drugs-with-atc.json"
CHECKPOINT_FILE = PROJECT_ROOT / "src/frontend/data/atc_fetch_checkpoint.json"

CHEMBL_SEARCH_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json"
HEADERS = {"Accept": "application/json"}
REQUEST_DELAY = 0.1  # 100ms between requests
CHECKPOINT_INTERVAL = 50  # Save every 50 drugs


def load_checkpoint():
    """Load checkpoint if exists."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return {"processed_ids": [], "results": {}}


def save_checkpoint(checkpoint_data):
    """Save checkpoint data."""
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint_data, f, indent=2)


def fetch_chembl_atc(drug_name: str, drug_id: str) -> dict:
    """Fetch ATC code from ChEMBL by drug name search."""
    result = {
        "drug_id": drug_id,
        "atc_code": None,
        "atc_category": None,
        "chembl_id": None,
    }

    try:
        # Clean drug name
        clean_name = drug_name.split("/")[0].strip()
        clean_name = "".join(c for c in clean_name if c.isalnum() or c in " -_")

        params = {"q": clean_name}
        resp = requests.get(
            CHEMBL_SEARCH_URL, params=params, headers=HEADERS, timeout=20
        )

        if resp.status_code != 200:
            return result

        data = resp.json()
        molecules = data.get("molecules", [])

        if not molecules:
            return result

        # Look for ATC classification
        for mol in molecules:
            atc_list = mol.get("atc_classifications", [])
            if atc_list:
                result["atc_code"] = atc_list[0]
                result["atc_category"] = atc_list[0][0] if atc_list[0] else None
                result["chembl_id"] = mol.get("molecule_chembl_id")
                break

        return result

    except Exception as e:
        print(f"  Error fetching {drug_name}: {e}")
        return result


def main():
    print("=" * 60)
    print("ChEMBL ATC Code Fetcher (with checkpointing)")
    print("=" * 60)

    # Load drugs
    print(f"\nLoading drugs from {DRUGS_FILE}...")
    with open(DRUGS_FILE, "r") as f:
        data = json.load(f)
        # Handle both {"drugs": [...]} and [...] formats
        if isinstance(data, dict) and "drugs" in data:
            drugs = data["drugs"]
        else:
            drugs = data
    print(f"Loaded {len(drugs)} drugs")

    # Load checkpoint
    checkpoint = load_checkpoint()
    processed_ids = set(checkpoint["processed_ids"])
    atc_results = checkpoint["results"]

    print(f"Resuming from checkpoint: {len(processed_ids)} already processed")

    # Filter unprocessed drugs
    drugs_to_process = [d for d in drugs if d.get("id") not in processed_ids]
    print(f"Drugs remaining to process: {len(drugs_to_process)}")

    if not drugs_to_process:
        print("\n✓ All drugs already processed!")
    else:
        # Process with progress bar
        success_count = 0
        fail_count = 0

        with tqdm(total=len(drugs_to_process), desc="Fetching ATC codes") as pbar:
            for drug in drugs_to_process:
                drug_id = drug.get("id")
                drug_name = drug.get("name", "")

                # Fetch ATC
                result = fetch_chembl_atc(drug_name, drug_id)

                # Store result
                atc_results[drug_id] = result
                processed_ids.add(drug_id)

                if result["atc_code"]:
                    success_count += 1
                else:
                    fail_count += 1

                # Update progress
                pbar.update(1)
                pbar.set_postfix({"found": success_count, "missing": fail_count})

                # Checkpoint every CHECKPOINT_INTERVAL drugs
                if len(processed_ids) % CHECKPOINT_INTERVAL == 0:
                    save_checkpoint(
                        {"processed_ids": list(processed_ids), "results": atc_results}
                    )

                # Rate limiting
                time.sleep(REQUEST_DELAY)

        # Final checkpoint
        save_checkpoint({"processed_ids": list(processed_ids), "results": atc_results})
        print(f"\n✓ Processed {len(drugs_to_process)} drugs")
        print(f"  ✓ ATC codes found: {success_count}")
        print(f"  ✗ No ATC found: {fail_count}")

    # Update drugs with ATC data
    print("\nUpdating drugs with ATC codes...")
    updated_drugs = []
    updated_count = 0

    for drug in drugs:
        drug_id = drug.get("id")
        if drug_id in atc_results:
            result = atc_results[drug_id]
            if result["atc_code"]:
                drug["atc_code"] = result["atc_code"]
                drug["atc_category"] = result["atc_category"]
                if result["chembl_id"]:
                    drug["chembl_id"] = result["chembl_id"]
                updated_count += 1
        updated_drugs.append(drug)

    # Save output
    print(f"\nSaving {len(updated_drugs)} drugs to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w") as f:
        json.dump(updated_drugs, f, indent=2)
    print(f"✓ Updated {updated_count} drugs with ATC codes")

    # Show ATC distribution
    print("\n" + "=" * 60)
    print("ATC Category Distribution:")
    print("=" * 60)
    from collections import Counter

    atc_dist = Counter(
        d.get("atc_category", "?") for d in updated_drugs if d.get("atc_category")
    )
    for cat, count in sorted(atc_dist.items()):
        print(f"  {cat}: {count} drugs")

    # Clean up checkpoint on success
    if CHECKPOINT_FILE.exists():
        print(f"\n✓ Cleaning up checkpoint file")
        CHECKPOINT_FILE.unlink()

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
