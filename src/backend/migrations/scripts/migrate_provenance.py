#!/usr/bin/env python3
"""
DrugTree - Provenance Migration Script (Task 9)

Adds provenance information to migrated drugs:
- Existing ATC codes: source="legacy"
- Placeholder codes: source="unknown", needs_enrichment=true
- Track enrichment status for Wave 3

Usage:
    python migrate_provenance.py [--dry-run] [--batch-size 500]

Author: DrugTree Team
Date: 2026-03-15
"""

import asyncio
import json
import logging
import sys
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db.connection import DatabaseConnection, get_db, close_db
from models.provenance import Provenance, ProvenanceSource, add_provenance

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(__file__).parent.parent.parent.parent.parent
            / "logs"
            / "migrations"
            / "migrate_provenance.log",
            mode="a",
        ),
    ],
)
logger = logging.getLogger(__name__)


# Curated drug IDs (same set as migrate_drugs.py)
CURATED_DRUG_IDS: Set[str] = {
    "1-mg-islatravir",
    "10-mg-rupatadine-on-demand",
    "20-mg-bardoxolone-methyl",
    "40-mg-laninamivir-octanoate",
    "5-mg-serlopitant-tablets",
    "5-fluorouracil-5-fu",
    "5-mg-desloratadine",
    "abacavir-abclamivudine-3tc-atazanavir-atv-ritonavir-r",
    "abediterol-0156-g",
    "abt-263",
    "ac220",
    "acetaminophen",
    "aclidinium-bromide-and-formoterol",
    "acth",
    "acyclovir",
    "adefovir-adv",
    "agomelatine",
    "alendronate",
    "alfuzosin",
    "aliskiren",
    "allopurinol",
    "alpelisib-byl719",
    "alprazolam",
    "alprostadil",
    "alteplase",
    "ambrisentan",
    "amiodarone",
    "amitriptyline",
    "amlodipine",
    "amlodipine-besylate",
    "amoxicillin",
    "ampicillin",
    "amrubicin",
    "anagrelide-retard",
    "anakinra-100-mg",
    "anastrozole-arimidex",
    "apalutamide",
    "apremilast",
    "aprepitant-pill",
    "aprocitentan-5-mg",
    "argatroban",
    "aripiprazole-im-depot",
    "artemisia-annua-leaf",
    "asp1941",
    "aspirin",
}


class ProvenanceMigrator:
    """Migrates provenance data to existing drugs."""

    def __init__(self, dry_run: bool = False, batch_size: int = 500):
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.db: Optional[DatabaseConnection] = None

        # Statistics
        self.stats = {
            "total_drugs": 0,
            "drugs_with_provenance": 0,
            "legacy_atc_count": 0,
            "needs_enrichment_count": 0,
            "curated_count": 0,
            "errors": 0,
        }

    async def init(self) -> None:
        """Initialize database connection."""
        self.db = await get_db()
        logger.info("Database connection initialized")

    async def close(self) -> None:
        """Close database connection."""
        if self.db:
            await close_db()
        logger.info("Database connection closed")

    async def fetch_drugs_without_provenance(self) -> List[Dict[str, Any]]:
        """
        Fetch drugs that don't have provenance set.

        Returns:
            List of drug records
        """
        query = """
            SELECT id, name, atc_code, atc_category, kegg_id, chembl_id
            FROM drugs
            WHERE provenance IS NULL 
               OR provenance = '{}'::jsonb
               OR provenance = 'null'::jsonb
            ORDER BY id
        """

        if not self.db:
            logger.error("Database connection not initialized")
            return []

        results = await self.db.fetch(query)
        return [dict(r) for r in results]

    def is_placeholder_code(self, atc_code: str) -> bool:
        """Check if ATC code is a placeholder (contains 99XX99)."""
        if not atc_code:
            return False
        return "99XX99" in atc_code or atc_code.endswith("XX99")

    def build_provenance(self, drug: Dict[str, Any]) -> Provenance:
        """
        Build provenance for a drug.

        Args:
            drug: Drug record with            atc_code: ATC code (may be placeholder)
            is_curated: Whether this is a curated drug

        Returns:
            Provenance object
        """
        is_curated = drug["id"] in CURATED_DRUG_IDS
        atc_code = drug.get("atc_code", "")
        is_placeholder = self.is_placeholder_code(atc_code)

        # Start with empty provenance
        provenance = None

        if is_curated:
            # Curated drug - high confidence
            provenance = add_provenance(
                provenance,
                source="curated",
                confidence=1.0,
                notes="Manually curated drug with verified ATC classification",
            )
        elif is_placeholder:
            # Placeholder code - needs enrichment
            provenance = add_provenance(
                provenance,
                source="unknown",
                confidence=0.0,
                notes="Placeholder ATC code requiring enrichment in Wave 3",
            )
        else:
            # Legacy ATC code from original JSON
            provenance = add_provenance(
                provenance,
                source="legacy",
                confidence=0.9,
                notes="Imported from original drugs.json with existing ATC classification",
            )

        # Add source references if available
        if drug.get("kegg_id"):
            provenance = add_provenance(
                provenance,
                source="kegg",
                url=f"https://www.kegg.jp/entry/{drug['kegg_id']}",
                confidence=0.95,
            )

        if drug.get("chembl_id"):
            provenance = add_provenance(
                provenance,
                source="chembl",
                url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{drug['chembl_id']}/",
                confidence=0.95,
            )

        if drug.get("pubchem_cid"):
            provenance = add_provenance(
                provenance,
                source="pubchem",
                url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{drug['pubchem_cid']}/",
                confidence=0.95,
            )

        return provenance

    async def update_drug_provenance(
        self, drug_id: str, provenance: Provenance
    ) -> bool:
        """
        Update provenance for a single drug.

        Args:
            drug_id: Drug ID
            provenance: Provenance object

        Returns:
            True if successful
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would update provenance for {drug_id}")
            return True

        query = """
            UPDATE drugs
            SET provenance = $1::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
        """

        try:
            if not self.db:
                logger.error("Database connection not initialized")
                return False
            await self.db.execute(query, [provenance.model_dump(), drug_id])
            return True
        except Exception as e:
            logger.error(f"Failed to update provenance for {drug_id}: {e}")
            return False

    async def migrate_batch(self, drugs: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Migrate provenance for a batch of drugs.

        Args:
            drugs: List of drug records

        Returns:
            Dict with success/failure counts
        """
        success_count = 0
        failure_count = 0

        for drug in drugs:
            drug_id = drug["id"]
            provenance = self.build_provenance(drug)

            if await self.update_drug_provenance(drug_id, provenance):
                success_count += 1

                # Update stats
                atc_code = drug.get("atc_code", "")
                if drug_id in CURATED_DRUG_IDS:
                    self.stats["curated_count"] += 1
                elif self.is_placeholder_code(atc_code):
                    self.stats["needs_enrichment_count"] += 1
                else:
                    self.stats["legacy_atc_count"] += 1
            else:
                failure_count += 1

        return {
            "success": success_count,
            "failure": failure_count,
        }

    async def run(self) -> bool:
        """
        Run the provenance migration.

        Returns:
            True if successful, False otherwise
        """
        start_time = datetime.now()
        logger.info(f"Starting provenance migration at {start_time}")

        try:
            # Initialize
            await self.init()

            # Fetch drugs without provenance
            drugs = await self.fetch_drugs_without_provenance()
            self.stats["total_drugs"] = len(drugs)

            if not drugs:
                logger.info(
                    "No drugs need provenance migration - all drugs already have provenance"
                )
                return True

            logger.info(f"Found {len(drugs)} drugs needing provenance migration")

            # Process in batches
            total_success = 0
            total_failure = 0

            for i in range(0, len(drugs), self.batch_size):
                batch = drugs[i : i + self.batch_size]
                logger.info(
                    f"Processing batch {i // self.batch_size + 1}: {len(batch)} drugs"
                )

                result = await self.migrate_batch(batch)
                total_success += result["success"]
                total_failure += result["failure"]

                logger.info(
                    f"Batch complete: {result['success']} success, "
                    f"{result['failure']} failures"
                )

            self.stats["drugs_with_provenance"] = total_success
            self.stats["errors"] = total_failure

            # Print summary
            self.print_summary()

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"Migration completed in {duration:.2f} seconds")

            return total_failure == 0

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return False

        finally:
            await self.close()

    def print_summary(self) -> None:
        """Print migration summary."""
        print("\n" + "=" * 60)
        print("PROVENANCE MIGRATION SUMMARY")
        print("=" * 60)
        print(f"Mode: {'DRY-RUN' if self.dry_run else 'LIVE'}")
        print(f"Total drugs processed: {self.stats['total_drugs']}")
        print(f"Drugs with provenance: {self.stats['drugs_with_provenance']}")
        print(f"  - Curated drugs: {self.stats['curated_count']}")
        print(f"  - Legacy ATC codes: {self.stats['legacy_atc_count']}")
        print(f"  - Needs enrichment: {self.stats['needs_enrichment_count']}")
        print(f"Errors: {self.stats['errors']}")
        print("=" * 60 + "\n")


async def main() -> int:
    """Main entry point."""
    parser = ArgumentParser(description="Migrate provenance data")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of records per batch (default: 500)",
    )

    args = parser.parse_args()

    migrator = ProvenanceMigrator(dry_run=args.dry_run, batch_size=args.batch_size)
    success = await migrator.run()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
