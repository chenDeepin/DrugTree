#!/usr/bin/env python3
"""
Batch ATC Lookup - KEGG Source

Query KEGG Drug API for ATC classifications with highest confidence.
KEGG provides authoritative ATC codes from WHO collaborations.

Usage:
    python -m src.backend.etl.atc_batch_kegg [--batch-size 50] [--dry-run]

Features:
- Respects KEGG REST API rate limits
- KEGG drug name/SMILES matching
- Confidence=1.0 for KEGG-sourced ATC codes (highest)
- Checkpoint support for resumable runs
- Progress logging with ETA
"""

import argparse
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Rate limiting
RATE_LIMIT_PER_SEC = 5.0
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3
BATCH_SIZE = 50
CHECKPOINT_INTERVAL = 30

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DRUGS_FILE = DATA_DIR / "drugs.json"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "atc_kegg_checkpoint.json"
EVIDENCE_DIR = PROJECT_ROOT / ".sisyphus" / "evidence"
REPORTS_DIR = DATA_DIR / "reports"

# KEGG API
KEGG_API_BASE = "https://rest.kegg.jp"


class KEGGBatchProcessor:
    """
    Batch ATC lookup processor for KEGG Drug API.

    KEGG provides authoritative ATC codes with highest confidence (1.0).
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

        self.stats = {
            "total_processed": 0,
            "atc_found": 0,
            "no_atc": 0,
            "errors": 0,
            "by_kegg_id": 0,
            "by_name": 0,
        }

        self.results: Dict[str, Dict] = {}
        self.processed_ids: set = set()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=KEGG_API_BASE,
                timeout=REQUEST_TIMEOUT,
            )
        return self._client

    async def _rate_limit_wait(self) -> None:
        elapsed = time.time() - self._last_request_time
        wait_time = (1.0 / self.rate_limit) - elapsed
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self._last_request_time = time.time()

    async def _request_with_retry(self, endpoint: str) -> Optional[str]:
        client = await self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                await self._rate_limit_wait()
                response = await client.get(endpoint)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as e:
                last_error = e
                await asyncio.sleep(2.0**attempt)
            except httpx.RequestError as e:
                last_error = e
                await asyncio.sleep(2.0**attempt)

        self.stats["errors"] += 1
        return None

    async def lookup_atc_for_drug(self, drug: Dict) -> Dict[str, Any]:
        result = {
            "drug_id": drug.get("id"),
            "atc_code": None,
            "atc_category": None,
            "kegg_id": None,
            "source": "kegg",
            "confidence": None,
            "alternatives": [],
            "retrieved_at": datetime.utcnow().isoformat(),
            "error": None,
        }

        kegg_id = drug.get("kegg_id")

        if kegg_id:
            text = await self._request_with_retry(f"/get/dr:{kegg_id}")
            if text:
                atc_data = self._parse_kegg_response(text)
                if atc_data:
                    result["kegg_id"] = kegg_id
                    result["atc_code"] = atc_data["primary"]
                    result["atc_category"] = (
                        atc_data["primary"][0] if atc_data["primary"] else None
                    )
                    result["confidence"] = 1.0
                    result["alternatives"] = atc_data["alternatives"]
                    self.stats["by_kegg_id"] += 1
                    return result

        name = drug.get("name", "")
        if name:
            clean_name = name.split("/")[0].strip()
            text = await self._request_with_retry(f"/find/drugs/{clean_name}")
            if text:
                kegg_ids = self._parse_find_response(text)
                for kid in kegg_ids[:3]:
                    detail = await self._request_with_retry(f"/get/dr:{kid}")
                    if detail:
                        atc_data = self._parse_kegg_response(detail)
                        if atc_data:
                            result["kegg_id"] = kid
                            result["atc_code"] = atc_data["primary"]
                            result["atc_category"] = (
                                atc_data["primary"][0] if atc_data["primary"] else None
                            )
                            result["confidence"] = 0.9
                            result["alternatives"] = atc_data["alternatives"]
                            self.stats["by_name"] += 1
                            return result

        return result

    def _parse_kegg_response(self, text: str) -> Optional[Dict[str, Any]]:
        atc_codes = []

        patterns = [
            r"ATC code:\s*([A-Z]\d{2}[A-Z]{2}\d{2})",
            r"ATC:\s*([A-Z]\d{2}[A-Z]{2}\d{2})",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for code in matches:
                if self._validate_atc_format(code):
                    atc_codes.append(code)

        if not atc_codes:
            return None

        atc_codes = list(dict.fromkeys(atc_codes))

        return {
            "primary": atc_codes[0],
            "alternatives": atc_codes[1:] if len(atc_codes) > 1 else [],
        }

    def _parse_find_response(self, text: str) -> List[str]:
        kegg_ids = []
        for line in text.strip().split("\n"):
            if line.startswith("dr:"):
                kid = line.split()[0].replace("dr:", "")
                kegg_ids.append(kid)
        return kegg_ids

    def _validate_atc_format(self, code: str) -> bool:
        if not code or len(code) != 7:
            return False
        pattern = r"^[A-Z]\d{2}[A-Z]{2}\d{2}$"
        if re.match(pattern, code):
            return "99XX99" not in code
        return False

    async def process_batch(
        self, drugs: List[Dict], dry_run: bool = False
    ) -> Dict[str, Any]:
        print(f"\n{'=' * 60}")
        print(f"KEGG Batch ATC Lookup Processor")
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

            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (len(drugs_to_process) - i - 1) / rate if rate > 0 else 0
                print(
                    f"  Progress: {i + 1}/{len(drugs_to_process)} "
                    f"(found: {self.stats['atc_found']}, ETA: {eta:.0f}s)"
                )

            result = await self.lookup_atc_for_drug(drug)

            self.results[drug_id] = result
            self.processed_ids.add(drug_id)

            self.stats["total_processed"] += 1
            if result["atc_code"]:
                self.stats["atc_found"] += 1
            else:
                self.stats["no_atc"] += 1

            if not dry_run and len(self.processed_ids) % CHECKPOINT_INTERVAL == 0:
                self._save_checkpoint()

        if not dry_run:
            self._save_checkpoint()

        elapsed = time.time() - start_time
        print(f"\n{'=' * 60}")
        print(f"Processing Complete")
        print(f"{'=' * 60}")
        print(f"Total processed: {self.stats['total_processed']}")
        print(f"ATC codes found: {self.stats['atc_found']}")
        print(f"  - By KEGG ID: {self.stats['by_kegg_id']}")
        print(f"  - By name search: {self.stats['by_name']}")
        print(f"No ATC found: {self.stats['no_atc']}")
        print(f"Errors: {self.stats['errors']}")
        print(f"Elapsed: {elapsed:.1f}s")

        return self.stats

    def _load_checkpoint(self) -> None:
        if CHECKPOINT_FILE.exists():
            with open(CHECKPOINT_FILE, "r") as f:
                data = json.load(f)
                self.processed_ids = set(data.get("processed_ids", []))
                self.results = data.get("results", {})

    def _save_checkpoint(self) -> None:
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
        from collections import Counter

        report = {
            "source": "kegg",
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
                            "kegg_id": result["kegg_id"],
                            "confidence": conf,
                        }
                    )

        report["atc_category_distribution"] = dict(categories)
        report["confidence_distribution"] = dict(confidences)
        report["drugs_updated"] = updated_drugs[:100]

        return report

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


def load_drugs() -> List[Dict]:
    with open(DRUGS_FILE, "r") as f:
        data = json.load(f)
        if isinstance(data, dict) and "drugs" in data:
            return data["drugs"]
        elif isinstance(data, list):
            return data
        else:
            raise ValueError(f"Invalid drugs.json format")


def filter_drugs_needing_atc(drugs: List[Dict]) -> List[Dict]:
    return [
        d
        for d in drugs
        if d.get("atc_code", "").endswith("99XX99")
        or d.get("atc_code", "").startswith("V99")
        or not d.get("atc_code")
    ]


async def main():
    parser = argparse.ArgumentParser(description="KEGG Batch ATC Lookup")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-drug", type=str, help="Test single drug lookup")
    args = parser.parse_args()

    if args.test_drug:
        print(f"Testing lookup for: {args.test_drug}")
        processor = KEGGBatchProcessor()
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

    processor = KEGGBatchProcessor(batch_size=args.batch_size)
    try:
        stats = await processor.process_batch(drugs_needing_atc, dry_run=args.dry_run)

        if not args.dry_run:
            report = processor.generate_report(drugs_needing_atc)
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            report_file = (
                REPORTS_DIR
                / f"kegg_atc_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\nReport saved to: {report_file}")

            EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
            evidence_file = EVIDENCE_DIR / "task-13-kegg-batch.log"
            with open(evidence_file, "w") as f:
                f.write(f"KEGG Batch ATC Lookup Results\n")
                f.write(f"{'=' * 60}\n")
                f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
                f.write(f"Total processed: {stats['total_processed']}\n")
                f.write(f"ATC codes found: {stats['atc_found']}\n")
                f.write(f"By KEGG ID: {stats['by_kegg_id']}\n")
                f.write(f"By name: {stats['by_name']}\n")
                f.write(f"No ATC found: {stats['no_atc']}\n")
                f.write(f"Errors: {stats['errors']}\n")
            print(f"Evidence saved to: {evidence_file}")
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
