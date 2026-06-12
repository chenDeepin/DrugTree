#!/usr/bin/env python3
"""
ATC Lookup via KEGG API for drugs with KEGG IDs but placeholder ATC codes.

This script queries the KEGG REST API for ATC codes for drugs
that have KEGG IDs but placeholder ATC codes (V99XX99 or 99XX99).

Usage:
    python -m src.backend.etl.atc_kegg_api_lookup [--batch-size N] [--dry-run]

Features:
    - Queries KEGG REST API for each drug
    - Extracts ATC code from BRITE section
    - Rate limiting to respect KEGG API (max 10 requests/second)
    - Progress tracking
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional
import httpx

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DRUGS_FILE = DATA_DIR / "drugs.json"
OUTPUT_FILE = DATA_DIR / "atc_from_kegg_api.json"


def load_drugs() -> List[Dict]:
    """Load drugs from JSON file."""
    with open(DRUGS_FILE, "r") as f:
        data = json.load(f)
        return data.get("drugs", [])


def filter_placeholder_drugs(drugs: List[Dict]) -> List[Dict]:
    """Filter drugs with placeholder ATC codes and KEGG IDs."""
    return [
        d
        for d in drugs
        if (
            d.get("atc_code", "").startswith(("V99", "99XX"))
            and d.get("kegg_id")
            and d.get("kegg_id").startswith("D")
        )
    ]


async def extract_atc_from_kegg_async(client: httpx.AsyncClient, kegg_id: str) -> Optional[str]:
    """Query KEGG API and extract ATC code from response."""
    url = f"https://rest.kegg.jp/get/{kegg_id}"

    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None

        text = resp.text

        # Look for ATC code in BRITE section
        # Format: "ATC code: A01AD05 B01AC06 N02BA01"
        for line in text.split("\n"):
            if "ATC code:" in line.lower():
                # Extract the ATC code (format varies)
                parts = line.split()
                for part in parts:
                    # ATC code format: 1 letter + 2 digits + 2 letters + 2 digits
                    if len(part) == 7 and part[0].isalpha() and part[1:3].isdigit():
                        if part[3:5].isalpha() and part[5:7].isdigit():
                            return part

        return None

    except httpx.HTTPError as e:
        print(f"Error querying {kegg_id}: {e}")
        return None


def extract_atc_from_kegg(kegg_id: str) -> Optional[str]:
    """Compatibility wrapper for legacy synchronous callers."""
    async def _run() -> Optional[str]:
        async with httpx.AsyncClient(timeout=10) as client:
            return await extract_atc_from_kegg_async(client, kegg_id)

    return asyncio.run(_run())


async def async_main():
    parser = argparse.ArgumentParser(description="KEGG API ATC Lookup")
    parser.add_argument(
        "--batch-size", type=int, default=50, help="Drugs to process per batch"
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't save results")
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of drugs to process"
    )
    args = parser.parse_args()

    print("Loading drugs...")
    all_drugs = load_drugs()
    print(f"Total drugs: {len(all_drugs)}")

    placeholder_drugs = filter_placeholder_drugs(all_drugs)
    print(f"Drugs with placeholder ATC and KEGG ID: {len(placeholder_drugs)}")

    if args.limit:
        placeholder_drugs = placeholder_drugs[: args.limit]
        print(f"Limited to: {len(placeholder_drugs)}")

    # Process drugs
    results = {
        "total": len(placeholder_drugs),
        "found": 0,
        "not_found": 1,
        "matches": [],
    }

    print(f"\nQuerying KEGG API...")

    async with httpx.AsyncClient(timeout=10) as client:
        for i, drug in enumerate(placeholder_drugs):
            kegg_id = drug.get("kegg_id")
            name = drug.get("name", "")

            # Progress
            if (i + 1) % 50 == 0:
                print(f"  Progress: {i + 1}/{len(placeholder_drugs)}")

            # Query KEGG
            atc = await extract_atc_from_kegg_async(client, kegg_id)

            if atc:
                results["found"] += 1
                results["matches"].append(
                    {
                        "drug_id": drug.get("id"),
                        "name": name,
                        "kegg_id": kegg_id,
                        "old_atc": drug.get("atc_code"),
                        "new_atc": atc,
                        "atc_category": atc[1] if atc else None,
                        "source": "kegg_api",
                        "confidence": 1.0,
                    }
                )
                print(f"    ✓ {name}: {drug.get('atc_code')} -> {atc}")
            else:
                results["not_found"] += 1

            # Rate limiting
            await asyncio.sleep(0.15)  # ~6-7 requests per second

    # Summary
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"Total processed: {results['total']}")
    print(
        f"Found ATC: {results['found']} ({100 * results['found'] / results['total']:.1f}%)"
    )
    print(f"Not found: {results['not_found']}")

    # Save results
    if not args.dry_run and results["matches"]:
        with open(OUTPUT_FILE, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {OUTPUT_FILE}")

    return results


def main():
    return asyncio.run(async_main())


if __name__ == "__main__":
    main()
