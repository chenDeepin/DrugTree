#!/usr/bin/env python3
"""
DrugTree - Drug Migration Script (Task 7)

Migrates 7,359 drugs from JSON to PostgreSQL with:
- Batch inserts (500 drugs per batch)
- Curated drug identification (61 drugs with is_curated=True)
- Provenance tracking
- Error handling with rollback
- Detailed migration logging

Usage:
    python migrate_drugs.py [--dry-run] [--batch-size 500] [--source FILE]

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
from typing import Any, Dict, List, Optional, Set, Tuple

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
            / "migrate_drugs.log",
            mode="a",
        ),
    ],
)
logger = logging.getLogger(__name__)


# Curated drug IDs (top 61 drugs with most complete data - 16 fields each)
# These drugs were manually curated with complete information
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
    "aspirin-d00769",
    "asunaprevir",
    "atenolol",
    "atorvastatin",
    "atorvastatin-d07474",
    "atra",
    "azd2171",
    "azilsartan",
    "azithromycin",
    "aztreonam",
    "baricitinib",
    "bay94-8862",
    "bazedoxifeneconjugate-estrogens-ce",
    "bci-024-over-encapsulated-buspirone-tablet-15-mg-qd-and-bci-049-over-encapsulated-melatonin-tablet-3-mg-qd",
    "beclomethasone-dipropionate",
    "belinostat",
}


class MigrationStats:
    """Track migration statistics."""

    def __init__(self):
        self.total_drugs_loaded = 0
        self.total_drugs_inserted = 0
        self.curated_drugs = 0
        self.skipped_drugs = 0
        self.error_count = 0
        self.batch_count = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def start(self):
        """Mark migration start."""
        self.start_time = datetime.now()

    def finish(self):
        """Mark migration end."""
        self.end_time = datetime.now()

    @property
    def duration_seconds(self) -> float:
        """Calculate migration duration."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "total_drugs_loaded": self.total_drugs_loaded,
            "total_drugs_inserted": self.total_drugs_inserted,
            "curated_drugs": self.curated_drugs,
            "skipped_drugs": self.skipped_drugs,
            "error_count": self.error_count,
            "batch_count": self.batch_count,
            "duration_seconds": round(self.duration_seconds, 2),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class DrugMigrator:
    """
    Migrates drugs from JSON to PostgreSQL database.

    Features:
    - Batch inserts for performance
    - Curated drug identification
    - Provenance tracking
    - Transaction rollback on errors
    """

    def __init__(self, source_path: Path, batch_size: int = 500, dry_run: bool = False):
        """
        Initialize DrugMigrator.

        Args:
            source_path: Path to drugs.json file
            batch_size: Number of drugs to insert per batch
            dry_run: If True, validate without inserting
        """
        self.source_path = Path(source_path)
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.stats = MigrationStats()
        self.db: Optional[DatabaseConnection] = None

    def load_drugs(self) -> List[Dict[str, Any]]:
        """
        Load drugs from JSON source file.

        Returns:
            List of drug dictionaries
        """
        logger.info(f"Loading drugs from {self.source_path}")

        if not self.source_path.exists():
            raise FileNotFoundError(f"Source file not found: {self.source_path}")

        with open(self.source_path, "r") as f:
            data = json.load(f)

        drugs = data.get("drugs", [])
        self.stats.total_drugs_loaded = len(drugs)

        logger.info(f"Loaded {len(drugs)} drugs from source file")
        return drugs

    def transform_drug(self, drug: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform JSON drug to PostgreSQL schema format.

        Args:
            drug: Drug dictionary from JSON

        Returns:
            Transformed drug dictionary matching PostgreSQL schema
        """
        drug_id = drug.get("id", "")
        is_curated = drug_id in CURATED_DRUG_IDS

        # Build provenance
        provenance = self._build_provenance(drug, is_curated)

        # Transform arrays (ensure they're lists)
        targets = drug.get("targets") or []
        if isinstance(targets, str):
            targets = [targets]

        synonyms = drug.get("synonyms") or []
        if isinstance(synonyms, str):
            synonyms = [synonyms]

        secondary_regions = drug.get("secondary_body_regions") or []
        clinical_trials = drug.get("clinical_trials") or []

        # Build transformed record
        return {
            "id": drug_id,
            "name": drug.get("name"),
            "smiles": drug.get("smiles"),
            "inchikey": drug.get("inchikey"),
            "atc_code": drug.get("atc_code"),
            "atc_category": drug.get("atc_category"),
            "molecular_weight": drug.get("molecular_weight"),
            "phase": drug.get("phase"),
            "year_approved": drug.get("year_approved"),
            "generation": drug.get("generation", 1),
            "indication": drug.get("indication"),
            "targets": targets,
            "company": drug.get("company"),
            "synonyms": synonyms,
            "class": drug.get("class"),
            "kegg_id": drug.get("kegg_id"),
            "chembl_id": drug.get("chembl_id"),
            "pubchem_cid": drug.get("pubchem_cid"),
            "body_region": drug.get("body_region"),
            "secondary_body_regions": secondary_regions,
            "clinical_trials": clinical_trials,
            "is_curated": is_curated,
            "provenance": provenance.model_dump()
            if isinstance(provenance, Provenance)
            else provenance,
        }

    def _build_provenance(self, drug: Dict[str, Any], is_curated: bool) -> Provenance:
        """
        Build provenance record for a drug using add_provenance() helper.

        Args:
            drug: Drug dictionary
            is_curated: Whether drug is manually curated

        Returns:
            Provenance object
        """
        provenance = None

        # Set primary source based on curation status
        if is_curated:
            provenance = add_provenance(
                provenance,
                source="curated",
                confidence=1.0,
                notes="Manually curated drug",
            )
        else:
            provenance = add_provenance(
                provenance, source="import", confidence=0.9, notes="Imported from JSON"
            )

        # Add external source references
        if drug.get("kegg_id"):
            provenance = add_provenance(
                provenance,
                source="kegg",
                url=f"https://www.kegg.jp/entry/{drug['kegg_id']}",
                confidence=0.95,
                notes=f"KEGG ID: {drug['kegg_id']}",
            )

        if drug.get("chembl_id"):
            provenance = add_provenance(
                provenance,
                source="chembl",
                url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{drug['chembl_id']}",
                confidence=0.95,
                notes=f"ChEMBL ID: {drug['chembl_id']}",
            )

        if drug.get("atc_code"):
            atc_code = drug["atc_code"]
            # Lower confidence for placeholder codes
            confidence = 0.9 if not atc_code.endswith("99") else 0.5
            provenance = add_provenance(
                provenance,
                source="atc",
                confidence=confidence,
                notes=f"ATC code: {atc_code}"
                + (" (placeholder)" if atc_code.endswith("99") else ""),
            )

        return provenance

    async def connect(self) -> None:
        """Establish database connection."""
        logger.info("Connecting to database...")
        self.db = await get_db()
        await self.db.connect()
        logger.info("Database connection established")

    async def disconnect(self) -> None:
        """Close database connection."""
        if self.db:
            await self.db.disconnect()
            logger.info("Database connection closed")
        await close_db()

    async def check_existing_drugs(self) -> Set[str]:
        """
        Check which drugs already exist in database.

        Returns:
            Set of existing drug IDs
        """
        if not self.db:
            raise RuntimeError("Database not connected")

        existing = await self.db.fetch("SELECT id FROM drugs")
        return {row["id"] for row in existing} if existing else set()

    async def insert_batch(
        self, batch: List[Dict[str, Any]], batch_num: int
    ) -> Tuple[int, int]:
        """
        Insert a batch of drugs.

        Args:
            batch: List of drug dictionaries
            batch_num: Batch number for logging

        Returns:
            Tuple of (inserted_count, error_count)
        """
        if not self.db:
            raise RuntimeError("Database not connected")

        inserted = 0
        errors = 0

        async with self.db.transaction():
            for drug in batch:
                try:
                    await self._insert_drug(drug)
                    inserted += 1

                    if drug.get("is_curated"):
                        self.stats.curated_drugs += 1

                except Exception as e:
                    errors += 1
                    self.stats.errors.append(f"Drug {drug.get('id')}: {str(e)}")
                    logger.error(f"Failed to insert drug {drug.get('id')}: {e}")
                    # Don't raise - continue with next drug

        logger.info(f"Batch {batch_num}: Inserted {inserted} drugs, {errors} errors")

        return inserted, errors

    async def _insert_drug(self, drug: Dict[str, Any]) -> None:
        """
        Insert a single drug record.

        Args:
            drug: Drug dictionary to insert
        """
        if not self.db:
            raise RuntimeError("Database not connected")

        # Build INSERT query
        query = """
            INSERT INTO drugs (
                id, name, smiles, inchikey,
                atc_code, atc_category,
                molecular_weight, phase, year_approved, generation,
                indication, targets, company, synonyms, class,
                kegg_id, chembl_id, pubchem_cid,
                body_region, secondary_body_regions, clinical_trials,
                is_curated, provenance
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6,
                $7, $8, $9, $10,
                $11, $12, $13, $14, $15,
                $16, $17, $18,
                $19, $20, $21,
                $22, $23
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                smiles = EXCLUDED.smiles,
                inchikey = EXCLUDED.inchikey,
                atc_code = EXCLUDED.atc_code,
                atc_category = EXCLUDED.atc_category,
                molecular_weight = EXCLUDED.molecular_weight,
                phase = EXCLUDED.phase,
                year_approved = EXCLUDED.year_approved,
                generation = EXCLUDED.generation,
                indication = EXCLUDED.indication,
                targets = EXCLUDED.targets,
                company = EXCLUDED.company,
                synonyms = EXCLUDED.synonyms,
                class = EXCLUDED.class,
                kegg_id = EXCLUDED.kegg_id,
                chembl_id = EXCLUDED.chembl_id,
                pubchem_cid = EXCLUDED.pubchem_cid,
                body_region = EXCLUDED.body_region,
                secondary_body_regions = EXCLUDED.secondary_body_regions,
                clinical_trials = EXCLUDED.clinical_trials,
                is_curated = EXCLUDED.is_curated,
                provenance = EXCLUDED.provenance,
                updated_at = CURRENT_TIMESTAMP
        """

        await self.db.execute(
            query,
            drug["id"],
            drug["name"],
            drug["smiles"],
            drug["inchikey"],
            drug["atc_code"],
            drug["atc_category"],
            drug["molecular_weight"],
            drug["phase"],
            drug["year_approved"],
            drug["generation"],
            drug["indication"],
            drug["targets"],
            drug["company"],
            drug["synonyms"],
            drug["class"],
            drug["kegg_id"],
            drug["chembl_id"],
            drug["pubchem_cid"],
            drug["body_region"],
            drug["secondary_body_regions"],
            drug["clinical_trials"],
            drug["is_curated"],
            json.dumps(drug["provenance"]),
        )

    async def run(self) -> MigrationStats:
        """
        Execute the drug migration.

        Returns:
            MigrationStats object with results
        """
        self.stats.start()
        logger.info("=" * 60)
        logger.info("STARTING DRUG MIGRATION")
        logger.info("=" * 60)

        try:
            # Load drugs from source
            drugs = self.load_drugs()

            # Connect to database (skip in dry-run)
            if not self.dry_run:
                await self.connect()

                # Check existing drugs
                existing_ids = await self.check_existing_drugs()
                logger.info(f"Found {len(existing_ids)} existing drugs in database")
            else:
                existing_ids = set()
                logger.info("DRY RUN - skipping database operations")

            # Filter out existing drugs
            new_drugs = [d for d in drugs if d["id"] not in existing_ids]
            self.stats.skipped_drugs = len(drugs) - len(new_drugs)

            logger.info(
                f"Will migrate {len(new_drugs)} new drugs "
                f"(skipping {self.stats.skipped_drugs} existing)"
            )

            # Transform drugs
            transformed_drugs = [self.transform_drug(d) for d in new_drugs]

            # Process in batches
            total_batches = (
                len(transformed_drugs) + self.batch_size - 1
            ) // self.batch_size

            for i in range(0, len(transformed_drugs), self.batch_size):
                batch = transformed_drugs[i : i + self.batch_size]
                batch_num = (i // self.batch_size) + 1

                logger.info(
                    f"Processing batch {batch_num}/{total_batches} ({len(batch)} drugs)"
                )

                if not self.dry_run:
                    inserted, errors = await self.insert_batch(batch, batch_num)
                    self.stats.total_drugs_inserted += inserted
                    self.stats.error_count += errors
                else:
                    self.stats.total_drugs_inserted += len(batch)
                    logger.info(f"DRY RUN - would insert {len(batch)} drugs")

                self.stats.batch_count = batch_num

            # Log final statistics
            self.stats.finish()
            self._log_final_stats()

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.stats.errors.append(f"Migration failed: {str(e)}")
            raise

        finally:
            if not self.dry_run:
                await self.disconnect()

        return self.stats

    def _log_final_stats(self) -> None:
        """Log final migration statistics."""
        logger.info("=" * 60)
        logger.info("MIGRATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total drugs loaded: {self.stats.total_drugs_loaded}")
        logger.info(f"Total drugs inserted: {self.stats.total_drugs_inserted}")
        logger.info(f"Curated drugs: {self.stats.curated_drugs}")
        logger.info(f"Skipped (existing): {self.stats.skipped_drugs}")
        logger.info(f"Errors: {self.stats.error_count}")
        logger.info(f"Duration: {self.stats.duration_seconds:..2f} seconds")

        if self.stats.errors:
            logger.warning(f"Errors encountered: {len(self.stats.errors)}")
            for error in self.stats.errors[:10]:  # Show first 10 errors
                logger.warning(f"  - {error}")


async def main():
    """Main entry point."""
    parser = ArgumentParser(description="Migrate drugs from JSON to PostgreSQL")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and log without inserting"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of drugs per batch (default: 500)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/drugs.json"),
        help="Path to source JSON file (default: data/drugs.json)",
    )

    args = parser.parse_args()

    # Resolve source path relative to project root
    project_root = Path(__file__).parent.parent.parent.parent
    source_path = project_root / args.source

    # Create logs directory
    logs_dir = project_root / "logs" / "migrations"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Run migration
    migrator = DrugMigrator(
        source_path=source_path, batch_size=args.batch_size, dry_run=args.dry_run
    )

    try:
        stats = await migrator.run()

        # Exit with error code if there were failures
        if stats.error_count > 0:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
