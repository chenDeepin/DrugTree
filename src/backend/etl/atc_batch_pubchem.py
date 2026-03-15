#!/usr/bin/env python3
"""
Batch ATC Lookup - PubChem Source

Query PubChem PUG-REST API for drugs with missing/placeholder ATC codes.
Stores results with source provenance and confidence scores.

Usage:
    python -m src.backend.etl.atc_batch_pubchem [--batch-size 100] [--dry-run]

Features:
- Respects 5 req/sec rate limit
- SMILES-based matching
- Checkpoint support for resumable runs
- Confidence scoring: 0.8 for PubChem
- Provenance tracking with timestamps
"""

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Rate limiting
RATE_LIMIT_PER_SEC = 5.0
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3
BATCH_SIZE = 100
CHECKPOINT_INTERVAL = 50

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DRUGS_FILE = DATA_DIR / "drugs.json"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "atc_pubchem_checkpoint.json"
EVIDENCE_DIR = PROJECT_ROOT / ".sisyphus" / "evidence"
REPORTS_DIR = DATA_DIR / "reports"

# PubChem API
PUBCHEM_API_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


class PubChemBatchProcessor:
    """
    Batch ATC lookup processor for PubChem PUG-REST API.

    Features:
    - Async HTTP with connection pooling
    - Rate limiting (5 req/sec)
    - Retry with exponential backoff
    - Checkpoint support
    - Provenance tracking
    """

    def __init__(
        self,
        rate_limit: float = RATE_LIMIT_PER_SEC,
        max_retries: int = MAX_RETRIES,
        batch_size: int = BATCH_SIZE,
    ):
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.batch_size = batch_size
        self._last_request_time = 0.0
        self._client: Optional[httpx.AsyncClient] = None

        # Statistics
        self.stats = {
            "total_processed": 0,
            "atc_found": 0,
            "by_cid": 0,
            "by_smiles": 0,
            "by_name": 0,
            "no_atc": 0,
            "errors": 0,
            "skipped": 0,
        }

        # Results
        self.results: Dict[str, Dict] = {}
        self.processed_ids: set = set()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def _rate_limit_wait(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        wait_time = (1.0 / self.rate_limit) - elapsed
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self._last_request_time = time.time()

    async def _request_with_retry(
        self, url: str, params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Make API request with retry and backoff."""
        client = await self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                await self._rate_limit_wait()
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 404:
                    return None
                if e.response.status_code == 429:
                    # Rate limited - wait longer
                    wait = 60.0
                else:
                    wait = 2.0**attempt
                await asyncio.sleep(wait)
            except httpx.RequestError as e:
                last_error = e
                await asyncio.sleep(2.0**attempt)

        self.stats["errors"] += 1
        return None

    async def lookup_atc_for_drug(self, drug: Dict) -> Dict[str, Any]:
        """
        Lookup ATC code for a single drug.

        Returns:
            Dict with keys:
            - drug_id: Drug identifier
            - atc_code: ATC code (or None)
            - atc_category: ATC category letter (or None)
            - pubchem_cid: PubChem CID (or None)
            - source: "pubchem"
            - confidence: 0.8
            - alternatives: List of alternative ATC codes
            - retrieved_at: Timestamp
            - error: Error message (or None)
        """
        result = {
            "drug_id": drug.get("id"),
            "atc_code": None,
            "atc_category": None,
            "pubchem_cid": None,
            "source": "pubchem",
            "confidence": None,
            "alternatives": [],
            "retrieved_at": datetime.utcnow().isoformat(),
            "error": None,
        }

        # Try by PubChem CID first
        pubchem_cid = drug.get("pubchem_cid")
        if pubchem_cid:
            cid_data = await self._request_with_retry(
                f"{PUBCHEM_API_BASE}/compound/cid/{pubchem_cid}/xrefs/RegistryID,SourceName,SourceID/json"
            )
            if cid_data:
                # Try to get ATC from xrefs
                atc_codes = self._extract_atc_from_xrefs(cid_data)
                if atc_codes:
                    result["pubchem_cid"] = pubchem_cid
                    result["atc_code"] = atc_codes[0]
                    result["atc_category"] = atc_codes[0][0] if atc_codes[0] else None
                    result["confidence"] = 0.8
                    result["alternatives"] = atc_codes[1:] if len(atc_codes) > 1 else []
                    self.stats["by_cid"] += 1
                    return result

        # Try by SMILES
        smiles = drug.get("smiles")
        if smiles:
            # Use SMILES to find CID first
            smiles_data = await self._request_with_retry(
                f"{PUBCHEM_API_BASE}/compound/smiles/cids/JSON",
                params={"smiles": smiles},
            )
            if (
                smiles_data
                and "IdentifierList" in smiles_data
                and smiles_data["IdentifierList"]["CID"]
            ):
                cid = smiles_data["IdentifierList"]["CID"][0]
                result["pubchem_cid"] = cid

                # Get ATC for this CID
                cid_data = await self._request_with_retry(
                    f"{PUBCHEM_API_BASE}/compound/cid/{cid}/xrefs/RegistryID,SourceName,SourceID/json"
                )
                if cid_data:
                    atc_codes = self._extract_atc_from_xrefs(cid_data)
                    if atc_codes:
                        result["atc_code"] = atc_codes[0]
                        result["atc_category"] = (
                            atc_codes[0][0] if atc_codes[0] else None
                        )
                        result["confidence"] = 0.8
                        result["alternatives"] = (
                            atc_codes[1:] if len(atc_codes) > 1 else []
                        )
                        self.stats["by_smiles"] += 1
                        return result

        # Try by name search
        name = drug.get("name", "")
        if name:
            clean_name = name.split("/")[0].strip()
            name_data = await self._request_with_retry(
                f"{PUBCHEM_API_BASE}/compound/name/{clean_name}/cids/JSON"
            )
            if (
                name_data
                and "IdentifierList" in name_data
                and name_data["IdentifierList"]["CID"]
            ):
                cid = name_data["IdentifierList"]["CID"][0]
                result["pubchem_cid"] = cid

                # Get ATC for this CID
                cid_data = await self._request_with_retry(
                    f"{PUBCHEM_API_BASE}/compound/cid/{cid}/xrefs/RegistryID,SourceName,SourceID/json"
                )
                if cid_data:
                    atc_codes = self._extract_atc_from_xrefs(cid_data)
                    if atc_codes:
                        result["atc_code"] = atc_codes[0]
                        result["atc_category"] = (
                            atc_codes[0][0] if atc_codes[0] else None
                        )
                        result["confidence"] = 0.8
                        result["alternatives"] = (
                            atc_codes[1:] if len(atc_codes) > 1 else []
                        )
                        self.stats["by_name"] += 1
                        return result

        return result

    def _extract_atc_from_xrefs(self, data: Dict) -> List[str]:
        """Extract ATC codes from PubChem xrefs data."""
        atc_codes = []

        try:
            info_list = data.get("InformationList", {}).get("Information", [])
            for info in info_list:
                # Check if this is from a source that provides ATC codes
                source_name = info.get("SourceName", "")
                source_id = info.get("SourceID", "")

                # ATC codes often come from KEGG Drug or similar sources
                if "ATC" in source_id or "atc" in source_id.lower():
                    # Extract ATC code pattern
                    import re

                    atc_pattern = r"[A-Z]\d{2}[A-Z]{2}\d{2}"
                    matches = re.findall(atc_pattern, source_id)
                    atc_codes.extend(matches)
        except Exception:
            pass

        # Remove duplicates while preserving order
        seen = set()
        unique_codes = []
        for code in atc_codes:
            if code not in seen:
                seen.add(code)
                unique_codes.append(code)

        return unique_codes

    async def process_batch(
        self, drugs: List[Dict], dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Process a batch of drugs for ATC lookup.

        Args:
            drugs: List of drug dictionaries
            dry_run: If True, don't save results

        Returns:
            Statistics dictionary
        """
        print(f"\n{'=' * 60}")
        print("PubChem Batch ATC Lookup Processor")
        print(f"{'=' * 60}")
        print(f"Batch size: {len(drugs)}")
        print(f"Rate limit: {self.rate_limit} req/sec")
        print(f"Dry run: {dry_run}")

        self._load_checkpoint()
        print(f"Resuming from checkpoint: {len(self.processed_ids)} already processed")

        drugs_to_process = [d for d in drugs if d.get("id") not in self.processed_ids]
        print(f"Drugs to process: {len(drugs_to_process)}")

        if not drugs_to_process:
            print("\n✓ All drugs already processed!")
            return self.stats

        start_time = time.time()

        for i, drug in enumerate(drugs_to_process):
            drug_id = drug.get("id")

            # Progress indicator
            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (len(drugs_to_process) - i - 1) / rate if rate > 0 else 0
                print(
                    f"  Progress: {i + 1}/{len(drugs_to_process)} "
                    f"({self.stats['atc_found']} found, ETA: {eta:.0f}s)"
                )

            try:
                result = await self.lookup_atc_for_drug(drug)

                self.results[drug_id] = result
                self.processed_ids.add(drug_id)

                self.stats["total_processed"] += 1
                if result["atc_code"]:
                    self.stats["atc_found"] += 1
                else:
                    self.stats["no_atc"] += 1

            except Exception as e:
                self.stats["errors"] += 1
                self.results[drug_id] = {
                    "drug_id": drug_id,
                    "error": str(e),
                    "retrieved_at": datetime.utcnow().isoformat(),
                }

            # Checkpoint periodically
            if not dry_run and len(self.processed_ids) % CHECKPOINT_INTERVAL == 0:
                self._save_checkpoint()

        if not dry_run:
            self._save_checkpoint()

        elapsed = time.time() - start_time
        print(f"\n{'=' * 60}")
        print("Processing Complete")
        print(f"{'=' * 60}")
        print(f"Total processed: {self.stats['total_processed']}")
        print(f"ATC codes found: {self.stats['atc_found']}")
        print(f"  - By CID: {self.stats['by_cid']}")
        print(f"  - By SMILES: {self.stats['by_smiles']}")
        print(f"  - By Name: {self.stats['by_name']}")
        print(f"No ATC found: {self.stats['no_atc']}")
        print(f"Errors: {self.stats['errors']}")
        print(f"Elapsed: {elapsed:.1f}s")

        return self.stats

    def _load_checkpoint(self) -> None:
        """Load checkpoint if it exists."""
        if CHECKPOINT_FILE.exists():
            with open(CHECKPOINT_FILE, "r") as f:
                data = json.load(f)
                self.processed_ids = set(data.get("processed_ids", []))
                self.results = data.get("results", {})

    def _save_checkpoint(self) -> None:
        """Save checkpoint."""
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(
                {
                    "processed_ids": list(self.processed_ids),
                    "results": self.results,
                    "stats": self.stats,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                f,
                indent=2,
            )

    def generate_report(self, drugs: List[Dict]) -> Dict[str, Any]:
        """Generate report of processing results."""
        from collections import Counter

        report = {
            "source": "pubchem",
            "timestamp": datetime.utcnow().isoformat(),
            "summary": self.stats,
            "atc_category_distribution": {},
            "confidence_distribution": {},
            "drugs_updated": [],
        }

        categories = Counter()
        confidences = Counter()
        updated_drugs = []

        for drug in drugs:
            drug_id = drug.get("id")
            if drug_id in self.results:
                result = self.results[drug_id]
                if result["atc_code"]:
                    categories[result["atc_category"] or "?"] += 1
                    conf = result["confidence"]
                    conf_key = f"{conf:.1f}" if conf else "none"
                    confidences[conf_key] += 1

                    updated_drugs.append(
                        {
                            "id": drug_id,
                            "name": drug.get("name"),
                            "old_atc": drug.get("atc_code"),
                            "new_atc": result["atc_code"],
                            "pubchem_cid": result["pubchem_cid"],
                            "confidence": conf,
                        }
                    )

        report["atc_category_distribution"] = dict(categories)
        report["confidence_distribution"] = dict(confidences)
        report["drugs_updated"] = updated_drugs[:100]

        return report

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


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


async def main():
    parser = argparse.ArgumentParser(description="PubChem Batch ATC Lookup")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-drug", type=str, help="Test single drug lookup")
    args = parser.parse_args()

    if args.test_drug:
        print(f"Testing lookup for: {args.test_drug}")
        processor = PubChemBatchProcessor()
        test_drug = {"id": "test", "name": args.test_drug}
        result = await processor.lookup_atc_for_drug(test_drug)
        print(f"Result: {json.dumps(result, indent=2)}")
        await processor.close()
        return

    print(f"Loading drugs from {DRUGS_FILE}...")
    drugs = load_drugs()
    print(f"Total drugs: {len(drugs)}")

    drugs_needing_atc = filter_drugs_needing_atc(drugs)
    print(f"Drugs needing ATC: {len(drugs_needing_atc)}")

    processor = PubChemBatchProcessor(batch_size=args.batch_size)
    try:
        stats = await processor.process_batch(drugs_needing_atc, dry_run=args.dry_run)

        if not args.dry_run:
            report = processor.generate_report(drugs_needing_atc)
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            report_file = (
                REPORTS_DIR
                / f"pubchem_atc_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\nReport saved to {report_file}")

            EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
            evidence_file = EVIDENCE_DIR / "task-14-pubchem-batch.log"
            with open(evidence_file, "w") as f:
                f.write(f"PubChem Batch ATC Lookup Results\n")
                f.write(f"{'=' * 60}\n")
                f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
                f.write(f"Total processed: {stats['total_processed']}\n")
                f.write(f"ATC codes found: {stats['atc_found']}\n")
                f.write(f"By CID: {stats['by_cid']}\n")
                f.write(f"By SMILES: {stats['by_smiles']}\n")
                f.write(f"By Name: {stats['by_name']}\n")
                f.write(f"No ATC found: {stats['no_atc']}\n")
                f.write(f"Errors: {stats['errors']}\n")
            print(f"Evidence saved to {evidence_file}")
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
