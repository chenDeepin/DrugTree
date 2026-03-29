#!/usr/bin/env python3
"""
DrugTree - ATC Code Migration Script (Task 8)

Migrates ATC codes from drugs.json to normalized PostgreSQL tables:
- Extracts unique ATC codes from drugs
- Populates atc_codes table with hierarchical structure
- Creates drug_atc_mapping junction entries
- Preserves placeholder codes (99XX99 pattern)

Usage:
    python migrate_atc.py [--dry-run] [--batch-size 500]

Author: DrugTree Team
Date: 2026-03-15
"""

import asyncio
import json
import logging
import re
import sys
from argparse import ArgumentParser
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db.connection import DatabaseConnection, get_db, close_db

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
            / "migrate_atc.log",
            mode="a",
        ),
    ],
)
logger = logging.getLogger(__name__)


# ATC Classification Level 1 Names (WHO Standard)
ATC_LEVEL1_NAMES: Dict[str, str] = {
    "A": "Alimentary tract and metabolism",
    "B": "Blood and blood forming organs",
    "C": "Cardiovascular system",
    "D": "Dermatologicals",
    "G": "Genito-urinary system and sex hormones",
    "H": "Systemic hormonalonal preparations, excluding sex hormones and insulins",
    "J": "Antiinfectives for systemic use",
    "L": "Antineoplastic and immunomodulating agents",
    "M": "Musculo-skeletal system",
    "N": "Nervous system",
    "P": "Antiparasitic products, insecticides and repellents",
    "R": "Respiratory system",
    "S": "Sensory organs",
    "V": "Various",
}


class ATCCodeParser:
    """Parses ATC codes into hierarchical components."""

    # ATC code pattern: 1 letter + 2 digits + 2 letters + 2 digits
    # Examples: C10AA05, N04AA08, V09XX99 (placeholder)
    ATC_PATTERN = re.compile(r"^([A-V])(\d{2})([A-Z]{2})(\d{2})$")

    @classmethod
    def parse(cls, code: str) -> Optional[Dict[str, str]]:
        """
        Parse ATC code into components.

        Args:
            code: 7-character ATC code (e.g., "C10AA05")

        Returns:
            Dict with 'category', 'level2', 'level3', 'level4' or None if invalid
        """
        if not code or len(code) != 7:
            return None

        match = cls.ATC_PATTERN.match(code)
        if not match:
            logger.warning(f"Invalid ATC code format: {code}")
            return None

        return {
            "category": match.group(1),
            "level2": match.group(2),
            "level3": match.group(3),
            "level4": match.group(4),
        }

    @classmethod
    def is_placeholder(cls, code: str) -> bool:
        """
        Check if ATC code is a placeholder (contains 99 or XX).

        Placeholder pattern: V09XX99 (category V + 09XX99)
        """
        if not code or len(code) != 7:
            return False
        # Check for 99 in level4 (last 2 digits) and XX in level3
        return "99" in code[-2:] and "XX" in code[3:5]


class ATCMigrator:
    """Migrates ATC codes from JSON to PostgreSQL."""

    def __init__(self, dry_run: bool = False, batch_size: int = 500):
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.db: Optional[DatabaseConnection] = None

        # Statistics
        self.stats = {
            "total_drugs": 0,
            "unique_atc_codes": 0,
            "placeholder_codes": 0,
            "mapping_entries": 0,
            "errors": 0,
        }

        # Track unique ATC codes
        self.atc_codes: Dict[str, Dict[str, Any]] = {}
        self.drug_atc_mappings: List[Dict[str, Any]] = []

    async def init(self) -> None:
        """Initialize database connection."""
        self.db = await get_db()
        logger.info("Database connection initialized")

    async def close(self) -> None:
        """Close database connection."""
        if self.db:
            await close_db()
        logger.info("Database connection closed")

    def load_drugs(self) -> List[Dict[str, Any]]:
        """Load drugs from JSON file."""
        json_path = (
            Path(__file__).parent.parent.parent.parent.parent / "data" / "drugs.json"
        )

        logger.info(f"Loading drugs from {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        drugs = data.get("drugs", [])
        logger.info(f"Loaded {len(drugs)} drugs")
        return drugs

    def extract_atc_codes(self, drugs: List[Dict[str, Any]]) -> None:
        """
        Extract unique ATC codes from drugs.

        Builds:
        - self.atc_codes: Dict[code, code_data]
        - self.drug_atc_mappings: List of mapping records
        """
        logger.info("Extracting ATC codes from drugs...")

        placeholder_count = 0

        for drug in drugs:
            drug_id = drug.get("id")
            atc_code = drug.get("atc_code")
            atc_category = drug.get("atc_category")

            if not drug_id or not atc_code:
                continue

            # Parse ATC code
            parsed = ATCCodeParser.parse(atc_code)
            if not parsed:
                logger.warning(
                    f"Skipping invalid ATC code '{atc_code}' for drug {drug_id}"
                )
                self.stats["errors"] += 1
                continue

            # Check if placeholder
            is_placeholder = ATCCodeParser.is_placeholder(atc_code)
            if is_placeholder:
                placeholder_count += 1

            # Add to unique ATC codes dict
            if atc_code not in self.atc_codes:
                self.atc_codes[atc_code] = {
                    "code": atc_code,
                    "category": parsed["category"],
                    "level2": parsed["level2"],
                    "level3": parsed["level3"],
                    "level4": parsed["level4"],
                    "level1_name": ATC_LEVEL1_NAMES.get(parsed["category"], "Unknown"),
                    "level2_name": None,  # Would require full ATC lookup
                    "level3_name": None,
                    "level4_name": None,
                    "is_placeholder": is_placeholder,
                }

            # Create mapping entry
            self.drug_atc_mappings.append(
                {
                    "drug_id": drug_id,
                    "atc_code": atc_code,
                    "is_primary": True,  # All current codes are primary
                    "source": "legacy",  # From original JSON
                    "confidence": 1.0,
                }
            )

        self.stats["total_drugs"] = len(drugs)
        self.stats["unique_atc_codes"] = len(self.atc_codes)
        self.stats["placeholder_codes"] = placeholder_count
        self.stats["mapping_entries"] = len(self.drug_atc_mappings)

        logger.info(f"Extracted {self.stats['unique_atc_codes']} unique ATC codes")
        logger.info(f"Found {self.stats['placeholder_codes']} placeholder codes")
        logger.info(f"Created {self.stats['mapping_entries']} mapping entries")

    async def insert_atc_codes(self) -> int:
        """
        Insert unique ATC codes into atc_codes table.

        Returns:
            Number of codes inserted
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would insert ATC codes")
            return 0

        logger.info("Inserting ATC codes into database...")

        codes_list = list(self.atc_codes.values())
        inserted = 0

        # Insert in batches
        for i in range(0, len(codes_list), self.batch_size):
            batch = codes_list[i : i + self.batch_size]

            # Build INSERT query with ON CONFLICT
            values_sql = []
            params = []
            param_idx = 1

            for code_data in batch:
                values_sql.append(
                    f"(${param_idx}, ${param_idx + 1}, ${param_idx + 2}, "
                    f"${param_idx + 3}, ${param_idx + 4}, ${param_idx + 5}, "
                    f"${param_idx + 6}, ${param_idx + 7}, ${param_idx + 8}, "
                    f"${param_idx + 9})"
                )
                params.extend(
                    [
                        code_data["code"],
                        code_data["category"],
                        code_data["level2"],
                        code_data["level3"],
                        code_data["level4"],
                        code_data["level1_name"],
                        code_data["level2_name"],
                        code_data["level3_name"],
                        code_data["is_placeholder"],
                    ]
                )
                param_idx += 10

            query = f"""
                INSERT INTO atc_codes (
                    code, category, level2, level3, level4,
                    level1_name, level2_name, level3_name, is_placeholder
                ) VALUES {", ".join(values_sql)}
                ON CONFLICT (code) DO NOTHING
            """

            try:
                await self.db.execute(query, params)
                inserted += len(batch)
                logger.info(
                    f"Inserted batch {i // self.batch_size + 1}: "
                    f"{len(batch)} codes (total: {inserted})"
                )
            except Exception as e:
                logger.error(f"Failed to insert batch: {e}")
                self.stats["errors"] += len(batch)

        return inserted

    async def insert_mappings(self) -> int:
        """
        Insert drug-ATC mappings into drug_atc_mapping table.

        Returns:
            Number of mappings inserted
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would insert mappings")
            return 0

        logger.info("Inserting drug-ATC mappings into database...")

        inserted = 0

        # Insert in batches
        for i in range(0, len(self.drug_atc_mappings), self.batch_size):
            batch = self.drug_atc_mappings[i : i + self.batch_size]

            # Build INSERT query with ON CONFLICT
            values_sql = []
            params = []
            param_idx = 1

            for mapping in batch:
                values_sql.append(
                    f"(${param_idx}, ${param_idx + 1}, ${param_idx + 2}, "
                    f"${param_idx + 3}, ${param_idx + 4})"
                )
                params.extend(
                    [
                        mapping["drug_id"],
                        mapping["atc_code"],
                        mapping["is_primary"],
                        mapping["source"],
                        mapping["confidence"],
                    ]
                )
                param_idx += 5

            query = f"""
                INSERT INTO drug_atc_mapping (
                    drug_id, atc_code, is_primary, source, confidence
                ) VALUES {", ".join(values_sql)}
                ON CONFLICT (drug_id, atc_code) DO NOTHING
            """

            try:
                await self.db.execute(query, params)
                inserted += len(batch)
                logger.info(
                    f"Inserted mapping batch {i // self.batch_size + 1}: "
                    f"{len(batch)} entries (total: {inserted})"
                )
            except Exception as e:
                logger.error(f"Failed to insert mapping batch: {e}")
                self.stats["errors"] += len(batch)

        return inserted

    async def verify_migration(self) -> Dict[str, int]:
        """Verify migration by counting records."""
        logger.info("Verifying migration...")

        if not self.db:
            logger.error("Database connection not initialized")
            return {
                "atc_codes": 0,
                "placeholder_codes": 0,
                "mappings": 0,
                "drugs_with_atc": 0,
            }

        # Count ATC codes
        atc_count_result = await self.db.fetchrow(
            "SELECT COUNT(*) as count FROM atc_codes"
        )
        atc_count = atc_count_result["count"] if atc_count_result else 0

        # Count placeholder codes
        placeholder_result = await self.db.fetchrow(
            "SELECT COUNT(*) as count FROM atc_codes WHERE is_placeholder = TRUE"
        )
        placeholder_count = placeholder_result["count"] if placeholder_result else 0

        # Count mappings
        mapping_count_result = await self.db.fetchrow(
            "SELECT COUNT(*) as count FROM drug_atc_mapping"
        )
        mapping_count = mapping_count_result["count"] if mapping_count_result else 0

        # Count drugs with ATC codes
        drugs_with_atc_result = await self.db.fetchrow(
            "SELECT COUNT(DISTINCT drug_id) as count FROM drug_atc_mapping"
        )
        drugs_with_atc = drugs_with_atc_result["count"] if drugs_with_atc_result else 0

        verification = {
            "atc_codes": atc_count,
            "placeholder_codes": placeholder_count,
            "mappings": mapping_count,
            "drugs_with_atc": drugs_with_atc,
        }

        logger.info("Verification results:")
        logger.info(f"  ATC codes in table: {atc_count}")
        logger.info(f"  Placeholder codes: {placeholder_count}")
        logger.info(f"  Drug-ATC mappings: {mapping_count}")
        logger.info(f"  Drugs with ATC codes: {drugs_with_atc}")

        return verification

    def print_summary(self) -> None:
        """Print migration summary."""
        print("\n" + "=" * 60)
        print("ATC CODE MIGRATION SUMMARY")
        print("=" * 60)
        print(f"Mode: {'DRY-RUN' if self.dry_run else 'LIVE'}")
        print(f"Total drugs processed: {self.stats['total_drugs']}")
        print(f"Unique ATC codes: {self.stats['unique_atc_codes']}")
        print(f"Placeholder codes (99XX99): {self.stats['placeholder_codes']}")
        print(f"Drug-ATC mappings: {self.stats['mapping_entries']}")
        print(f"Errors: {self.stats['errors']}")
        print("=" * 60 + "\n")

    async def run(self) -> bool:
        """
        Run the complete ATC migration.

        Returns:
            True if successful, False otherwise
        """
        start_time = datetime.now()
        logger.info(f"Starting ATC migration at {start_time}")

        try:
            # Initialize
            await self.init()

            # Load drugs
            drugs = self.load_drugs()

            # Extract ATC codes
            self.extract_atc_codes(drugs)

            # Insert ATC codes
            await self.insert_atc_codes()

            # Insert mappings
            await self.insert_mappings()

            # Verify (only if not dry-run)
            if not self.dry_run:
                await self.verify_migration()

            # Print summary
            self.print_summary()

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"Migration completed in {duration:.2f} seconds")

            return self.stats["errors"] == 0

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return False

        finally:
            await self.close()


async def main() -> int:
    """Main entry point."""
    parser = ArgumentParser(description="Migrate ATC codes to PostgreSQL")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of records per batch insert (default: 500)",
    )

    args = parser.parse_args()

    migrator = ATCMigrator(dry_run=args.dry_run, batch_size=args.batch_size)
    success = await migrator.run()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
