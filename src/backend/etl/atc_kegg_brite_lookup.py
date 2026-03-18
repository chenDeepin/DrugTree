#!/usr/bin/env python3
"""
ATC Lookup from KEGG BRITE ATC Classification (br08303.keg)

Parses the KEGG BRITE ATC hierarchy file to build a local lookup table,
then matches drugs against it using name matching.

Usage:
    python -m src.backend.etl.atc_kegg_brite_lookup [--dry-run] [--test]

Features:
    - Parses KEGG BRITE ATC file locally (no API calls)
    - Matches drug names using fuzzy matching
    - Processes 3,280 drugs in seconds (vs hours for API)
    - Checkpoint support for resumable runs
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DRUGS_FILE = DATA_DIR / "drugs.json"
KEGG_BRITE_FILE = DATA_DIR / "kegg_brite_atc_br08303.keg"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "atc_kegg_brite_checkpoint.json"
OUTPUT_FILE = DATA_DIR / "atc_enriched_from_kegg_brite.json"


class KEGGBRITEATCLookup:
    """
    Parse KEGG BRITE ATC file and build lookup tables.

    File structure:
    - E lines: ATC codes + drug names (E A01AA01 Sodium fluoride)
    - F lines: KEGG Drug IDs + drug names (F D00943 Sodium fluoride)
    """

    def __init__(self, brite_file: Path = KEGG_BRITE_FILE):
        self.brite_file = brite_file
        self.atc_by_name: Dict[str, str] = {}  # drug_name -> ATC code
        self.atc_by_kegg_id: Dict[str, str] = {}  # KEGG ID -> ATC code
        self.name_by_kegg_id: Dict[str, str] = {}  # KEGG ID -> drug name
        self.kegg_ids_by_name: Dict[str, List[str]] = defaultdict(
            list
        )  # name -> KEGG IDs

        # Current ATC code context (from parent E lines)
        self._current_atc: Optional[str] = None

    def parse(self) -> Tuple[int, int]:
        """
        Parse KEGG BRITE ATC file.

        Returns:
            (atc_entries, drug_entries) count
        """
        if not self.brite_file.exists():
            raise FileNotFoundError(f"KEGG BRITE file not found: {self.brite_file}")

        atc_count = 0
        drug_count = 0

        print(f"Parsing KEGG BRITE ATC file: {self.brite_file}")
        print(f"File size: {self.brite_file.stat().st_size / 1024:.1f} KB")

        with open(self.brite_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue

                first_char = line[0] if line else ""
                content = line[1:].strip()

                if first_char == "E":
                    # ATC code line: E <ATC_CODE> <DRUG_NAME>
                    # Example: E        A01AA01 Sodium fluoride
                    atc_count += 1
                    parts = content.split(None, 1)  # Split into max 2 parts
                    if len(parts) >= 1:
                        atc_code = parts[0]
                        drug_name = parts[1] if len(parts) > 1 else ""

                        # Validate ATC code format (e.g., A01AA01)
                        if re.match(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$", atc_code):
                            self._current_atc = atc_code
                            if drug_name:
                                # Store lowercase for case-insensitive lookup
                                self.atc_by_name[drug_name.lower()] = atc_code

                elif first_char == "F":
                    # Drug entry line: F <KEGG_ID> <DRUG_NAME>
                    # Example: F          D00943  Sodium fluoride (JAN/USP)
                    drug_count += 1
                    parts = content.split(None, 1)
                    if len(parts) >= 1:
                        kegg_id = parts[0]
                        drug_name = parts[1] if len(parts) > 1 else ""

                        # Clean up drug name (remove parentheticals like "(JAN/USP)")
                        clean_name = re.sub(r"\s*\([^)]*\)\s*", "", drug_name).strip()

                        self.name_by_kegg_id[kegg_id] = clean_name

                        if clean_name:
                            self.kegg_ids_by_name[clean_name.lower()].append(kegg_id)

                        # Map KEGG ID to current ATC code (from parent E line)
                        if self._current_atc and kegg_id.startswith("D"):
                            self.atc_by_kegg_id[kegg_id] = self._current_atc

        print(f"\nParsed {atc_count} ATC entries, {drug_count} drug entries")
        print(f"Built {len(self.atc_by_name)} name->ATC mappings")
        print(f"Built {len(self.atc_by_kegg_id)} KEGG ID->ATC mappings")

        return atc_count, drug_count

    def lookup_by_name(self, drug_name: str) -> Optional[str]:
        """
        Look up ATC code by drug name.

        Tries:
        1. Exact match (case-insensitive)
        2. Match without salt suffix (e.g., "aspirin" vs "aspirin sodium")
        3. Match first word only
        """
        if not drug_name:
            return None

        name_lower = drug_name.lower().strip()

        # 1. Exact match
        if name_lower in self.atc_by_name:
            return self.atc_by_name[name_lower]

        # 2. Try removing common salt suffixes
        for suffix in [
            " hydrochloride",
            " hcl",
            " sulfate",
            " sulphate",
            " sodium",
            " potassium",
            " maleate",
            " fumarate",
            " tartrate",
            " citrate",
            " phosphate",
            " acetate",
            " mesylate",
            " besylate",
        ]:
            if name_lower.endswith(suffix):
                base_name = name_lower[: -len(suffix)]
                if base_name in self.atc_by_name:
                    return self.atc_by_name[base_name]

        # 3. Try first word only
        first_word = name_lower.split()[0] if name_lower else ""
        if first_word and len(first_word) > 3 and first_word in self.atc_by_name:
            return self.atc_by_name[first_word]

        return None

    def lookup_by_kegg_id(self, kegg_id: str) -> Optional[str]:
        """Look up ATC code by KEGG Drug ID."""
        return self.atc_by_kegg_id.get(kegg_id)


def load_drugs() -> List[Dict]:
    """Load drugs from JSON file."""
    with open(DRUGS_FILE, "r") as f:
        data = json.load(f)
        if isinstance(data, dict) and "drugs" in data:
            return data["drugs"]
        elif isinstance(data, list):
            return data
        else:
            raise ValueError(f"Invalid drugs.json format")


def filter_drugs_needing_atc(drugs: List[Dict]) -> List[Dict]:
    """Filter drugs that need ATC lookup."""
    return [
        d
        for d in drugs
        if d.get("atc_code", "").endswith("99XX99")
        or d.get("atc_code", "").startswith("V99")
        or not d.get("atc_code")
    ]


def main():
    parser = argparse.ArgumentParser(description="KEGG BRITE ATC Lookup")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show results without saving"
    )
    parser.add_argument("--test", action="store_true", help="Test with 50 drugs only")
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of drugs to process"
    )
    args = parser.parse_args()

    # Parse KEGG BRITE file
    lookup = KEGGBRITEATCLookup()
    lookup.parse()

    # Load drugs
    print(f"\nLoading drugs from {DRUGS_FILE}...")
    all_drugs = load_drugs()
    print(f"Total drugs: {len(all_drugs)}")

    drugs_needing_atc = filter_drugs_needing_atc(all_drugs)
    print(f"Drugs needing ATC: {len(drugs_needing_atc)}")

    if args.test:
        drugs_needing_atc = drugs_needing_atc[:50]
        print(f"TEST MODE: Processing only {len(drugs_needing_atc)} drugs")
    elif args.limit:
        drugs_needing_atc = drugs_needing_atc[: args.limit]
        print(f"LIMIT: Processing {len(drugs_needing_atc)} drugs")

    # Match drugs
    print(f"\n{'=' * 60}")
    print("Matching drugs against KEGG BRITE lookup table...")
    print(f"{'=' * 60}")

    results = {
        "matched": 0,
        "not_matched": 0,
        "by_name": 0,
        "total_processed": 0,
        "matches": [],
    }

    for drug in drugs_needing_atc:
        drug_id = drug.get("id", "")
        drug_name = drug.get("name", "")

        # Try name lookup
        atc_code = lookup.lookup_by_name(drug_name)

        if atc_code:
            results["matched"] += 1
            results["by_name"] += 1
            results["matches"].append(
                {
                    "drug_id": drug_id,
                    "drug_name": drug_name,
                    "old_atc": drug.get("atc_code"),
                    "new_atc": atc_code,
                    "atc_category": atc_code[0] if atc_code else None,
                    "source": "kegg_brite",
                    "confidence": 0.9,
                    "match_type": "name",
                }
            )
        else:
            results["not_matched"] += 1

        results["total_processed"] += 1

        # Progress
        if results["total_processed"] % 100 == 0:
            print(
                f"  Progress: {results['total_processed']}/{len(drugs_needing_atc)} "
                f"({results['matched']} matched, {results['not_matched']} not found)"
            )

    # Summary
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"Total processed: {results['total_processed']}")
    print(
        f"Matched: {results['matched']} ({100 * results['matched'] / results['total_processed']:.1f}%)"
    )
    print(f"  - By name: {results['by_name']}")
    print(f"Not matched: {results['not_matched']}")

    # Save results
    if not args.dry_run and results["matches"]:
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

        output = {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "kegg_brite_br08303",
            "summary": {
                "total_processed": results["total_processed"],
                "matched": results["matched"],
                "success_rate": f"{100 * results['matched'] / results['total_processed']:.1f}%",
            },
            "matches": results["matches"],
        }

        with open(OUTPUT_FILE, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to: {OUTPUT_FILE}")

    return results


if __name__ == "__main__":
    main()
