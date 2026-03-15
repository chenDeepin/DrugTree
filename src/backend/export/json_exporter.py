"""
DrugTree - JSON Export Compatibility Layer

Exports PostgreSQL drug data back to JSON format for frontend compatibility.
Ensures backward compatibility with the existing frontend that expects
the data/drugs.json format.

Usage:
    python -m src.backend.export.json_exporter > drugs.json
    python -m src.backend.export.json_exporter --output drugs.json
    python -m src.backend.export.json_exporter --validate  # Compare with original
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db.connection import DatabaseConnection, get_db

logger = logging.getLogger(__name__)


class JSONExporter:
    """
    Exports PostgreSQL drug data to JSON format compatible with frontend.

    The exported JSON matches the exact structure of data/drugs.json:
    - Root object with "drugs" array
    - All fields preserved (including nulls)
    - Field ordering consistent with original
    - Arrays (targets, synonyms, clinical_trials) properly formatted
    """

    # Field order matching original drugs.json format
    FIELD_ORDER = [
        "id",
        "name",
        "smiles",
        "inchikey",
        "atc_code",
        "atc_category",
        "molecular_weight",
        "phase",
        "year_approved",
        "generation",
        "indication",
        "targets",
        "company",
        "synonyms",
        "class",
        "clinical_trials",
        "kegg_id",
        "body_region",
        "secondary_body_regions",
        "chembl_id",
    ]

    def __init__(self, db: Optional[DatabaseConnection] = None):
        """
        Initialize exporter.

        Args:
            db: Optional database connection (will create if not provided)
        """
        self.db = db
        self._own_db = db is None

    async def connect(self) -> None:
        """Establish database connection if needed"""
        if self.db is None:
            self.db = await get_db()

    async def disconnect(self) -> None:
        """Close database connection if we own it"""
        if self._own_db:
            from db.connection import close_db

            await close_db()
            self.db = None

    async def fetch_all_drugs(self) -> List[Dict[str, Any]]:
        """
        Fetch all drugs from PostgreSQL database.

        Returns:
            List of drug dictionaries with all fields
        """
        if not self.db:
            await self.connect()

        query = """
            SELECT id, name, smiles, inchikey, atc_code, atc_category,
                   molecular_weight, phase, year_approved, generation,
                   indication, targets, company, synonyms, class,
                   clinical_trials, kegg_id, body_region, secondary_body_regions,
                   chembl_id
            FROM drugs
            ORDER BY id
        """

        rows = await self.db.fetch(query)

        drugs = []
        for row in rows:
            # Convert asyncpg Record to dict
            drug = dict(row)
            drugs.append(drug)

        logger.info(f"Fetched {len(drugs)} drugs from database")
        return drugs

    def format_drug_for_export(self, db_drug: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a database drug record for JSON export.

        Ensures:
        - Only frontend-expected fields included
        - Field ordering consistent
        - Null values preserved
        - Arrays properly formatted (not null, but empty list if needed)

        Args:
            db_drug: Drug record from database

        Returns:
            Drug dictionary in export format
        """
        # Build drug with correct field order
        exported = {}

        for field in self.FIELD_ORDER:
            value = db_drug.get(field)

            # Handle array fields - convert null to empty array
            if field in (
                "targets",
                "synonyms",
                "clinical_trials",
                "secondary_body_regions",
            ):
                if value is None:
                    value = []
                elif isinstance(value, str):
                    # Handle case where array might be stored as string
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        value = []

            exported[field] = value

        return exported

    async def export_to_json(
        self, output_path: Optional[str] = None, pretty: bool = True
    ) -> Dict[str, Any]:
        """
        Export all drugs to JSON format.

        Args:
            output_path: Optional path to write JSON file
            pretty: Whether to format with indentation

        Returns:
            Exported data dictionary with "drugs" key
        """
        # Fetch all drugs from database
        db_drugs = await self.fetch_all_drugs()

        # Format for export
        exported_drugs = [self.format_drug_for_export(drug) for drug in db_drugs]

        # Build final structure
        export_data = {"drugs": exported_drugs}

        # Write to file if path provided
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                if pretty:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(export_data, f, ensure_ascii=False)

            logger.info(f"Exported {len(exported_drugs)} drugs to {output_path}")

        return export_data

    async def compare_with_original(
        self, original_path: str = "data/drugs.json"
    ) -> Dict[str, Any]:
        """
        Compare exported data with original JSON file.

        Args:
            original_path: Path to original drugs.json

        Returns:
            Comparison results dictionary
        """
        # Load original
        original_file = (
            Path(__file__).parent.parent.parent.parent.parent / original_path
        )
        with open(original_file, "r", encoding="utf-8") as f:
            original_data = json.load(f)
        original_drugs = {d["id"]: d for d in original_data.get("drugs", [])}

        # Export current
        export_data = await self.export_to_json()
        export_drugs = {d["id"]: d for d in export_data.get("drugs", [])}

        # Compare
        original_ids = set(original_drugs.keys())
        export_ids = set(export_drugs.keys())

        missing = original_ids - export_ids
        added = export_ids - original_ids
        common = original_ids & export_ids

        # Check field differences
        field_differences = {}
        for drug_id in common:
            orig = original_drugs[drug_id]
            exp = export_drugs[drug_id]

            diff_fields = []
            for field in self.FIELD_ORDER:
                orig_val = orig.get(field)
                exp_val = exp.get(field)

                # Handle array comparison
                if isinstance(orig_val, list) and isinstance(exp_val, list):
                    if set(orig_val) != set(exp_val):
                        diff_fields.append(field)
                elif orig_val != exp_val:
                    diff_fields.append(field)

            if diff_fields:
                field_differences[drug_id] = diff_fields

        return {
            "original_count": len(original_drugs),
            "exported_count": len(export_drugs),
            "missing_drugs": list(missing),
            "added_drugs": list(added),
            "drugs_with_differences": field_differences,
            "is_compatible": len(missing) == 0 and len(added) == 0,
        }


async def main():
    """Main entry point for CLI usage"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Export PostgreSQL drug data to JSON format"
    )
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    parser.add_argument(
        "--validate",
        "-v",
        action="store_true",
        help="Compare exported data with original drugs.json",
    )
    parser.add_argument(
        "--pretty",
        "-p",
        action="store_true",
        default=True,
        help="Pretty print JSON with indentation (default: True)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    exporter = JSONExporter()

    try:
        await exporter.connect()

        if args.validate:
            # Compare mode
            comparison = await exporter.compare_with_original()
            print(json.dumps(comparison, indent=2))

            if not comparison["is_compatible"]:
                logger.warning("Exported data differs from original!")
                sys.exit(1)
        else:
            # Export mode
            if args.output:
                await exporter.export_to_json(args.output, pretty=args.pretty)
                logger.info(f"Export complete: {args.output}")
            else:
                # Write to stdout
                export_data = await exporter.export_to_json(pretty=args.pretty)
                print(json.dumps(export_data, indent=2 if args.pretty else None))

    finally:
        await exporter.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
