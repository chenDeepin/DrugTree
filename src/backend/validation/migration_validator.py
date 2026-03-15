"""
Migration Validation Tool (Task 11)

Compares JSON source data with PostgreSQL data after migration.
Generates detailed validation report without modifying any data.

DO NOT auto-fix discrepancies (report only)
DO NOT modify data during validation
"""

import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

# Add parent directory to path for imports
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import DatabaseConnection, get_db
from validation.validators import calculate_coverage, validate_atc_code


@dataclass
class FieldDiscrepancy:
    """Represents a field-level discrepancy between JSON and PostgreSQL"""

    drug_id: str
    drug_name: str
    field_name: str
    json_value: Any
    postgres_value: Any
    discrepancy_type: str  # 'type_mismatch', 'value_mismatch', 'missing_in_json', 'missing_in_postgres'


@dataclass
class MissingDrug:
    """Represents a drug present in JSON but missing from PostgreSQL"""

    drug_id: str
    drug_name: str
    reason: str  # 'not_migrated', `migration_failed`, `validation_error`


@dataclass
class MigrationReport:
    """Complete migration validation report"""

    generated_at: str
    source_file: str
    source_count: int
    postgres_count: int
    coverage_percentage: float

    # Discrepancies
    missing_drugs: List[Dict[str, Any]] = field(default_factory=list)
    field_discrepancies: List[Dict[str, Any]] = field(default_factory=list)

    # Statistics
    total_discrepancies: int = 0
    drugs_with_discrepancies: int = 0
    critical_discrepancies: int = 0  # Fields required by frontend

    # Coverage metrics
    atc_coverage: float = 0.0
    fields_coverage: Dict[str, float] = field(default_factory=dict)

    # Validation status
    migration_passed: bool = False
    warnings: List[str] = field(default_factory=list)


class MigrationValidator:
    """Validates JSON → PostgreSQL migration integrity"""

    # Fields required by frontend (from frontend/js/app.js DrugTreeApp)
    FRONTEND_REQUIRED_FIELDS = [
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
    ]

    # Fields that may have different representations
    TYPE_FLEXIBLE_FIELDS = ["targets", "synonyms"]  # Can be string or list

    def __init__(self, json_path: str, db: Optional[DatabaseConnection] = None):
        """
        Initialize validator.

        Args:
            json_path: Path to source JSON file
            db: Database connection (optional, will create if None)
        """
        self.json_path = Path(json_path)
        self.db = db
        self._owns_db = db is None

    async def _get_db(self) -> DatabaseConnection:
        """Get database connection, creating if needed"""
        if self.db is None:
            self.db = await get_db()
        return self.db

    async def _load_json_drugs(self) -> Dict[str, Dict]:
        """Load drugs from JSON file"""
        with open(self.json_path, "r") as f:
            data = json.load(f)

        drugs = data.get("drugs", [])
        return {drug["id"]: drug for drug in drugs if "id" in drug}

    async def _load_postgres_drugs(self) -> Dict[str, Dict]:
        """Load drugs from PostgreSQL"""
        db = await self._get_db()

        # Query all drugs from database
        query = """
        SELECT 
            id, name, smiles, inchikey, atc_code, atc_category,
            molecular_weight, phase, year_approved, generation,
            indication, targets, company, synonyms, class,
            parent_drugs, created_at, updated_at, source
        FROM drugs
        """

        rows = await db.fetch(query)

        # Convert database rows to dictionaries
        drugs = {}
        for row in rows:
            # Handle row as dict-like object
            if hasattr(row, "keys"):
                # asyncpg Record object
                drug_dict = dict(row)
            else:
                # Already a dict
                drug_dict = row

            drug_id = drug_dict.get("id")
            if drug_id:
                drugs[drug_id] = drug_dict

        return drugs

    def _compare_values(self, json_val: Any, postgres_val: Any, field: str) -> bool:
        """
        Compare values considering type flexibility

        Args:
            json_val: Value from JSON
            postgres_val: Value from PostgreSQL
            field: Field name

        Returns:
            True if values are considered equal
        """
        # Handle None/null
        if json_val is None and postgres_val is None:
            return True
        if json_val is None or postgres_val is None:
            return False

        # Handle type flexible fields (lists/arrays)
        if field in self.TYPE_FLEXIBLE_FIELDS:
            # Convert both to lists for comparison
            json_list = (
                json_val
                if isinstance(json_val, list)
                else [json_val]
                if json_val
                else []
            )
            postgres_list = (
                postgres_val
                if isinstance(postgres_val, list)
                else [postgres_val]
                if postgres_val
                else []
            )
            return set(json_list) == set(postgres_list)

        # Direct comparison for all other fields
        return json_val == postgres_val

    async def _compare_drug(
        self, drug_id: str, json_drug: Dict, postgres_drug: Dict
    ) -> List[FieldDiscrepancy]:
        """
        Compare a single drug between JSON and PostgreSQL

        Args:
            drug_id: Drug ID
            json_drug: Drug data from JSON
            postgres_drug: Drug data from PostgreSQL

        Returns:
            List of field discrepancies
        """
        discrepancies = []

        # Check all fields
        all_fields = set(json_drug.keys()) | set(postgres_drug.keys())

        for field in all_fields:
            json_val = json_drug.get(field)
            postgres_val = postgres_drug.get(field)

            # Skip internal fields
            if field in ["created_at", "updated_at", "source"]:
                continue

            if not self._compare_values(json_val, postgres_val, field):
                # Determine discrepancy type
                if json_val is None and postgres_val is not None:
                    disc_type = "missing_in_json"
                elif json_val is not None and postgres_val is None:
                    disc_type = "missing_in_postgres"
                elif type(json_val) != type(postgres_val):
                    disc_type = "type_mismatch"
                else:
                    disc_type = "value_mismatch"

                discrepancies.append(
                    FieldDiscrepancy(
                        drug_id=drug_id,
                        drug_name=json_drug.get("name", ""),
                        field_name=field,
                        json_value=json_val,
                        postgres_value=postgres_val,
                        discrepancy_type=disc_type,
                    )
                )

        return discrepancies

    async def validate(self) -> MigrationReport:
        """
        Run migration validation

        Returns:
            MigrationReport with validation results
        """
        print("Starting migration validation...")
        print(f"Loading drugs from: {self.json_path}")

        # Load data
        json_drugs = await self._load_json_drugs()
        postgres_drugs = await self._load_postgres_drugs()

        print(f"JSON drugs: {len(json_drugs)}")
        print(f"PostgreSQL drugs: {len(postgres_drugs)}")

        # Initialize report
        report = MigrationReport(
            generated_at=datetime.now().isoformat(),
            source_file=str(self.json_path),
            source_count=len(json_drugs),
            postgres_count=len(postgres_drugs),
            coverage_percentage=(
                len(postgres_drugs) / len(json_drugs) * 100 if json_drugs else 0
            ),
        )

        # Find missing drugs
        json_ids = set(json_drugs.keys())
        postgres_ids = set(postgres_drugs.keys())

        for drug_id in json_ids - postgres_ids:
            drug = json_drugs[drug_id]
            report.missing_drugs.append(
                {
                    "drug_id": drug_id,
                    "drug_name": drug.get("name", ""),
                    "reason": "not_migrated",
                }
            )

        # Find field discrepancies
        drugs_with_discrepancies = set()

        for drug_id in json_ids & postgres_ids:
            json_drug = json_drugs[drug_id]
            postgres_drug = postgres_drugs[drug_id]

            discrepancies = await self._compare_drug(drug_id, json_drug, postgres_drug)

            if discrepancies:
                drugs_with_discrepancies.add(drug_id)
                for disc in discrepancies:
                    report.field_discrepancies.append(asdict(disc))

        # Calculate statistics
        report.total_discrepancies = len(report.field_discrepancies)
        report.drugs_with_discrepancies = len(drugs_with_discrepancies)

        # Count critical discrepancies (frontend-required fields)
        critical_fields_set = set(self.FRONTEND_REQUIRED_FIELDS)
        for disc in report.field_discrepancies:
            if disc["field_name"] in critical_fields_set:
                report.critical_discrepancies += 1

        # Calculate field coverage
        report.fields_coverage = {}
        for field in self.FRONTEND_REQUIRED_FIELDS:
            count = 0
            for drug_id in json_ids & postgres_ids:
                json_val = json_drugs[drug_id].get(field)
                postgres_val = postgres_drugs[drug_id].get(field)
                if json_val is not None and postgres_val is not None:
                    count += 1
            coverage = (
                (count / len(json_ids & postgres_ids) * 100)
                if (json_ids & postgres_ids)
                else 0
            )
            report.fields_coverage[field] = round(coverage, 2)

        # Calculate ATC coverage from PostgreSQL data
        postgres_drug_list = list(postgres_drugs.values())
        atc_stats = calculate_coverage(postgres_drug_list)
        report.atc_coverage = atc_stats["coverage_percentage"]

        # Determine if migration passed
        report.migration_passed = self._evaluate_migration(report)

        # Add warnings
        self._add_warnings(report)

        return report

    def _evaluate_migration(self, report: MigrationReport) -> bool:
        """
        Determine if migration passed validation.

        Pass criteria:
        - Coverage ≥ 95%
        - No critical discrepancies
        - ATC coverage ≥ 85% (from plan)
        """
        if report.coverage_percentage < 95.0:
            return False

        if report.critical_discrepancies > 0:
            return False

        if report.atc_coverage < 85.0:
            return False

        return True

    def _add_warnings(self, report: MigrationReport) -> None:
        """Add warnings to report"""
        if report.coverage_percentage < 95.0:
            report.warnings.append(
                f"Coverage below 95%: {report.coverage_percentage:.1f}%"
            )

        if report.atc_coverage < 85.0:
            report.warnings.append(
                f"ATC coverage below 85% target: {report.atc_coverage:.1f}%"
            )

        if report.critical_discrepancies > 0:
            report.warnings.append(
                f"Found {report.critical_discrepancies} critical field discrepancies"
            )

        if report.missing_drugs:
            report.warnings.append(f"{len(report.missing_drugs)} drugs not migrated")

    async def save_report(self, report: MigrationReport, output_path: str) -> None:
        """Save validation report to JSON file"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert report to dict
        report_dict = asdict(report)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Report saved to: {output_file}")


async def main():
    """Run migration validation"""
    # Paths (relative to project root)
    project_root = Path(__file__).parent.parent.parent.parent
    json_path = project_root / "data" / "drugs.json"
    output_path = (
        project_root / ".sisyphus" / "evidence" / "migration-validation-report.json"
    )

    # Create validator
    validator = MigrationValidator(str(json_path))

    try:
        # Run validation
        report = await validator.validate()

        # Save report
        await validator.save_report(report, str(output_path))

        # Print summary
        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)
        print(f"Source drugs:      {report.source_count}")
        print(f"PostgreSQL drugs:  {report.postgres_count}")
        print(f"Coverage:          {report.coverage_percentage:.1f}%")
        print(f"ATC coverage:      {report.atc_coverage:.1f}%")
        print(f"Missing drugs:     {len(report.missing_drugs)}")
        print(f"Discrepancies:     {report.total_discrepancies}")
        print(f"  - Critical:      {report.critical_discrepancies}")
        print(f"  - Drugs affected:{report.drugs_with_discrepancies}")
        print(f"\nMigration {'✓ PASSED' if report.migration_passed else '✗ FAILED'}")

        if report.warnings:
            print("\nWarnings:")
            for warning in report.warnings:
                print(f"  ⚠ {warning}")

        print("=" * 70)

    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Validation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
