#!/usr/bin/env python3
"""
Drug ATC Enrichment - KEGG ID-based lookup for placeholder ATC drugs
Target: 2,683 drugs with placeholder ATC codes
"""

import json
import time
import re
import requests
import os
from pathlib import Path


def load_drugs_database():
    with open("data/drugs.js", "r", encoding="utf-8") as f:
        content = f.read()

    start = content.find("{")
    end = content.rfind("}") + 1
    json_str = content[start:end]
    data = json.loads(json_str)
    return data["drugs"]


def find_drugs_needing_atc(drugs):
    drugs_needing_atc = []
    for drug in drugs:
        atc = drug.get("atc_code", "")
        kegg_id = drug.get("kegg_id")

        if atc and atc.startswith("V99XX99") and kegg_id:
            drugs_needing_atc.append(drug)

    return drugs_needing_atc


def batch_kegg_atc_lookup(kegg_ids):
    """
    Query KEGG API for ATC codes using KEGG IDs
    KEGG API: https://rest.kegg.jp/list/<database>/<entry>
    We'll use: https://rest.kegg.jp/get/<database>/<entry>/<field>
    """
    atc_updates = {}
    batch_size = 10

    print(f"Querying KEGG API for {len(kegg_ids)} drugs...")

    for i in range(0, len(kegg_ids), batch_size):
        batch = kegg_ids[i : i + batch_size]
        print(f"Processing batch {i // batch_size}...", end="")

        for kegg_id in batch:
            try:
                kegg_api_key = os.environ.get("KEGG_API_KEY", "")

                headers = {}
                if kegg_api_key:
                    headers["Authorization"] = f"Bearer {kegg_api_key}"

                url = f"https://rest.kegg.jp/get/dr:{kegg_id}"
                response = requests.get(url, headers=headers, timeout=10)

                if response.status_code == 200:
                    content = response.text

                    if "ATC" in content or "atc" in content.lower():
                        import re

                        atc_match = re.search(
                            r"ATC[:\s]+([A-Z]\d{2}[A-Z]\d{2})", content, re.IGNORECASE
                        )
                        if atc_match:
                            atc_code = atc_match.group(1)
                            atc_updates[kegg_id] = atc_code
                            print(f"  ✓ Found ATC for {kegg_id}: {atc_code}")
                        else:
                            atc_match = re.search(r"D\d{7}", content)
                            if atc_match:
                                pass

                    time.sleep(0.5)

                elif response.status_code == 403:
                    print(f"  ✗ Rate limited for {kegg_id}, waiting...")
                    time.sleep(2)
                else:
                    print(f"  ✗ Error for {kegg_id}: {response.status_code}")

            except Exception as e:
                print(f"  ✗ Exception for {kegg_id}: {e}")

        if i > 0 and i % batch_size == 00:
            print(f"  Waiting 2 seconds...")
            time.sleep(2)

    return atc_updates


def main():
    print("=== Drug ATC Enrichment ===")

    drugs = load_drugs_database()
    print(f"Total drugs in database: {len(drugs)}")

    drugs_needing_atc = find_drugs_needing_atc(drugs)
    print(f"Drugs needing ATC: {len(drugs_needing_atc)}")

    if not drugs_needing_atc:
        print("No drugs need ATC enrichment!")
        return

    kegg_ids = [drug["kegg_id"] for drug in drugs_needing_atc]

    sample_size = 50
    sample_kegg_ids = kegg_ids[:sample_size]

    print(f"\nQuerying sample of {sample_size} drugs from KEGG API...")
    atc_updates = batch_kegg_atc_lookup(sample_kegg_ids)

    print(f"\nResults:")
    print(f"ATC codes found: {len(atc_updates)}")

    if atc_updates:
        print("\nSample ATC mappings:")
        for kegg_id, atc_code in list(atc_updates.items())[:5]:
            drug_name = next(
                (d["name"] for d in drugs_needing_atc if d["kegg_id"] == kegg_id), None
            )
            if drug_name:
                print(f"  {kegg_id} ({drug_name.get('name', 'Unknown')}): {atc_code}")
    else:
        print("No ATC codes found in sample")

    output = {
        "total_drugs": len(drugs),
        "drugs_needing_atc": len(drugs_needing_atc),
        "sample_size": sample_size,
        "atc_codes_found": len(atc_updates),
        "atc_updates": atc_updates,
    }

    with open("atc_enrichment_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to atc_enrichment_results.json")


if __name__ == "__main__":
    main()
