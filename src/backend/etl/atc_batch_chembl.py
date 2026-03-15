#!/usr/bin/env python3
"""
Batch ATC Lookup - ChEMBL Source

Query ChEMBL API for drugs with missing/placeholder ATC codes.
Stores results with source provenance and confidence scores.

Usage:
    python -m src.backend.etl.atc_batch_chembl [--batch-size 100] [--dry-run]

Features:
- Respects 10 req/sec rate limit
- Processes in batches of 100 drugs
- Checkpoint support for resumable runs
- Confidence scoring: 0.9 for ChEMBL direct
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
RATE_LIMIT_PER_SEC = 10.0
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3
BATCH_SIZE = 100
CHECKPOINT_INTERVAL = 50

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DRUGS_FILE = DATA_DIR / "drugs.json"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "atc_chembl_checkpoint.json"
EVIDENCE_DIR = PROJECT_ROOT / ".sisyphus" / "evidence"
REPORTS_DIR = DATA_DIR / "reports"

# ChEMBL API
CHEMBL_API_BASE = "https://www.ebi.ac.uk/chembl/api/data"


class ChEMBLBatchProcessor:
    """
    Batch ATC lookup processor for ChEMBL API.

    Features:
    - Async HTTP with connection pooling
    - Rate limiting (10 req/sec)
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
                base_url=CHEMBL_API_BASE,
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
        self, endpoint: str, params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Make API request with retry and backoff."""
        client = await self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                await self._rate_limit_wait()
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 404:
                    return None
                if e.response.status_code == 429:
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
            - chembl_id: ChEMBL ID (or None)
            - source: "chembl"
            - confidence: 0.9 (high confidence for direct ChEMBL)
            - alternatives: List of alternative ATC codes
            - retrieved_at: Timestamp
            - error: Error message (or None)
        """
        result = {
            "drug_id": drug.get("id"),
            "atc_code": None,
            "atc_category": None,
            "chembl_id": None,
            "source": "chembl",
            "confidence": None,
            "alternatives": [],
            "retrieved_at": datetime.utcnow().isoformat(),
            "error": None,
        }

        # Try by ChEMBL ID first
        chembl_id = drug.get("chembl_id")
        if chembl_id:
            data = await self._request_with_retry(f"/molecule/{chembl_id}")
            if data:
                atc_codes = self._extract_atc_codes(data)
                if atc_codes:
                    result["chembl_id"] = chembl_id
                    result["atc_code"] = atc_codes[0]
                    result["atc_category"] = atc_codes[0][0] if atc_codes[0] else None
                    result["confidence"] = 0.9
                    result["alternatives"] = atc_codes[1:] if len(atc_codes) > 1 else []
                    return result

        # Try by name search
        name = drug.get("name", "")
        if name:
            clean_name = name.split("/")[0].strip()
            data = await self._request_with_retry(
                "/molecule/search.json", params={"q": clean_name}
            )
            if data:
                molecules = data.get("molecules", [])
                for mol in molecules[:3]:  # Check top 3 matches
                    atc_codes = self._extract_atc_codes(mol)
                    if atc_codes:
                        result["chembl_id"] = mol.get("molecule_chembl_id")
                        result["atc_code"] = atc_codes[0]
                        result["atc_category"] = (
                            atc_codes[0][0] if atc_codes[0] else None
                        )
                        result["confidence"] = 0.7  # Lower confidence for name match
                        result["alternatives"] = (
                            atc_codes[1:] if len(atc_codes) > 1 else []
                        )
                        return result

        return result

    def _extract_atc_codes(self, mol_data: Dict) -> List[str]:
        """Extract ATC codes from ChEMBL molecule data."""
        atc_codes = []

        # Try atc_classifications field
        atc_list = mol_data.get("atc_classifications", [])
        if atc_list:
            for atc in atc_list:
                code = atc.get("atc_code") if isinstance(atc, dict) else atc
                if code and self._validate_atc_format(code):
                    atc_codes.append(code)

        # Try molecule_properties.atc_code
        props = mol_data.get("molecule_properties", {})
        if isinstance(props, dict):
            atc_code = props.get("atc_code")
            if atc_code and self._validate_atc_format(atc_code):
                atc_codes.append(atc_code)

        return list(set(atc_codes))  # Deduplicate

    def _validate_atc_format(self, code: str) -> bool:
        """Validate ATC code format: X99XX99 (not placeholder)."""
        import re

        if not code or len(code) != 7:
            return False
        # Match ATC format: letter + 2 digits + 2 letters + 2 digits
        pattern = r"^[A-Z]\d{2}[A-Z]{2}\d{2}$"
        if re.match(pattern, code):
            # Check it's not a placeholder (XX99)
            return "99XX99" not in code and not code.endswith("99XX99")
        return False

    async def process_batch(
        self, drugs: List[Dict], dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Process a batch of drugs.

        Args:
            drugs: List of drug dicts
            dry_run: If True, don't save results

        Returns:
            Processing statistics
        """
        print(f"\n{'=' * 60}")
        print(f"ChEMBL Batch ATC Lookup Processor")
        print(f"{'=' * 60}")
        print(f"Batch size: {len(drugs)}")
        print(f"Rate limit: {self.rate_limit} req/sec")
        print(f"Dry run: {dry_run}")

        # Load checkpoint
        self._load_checkpoint()
        print(f"Resuming from checkpoint: {len(self.processed_ids)} already processed")

        # Filter unprocessed drugs
        drugs_to_process = [d for d in drugs if d.get("id") not in self.processed_ids]
        print(f"Drugs to process: {len(drugs_to_process)}")

        if not drugs_to_process:
            print("\n✓ All drugs already processed!")
            return self.stats

        # Process drugs
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
                    f"({rate:.1f} drugs/sec, ETA: {eta:.0f}s)"
                )

            # Lookup ATC
            result = await self.lookup_atc_for_drug(drug)

            # Store result
            self.results[drug_id] = result
            self.processed_ids.add(drug_id)

            # Update stats
            self.stats["total_processed"] += 1
            if result["atc_code"]:
                self.stats["atc_found"] += 1
            elif result["error"]:
                self.stats["errors"] += 1
            else:
                self.stats["no_atc"] += 1

            # Checkpoint periodically
            if not dry_run and len(self.processed_ids) % CHECKPOINT_INTERVAL == 0:
                self._save_checkpoint()

        # Final checkpoint
        if not dry_run:
            self._save_checkpoint()

        elapsed = time.time() - start_time
        print(f"\n{'=' * 60}")
        print(f"Processing Complete")
        print(f"{'=' * 60}")
        print(f"Total processed: {self.stats['total_processed']}")
        print(f"ATC codes found: {self.stats['atc_found']}")
        print(f"No ATC found: {self.stats['no_atc']}")
        print(f"Errors: {self.stats['errors']}")
        print(f"Elapsed: {elapsed:.1f}s")
        print(f"Rate: {self.stats['total_processed'] / elapsed:.1f} drugs/sec")

        return self.stats

    def _load_checkpoint(self) -> None:
        """Load checkpoint if exists."""
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
        """Generate detailed report of ATC enrichment."""
        from collections import Counter

        report = {
            "source": "chembl",
            "timestamp": datetime.utcnow().isoformat(),
            "summary": self.stats,
            "atc_category_distribution": {},
            "confidence_distribution": {},
            "drugs_updated": [],
        }

        # Calculate distributions
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
                            "confidence": conf,
                        }
                    )

        report["atc_category_distribution"] = dict(categories)
        report["confidence_distribution"] = dict(confidences)
        report["drugs_updated"] = updated_drugs[:100]  # First 100

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
    """Filter drugs with placeholder or missing ATC codes."""
    return [
        d
        for d in drugs
        if d.get("atc_code", "").endswith("99XX99")
        or d.get("atc_code", "").startswith("V99")
        or not d.get("atc_code")
    ]


async def main():
    parser = argparse.ArgumentParser(description="ChEMBL Batch ATC Lookup")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-rate-limit", action="store_true")
    args = parser.parse_args()

    # Test rate limiting
    if args.test_rate_limit:
        print("Testing rate limiting...")
        processor = ChEMBLBatchProcessor()
        start = time.time()
        for _ in range(20):
            await processor._rate_limit_wait()
        elapsed = time.time() - start
        expected = 20 / RATE_LIMIT_PER_SEC
        print(f"  20 requests in {elapsed:.2f}s (expected: {expected:.2f}s)")
        print(f"  Rate: {20 / elapsed:.1f} req/sec (target: {RATE_LIMIT_PER_SEC})")
        await processor.close()
        return

    # Load drugs
    print(f"Loading drugs from {DRUGS_FILE}...")
    drugs = load_drugs()
    print(f"Total drugs: {len(drugs)}")

    # Filter drugs needing ATC
    drugs_needing_atc = filter_drugs_needing_atc(drugs)
    print(f"Drugs needing ATC: {len(drugs_needing_atc)}")

    # Process batch
    processor = ChEMBLBatchProcessor(batch_size=args.batch_size)
    try:
        stats = await processor.process_batch(drugs_needing_atc, dry_run=args.dry_run)

        # Generate report
        if not args.dry_run:
            report = processor.generate_report(drugs_needing_atc)
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            report_file = (
                REPORTS_DIR
                / f"chembl_atc_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\nReport saved to: {report_file}")

            # Save evidence
            EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
            evidence_file = EVIDENCE_DIR / "task-12-chembl-batch.log"
            with open(evidence_file, "w") as f:
                f.write(f"ChEMBL Batch ATC Lookup Results\n")
                f.write(f"{'=' * 60}\n")
                f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
                f.write(f"Total processed: {stats['total_processed']}\n")
                f.write(f"ATC codes found: {stats['atc_found']}\n")
                f.write(f"No ATC found: {stats['no_atc']}\n")
                f.write(f"Errors: {stats['errors']}\n")
            print(f"Evidence saved to: {evidence_file}")
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
