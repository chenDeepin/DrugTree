#!/usr/bin/env python3
"""
Fetch ATC codes from KEGG API for drugs with KEGG IDs.
Updates drugs.json with real ATC codes.

Usage:
    python fetch_atc_from_kegg.py
"""

import json
import re
import asyncio
from pathlib import Path
import httpx
from tqdm import tqdm

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DRUGS_FILE = PROJECT_ROOT / "data/drugs.json"
OUTPUT_FILE = PROJECT_ROOT / "data/drugs-with-atc.json"

# KEGG API
KEGG_API_URL = "https://rest.kegg.jp/get/dr:{}"

# Rate limiting
REQUEST_DELAY = 0.1  # seconds between requests
BATCH_SIZE = 100


async def fetch_kegg_atc_async(client: httpx.AsyncClient, kegg_id: str) -> tuple:
    """Fetch ATC code from KEGG API for a single drug."""
    try:
        url = KEGG_API_URL.format(kegg_id)
        resp = await client.get(url)

        if resp.status_code != 200:
            return kegg_id, None, None

        text = resp.text

        # Extract ATC code - look for "ATC code: XXXXXXXX"
        atc_match = re.search(r"ATC code:\s*([A-Z]\d{2}[A-Z]{2}\d{2})", text)
        if atc_match:
            atc_code = atc_match.group(1)
            atc_category = atc_code[0]  # First letter is the category
            return kegg_id, atc_code, atc_category

        # Try alternative pattern
        atc_match2 = re.search(r"ATC:\s*([A-Z]\d{2}[A-Z]{2}\d{2})", text)
        if atc_match2:
            atc_code = atc_match2.group(1)
            atc_category = atc_code[0]
            return kegg_id, atc_code, atc_category

        return kegg_id, None, None

    except httpx.HTTPError as e:
        print(f"Error fetching {kegg_id}: {e}")
        return kegg_id, None, None


def fetch_kegg_atc(kegg_id: str) -> tuple:
    """Compatibility wrapper for legacy synchronous callers."""
    async def _run() -> tuple:
        async with httpx.AsyncClient(timeout=10) as client:
            return await fetch_kegg_atc_async(client, kegg_id)

    return asyncio.run(_run())


async def async_main():
    print("=" * 60)
    print("KEGG ATC Code Fetcher for DrugTree")
    print("=" * 60)

    # Load drugs
    print(f"\nLoading drugs from {DRUGS_FILE}...")
    with open(DRUGS_FILE) as f:
        data = json.load(f)

    drugs = data if isinstance(data, list) else data.get("drugs", [])
    print(f"Total drugs: {len(drugs)}")

    # Find drugs with KEGG IDs
    drugs_with_kegg = [(i, d) for i, d in enumerate(drugs) if d.get("kegg_id")]
    print(f"Drugs with KEGG ID: {len(drugs_with_kegg)}")

    # Fetch ATC codes with async rate limiting
    print(f"\nFetching ATC codes from KEGG API...")
    print(f"(Async client, delay={REQUEST_DELAY}s)")

    atc_mapping = {}  # kegg_id -> (atc_code, atc_category)

    async with httpx.AsyncClient(timeout=10) as client:
        with tqdm(total=len(drugs_with_kegg), desc="Fetching") as pbar:
            for idx, drug in drugs_with_kegg:
                kegg_id = drug["kegg_id"]
                kegg_id, atc_code, atc_category = await fetch_kegg_atc_async(client, kegg_id)
                if atc_code:
                    atc_mapping[kegg_id] = (atc_code, atc_category)
                pbar.update(1)
                await asyncio.sleep(REQUEST_DELAY)

    print(f"\nFetched ATC codes for {len(atc_mapping)} drugs")

    # Update drugs with ATC codes
    print("\nUpdating drug records...")
    updated_count = 0
    for idx, drug in drugs_with_kegg:
        kegg_id = drug["kegg_id"]
        if kegg_id in atc_mapping:
            atc_code, atc_category = atc_mapping[kegg_id]
            drugs[idx]["atc_code"] = atc_code
            drugs[idx]["atc_category"] = atc_category
            updated_count += 1

    print(f"Updated {updated_count} drugs with real ATC codes")

    # Count category distribution
    from collections import Counter

    categories = Counter(d.get("atc_category", "?") for d in drugs)

    print("\n=== ATC Category Distribution ===")
    atc_names = {
        "A": "Alimentary & Metabolism",
        "B": "Blood & Blood-forming",
        "C": "Cardiovascular",
        "D": "Dermatological",
        "G": "Genito-urinary",
        "H": "Hormones",
        "J": "Anti-infectives",
        "L": "Antineoplastic",
        "M": "Musculo-skeletal",
        "N": "Nervous System",
        "P": "Antiparasitic",
        "R": "Respiratory",
        "S": "Sensory Organs",
        "V": "Various",
        "?": "Unknown/Placeholder",
    }

    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        name = atc_names.get(cat, "Unknown")
        pct = count / len(drugs) * 100
        print(f"  {cat}: {count:4d} ({pct:5.1f}%) - {name}")

    # Save updated drugs
    print(f"\nSaving to {OUTPUT_FILE}...")

    output_data = {"drugs": drugs} if isinstance(data, dict) else drugs
    output_data["version"] = "3.0.0"
    output_data["total_drugs"] = len(drugs)
    output_data["atc_fetched"] = updated_count

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✅ Done! Output saved to {OUTPUT_FILE}")
    print(f"   Total drugs: {len(drugs)}")
    print(f"   With real ATC: {updated_count}")

    # Also update the main drugs.json
    print(f"\nUpdating main {DRUGS_FILE}...")
    with open(DRUGS_FILE, "w") as f:
        json.dump(output_data, f, indent=2)
    print("✅ Updated main drugs.json")


def main():
    return asyncio.run(async_main())


if __name__ == "__main__":
    main()
