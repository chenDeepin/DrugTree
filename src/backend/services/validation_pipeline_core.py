"""Core validation pipeline implementation."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..models.audit import AuditAction, AuditActor, AuditLog
from .validation_models import (
    ValidationReport,
    ValidationResult,
    ValidationSeverity,
    ValidationType,
)

logger = logging.getLogger(__name__)

class ValidationPipeline:
    """
    End-to-end validation pipeline for drug data.

    Features:
    - ATC coverage validation (≥85%)
    - Provenance integrity checks
    - Data consistency validation
    - Alerting on critical issues
    - Health check endpoint support
    """

    # Thresholds
    ATC_COVERAGE_THRESHOLD = 85.0  # Minimum ATC coverage percentage
    PROVENANCE_COVERAGE_THRESHOLD = 100.0  # All drugs should have provenance
    DUPLICATE_THRESHOLD = 0  # Zero tolerance for duplicates

    def __init__(
        self,
        reports_path: Optional[Path] = None,
        alert_handlers: Optional[List[Callable]] = None,
    ):
        """
        Initialize validation pipeline.

        Args:
            reports_path: Path to save validation reports
            alert_handlers: List of async functions to call on alerts
        """
        self.reports_path = reports_path or Path("data/reports")
        self.reports_path.mkdir(parents=True, exist_ok=True)
        self.alert_handlers = alert_handlers or []

        # Latest report for health endpoint
        self._latest_report: Optional[ValidationReport] = None

    async def run_validation(
        self,
        drugs: List[Dict[str, Any]],
        provenance_records: Optional[List[Dict[str, Any]]] = None,
        sync_job_id: Optional[str] = None,
    ) -> ValidationReport:
        """
        Run full validation pipeline on drug data.

        Args:
            drugs: List of drug dictionaries to validate
            provenance_records: List of provenance records
            sync_job_id: ID of the sync job that triggered validation

        Returns:
            ValidationReport with all validation results
        """
        logger.info(f"Starting validation pipeline for {len(drugs)} drugs")

        report = ValidationReport(sync_job_id=sync_job_id)
        report.drug_count = len(drugs)

        # Run all validations
        await self._validate_atc_coverage(drugs, report)
        await self._validate_provenance_integrity(drugs, provenance_records, report)
        await self._validate_data_consistency(drugs, report)
        await self._validate_duplicates(drugs, report)
        await self._validate_schema_compliance(drugs, report)
        await self._validate_relationships(drugs, report)
        await self._validate_phase_distribution(drugs, report)
        await self._validate_structures(drugs, report)

        # Store metrics
        self._latest_report = report

        # Save report
        report_path = self.reports_path / f"validation_{report.report_id}.json"
        report.save(report_path)

        # Also save as "latest" for easy access
        latest_path = self.reports_path / "validation_latest.json"
        report.save(latest_path)

        # Trigger alerts if needed
        if report.alerts_triggered:
            await self._trigger_alerts(report)

        logger.info(
            f"Validation complete: {report.overall_status} "
            f"({report.passed_checks}/{report.total_checks} checks passed)"
        )

        return report

    async def _validate_atc_coverage(
        self,
        drugs: List[Dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        """Validate ATC code coverage."""
        if not drugs:
            result = ValidationResult(
                validation_type=ValidationType.ATC_COVERAGE,
                severity=ValidationSeverity.ERROR,
                passed=False,
                message="No drugs to validate",
            )
            report.add_result(result)
            return

        # Count drugs with valid ATC codes
        valid_atc_count = 0
        invalid_drugs = []

        for drug in drugs:
            atc_code = drug.get("atc_code")
            atc_category = drug.get("atc_category")

            # Check if ATC code is valid (not placeholder)
            if atc_code and not atc_code.startswith("XX"):
                valid_atc_count += 1
            else:
                invalid_drugs.append(drug.get("id", "unknown"))

        coverage = (valid_atc_count / len(drugs)) * 100
        report.atc_coverage_percent = coverage

        passed = coverage >= self.ATC_COVERAGE_THRESHOLD
        severity = (
            ValidationSeverity.INFO
            if passed
            else (
                ValidationSeverity.CRITICAL
                if coverage < 70
                else ValidationSeverity.ERROR
            )
        )

        result = ValidationResult(
            validation_type=ValidationType.ATC_COVERAGE,
            severity=severity,
            passed=passed,
            message=f"ATC coverage: {coverage:.1f}% (threshold: {self.ATC_COVERAGE_THRESHOLD}%)",
            details={
                "valid_count": valid_atc_count,
                "total_count": len(drugs),
                "coverage_percent": round(coverage, 2),
                "threshold": self.ATC_COVERAGE_THRESHOLD,
            },
            affected_count=len(invalid_drugs),
            affected_items=invalid_drugs,
        )

        report.add_result(result)

        if not passed:
            report.alerts_triggered.append("ATC_COVERAGE_LOW")

    async def _validate_provenance_integrity(
        self,
        drugs: List[Dict[str, Any]],
        provenance_records: Optional[List[Dict[str, Any]]],
        report: ValidationReport,
    ) -> None:
        """Validate provenance tracking integrity."""
        if not drugs:
            return

        # If no provenance records provided, check drug metadata
        if not provenance_records:
            # Check if drugs have provenance metadata
            drugs_with_provenance = sum(
                1
                for d in drugs
                if d.get("source")
                or d.get("provenance_timestamp")
                or d.get("data_sources")
            )
            coverage = (drugs_with_provenance / len(drugs)) * 100
        else:
            # Match provenance records to drugs
            provenance_drug_ids = {p.get("drug_id") for p in provenance_records}
            drugs_with_provenance = sum(
                1 for d in drugs if d.get("id") in provenance_drug_ids
            )
            coverage = (drugs_with_provenance / len(drugs)) * 100

        report.provenance_coverage_percent = coverage

        passed = coverage >= self.PROVENANCE_COVERAGE_THRESHOLD
        severity = ValidationSeverity.WARNING if not passed else ValidationSeverity.INFO

        result = ValidationResult(
            validation_type=ValidationType.PROVENANCE_INTEGRITY,
            severity=severity,
            passed=passed,
            message=f"Provenance coverage: {coverage:.1f}%",
            details={
                "drugs_with_provenance": drugs_with_provenance,
                "total_drugs": len(drugs),
                "coverage_percent": round(coverage, 2),
            },
        )

        report.add_result(result)

        if not passed:
            report.alerts_triggered.append("PROVENANCE_INCOMPLETE")

    async def _validate_data_consistency(
        self,
        drugs: List[Dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        """Validate data consistency across fields."""
        inconsistencies = []

        for drug in drugs:
            # Check phase vs year_approved consistency
            phase = drug.get("phase")
            year = drug.get("year_approved")

            if phase == "IV" and not year:
                inconsistencies.append(
                    f"{drug.get('id')}: Phase IV drug missing year_approved"
                )

            # Check molecular weight range
            mw = drug.get("molecular_weight")
            if mw and (mw < 50 or mw > 2000):
                inconsistencies.append(
                    f"{drug.get('id')}: Suspicious molecular weight: {mw}"
                )

            # Check ATC code/category consistency
            atc_code = drug.get("atc_code", "")
            atc_category = drug.get("atc_category", "")
            if atc_code and atc_category and not atc_code.startswith(atc_category):
                inconsistencies.append(
                    f"{drug.get('id')}: ATC code {atc_code} doesn't match category {atc_category}"
                )

        passed = len(inconsistencies) == 0
        severity = (
            ValidationSeverity.WARNING if inconsistencies else ValidationSeverity.INFO
        )

        result = ValidationResult(
            validation_type=ValidationType.DATA_CONSISTENCY,
            severity=severity,
            passed=passed,
            message=f"Found {len(inconsistencies)} data inconsistencies",
            details={"inconsistency_count": len(inconsistencies)},
            affected_count=len(inconsistencies),
            affected_items=inconsistencies[:20],  # Limit for report
        )

        report.add_result(result)

    async def _validate_duplicates(
        self,
        drugs: List[Dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        """Detect duplicate drugs by SMILES or InChIKey."""
        smiles_map: Dict[str, List[str]] = {}
        inchikey_map: Dict[str, List[str]] = {}

        for drug in drugs:
            drug_id = drug.get("id", "unknown")
            smiles = drug.get("smiles")
            inchikey = drug.get("inchikey")

            if smiles:
                # Normalize SMILES (basic normalization)
                normalized = smiles.strip()
                if normalized not in smiles_map:
                    smiles_map[normalized] = []
                smiles_map[normalized].append(drug_id)

            if inchikey:
                if inchikey not in inchikey_map:
                    inchikey_map[inchikey] = []
                inchikey_map[inchikey].append(drug_id)

        # Find duplicates
        duplicates = []
        for smiles, ids in smiles_map.items():
            if len(ids) > 1:
                duplicates.append(f"SMILES duplicate: {', '.join(ids)}")

        for inchikey, ids in inchikey_map.items():
            if len(ids) > 1:
                duplicates.append(f"InChIKey duplicate ({inchikey}): {', '.join(ids)}")

        passed = len(duplicates) <= self.DUPLICATE_THRESHOLD
        severity = ValidationSeverity.ERROR if duplicates else ValidationSeverity.INFO

        result = ValidationResult(
            validation_type=ValidationType.DUPLICATE_DETECTION,
            severity=severity,
            passed=passed,
            message=f"Found {len(duplicates)} potential duplicates",
            details={"duplicate_count": len(duplicates)},
            affected_count=len(duplicates),
            affected_items=duplicates,
        )

        report.add_result(result)

        if not passed:
            report.alerts_triggered.append("DUPLICATES_DETECTED")

    async def _validate_schema_compliance(
        self,
        drugs: List[Dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        """Validate drugs comply with schema."""
        required_fields = ["id", "name", "smiles", "atc_code", "atc_category"]
        violations = []

        for drug in drugs:
            missing = [f for f in required_fields if not drug.get(f)]
            if missing:
                violations.append(
                    f"{drug.get('id', 'unknown')}: Missing {', '.join(missing)}"
                )

        passed = len(violations) == 0
        severity = ValidationSeverity.ERROR if violations else ValidationSeverity.INFO

        result = ValidationResult(
            validation_type=ValidationType.SCHEMA_COMPLIANCE,
            severity=severity,
            passed=passed,
            message=f"Found {len(violations)} schema violations",
            details={"violation_count": len(violations)},
            affected_count=len(violations),
            affected_items=violations,
        )

        report.add_result(result)

    async def _validate_relationships(
        self,
        drugs: List[Dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        """Validate parent/successor relationships."""
        drug_ids = {d.get("id") for d in drugs}
        broken_relationships = []

        for drug in drugs:
            # Check parent_drugs references
            parents = drug.get("parent_drugs", [])
            for parent_id in parents:
                if parent_id not in drug_ids:
                    broken_relationships.append(
                        f"{drug.get('id')}: Missing parent_drugs reference to {parent_id}"
                    )

        passed = len(broken_relationships) == 0
        severity = (
            ValidationSeverity.WARNING
            if broken_relationships
            else ValidationSeverity.INFO
        )

        result = ValidationResult(
            validation_type=ValidationType.RELATIONSHIP_INTEGRITY,
            severity=severity,
            passed=passed,
            message=f"Found {len(broken_relationships)} broken relationships",
            details={"broken_count": len(broken_relationships)},
            affected_count=len(broken_relationships),
            affected_items=broken_relationships,
        )

        report.add_result(result)

    async def _validate_phase_distribution(
        self,
        drugs: List[Dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        """Validate phase distribution is reasonable."""
        phase_counts: Dict[str, int] = {}

        for drug in drugs:
            phase = drug.get("phase", "Unknown")
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

        total = len(drugs)
        phase_iv_percent = (phase_counts.get("IV", 0) / total * 100) if total else 0

        # For approved drugs database, expect most to be Phase IV
        # But allow flexibility for different datasets
        passed = True  # Informational check
        severity = ValidationSeverity.INFO

        result = ValidationResult(
            validation_type=ValidationType.PHASE_DISTRIBUTION,
            severity=severity,
            passed=passed,
            message=f"Phase distribution: {dict(phase_counts)}",
            details={
                "phase_counts": phase_counts,
                "phase_iv_percent": round(phase_iv_percent, 2),
            },
        )

        report.add_result(result)

    async def _validate_structures(
        self,
        drugs: List[Dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        """Validate molecular structures (SMILES validity)."""
        # Basic SMILES validation (check for common issues)
        invalid_structures = []

        for drug in drugs:
            smiles = drug.get("smiles", "")

            # Check for obvious issues
            issues = []
            if not smiles:
                issues.append("Empty SMILES")
            elif len(smiles) < 5:
                issues.append("SMILES too short")
            elif smiles.count("(") != smiles.count(")"):
                issues.append("Unbalanced parentheses")
            elif smiles.count("[") != smiles.count("]"):
                issues.append("Unbalanced brackets")

            if issues:
                invalid_structures.append(f"{drug.get('id')}: {', '.join(issues)}")

        valid_count = len(drugs) - len(invalid_structures)
        coverage = (valid_count / len(drugs) * 100) if drugs else 100
        report.structure_validity_percent = coverage

        passed = len(invalid_structures) == 0
        severity = (
            ValidationSeverity.WARNING
            if invalid_structures
            else ValidationSeverity.INFO
        )

        result = ValidationResult(
            validation_type=ValidationType.STRUCTURE_VALIDITY,
            severity=severity,
            passed=passed,
            message=f"Structure validity: {coverage:.1f}%",
            details={
                "valid_count": valid_count,
                "invalid_count": len(invalid_structures),
                "validity_percent": round(coverage, 2),
            },
            affected_count=len(invalid_structures),
            affected_items=invalid_structures,
        )

        report.add_result(result)

    async def _trigger_alerts(self, report: ValidationReport) -> None:
        """Trigger alert handlers for validation failures."""
        for handler in self.alert_handlers:
            try:
                await handler(report)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")

        logger.warning(f"Alerts triggered: {report.alerts_triggered}")

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get current data quality health status.

        Used by /api/health/data-quality endpoint.

        Returns:
            Dict with health metrics
        """
        if not self._latest_report:
            return {
                "status": "unknown",
                "message": "No validation has been run yet",
                "last_validation": None,
            }

        report = self._latest_report

        return {
            "status": report.overall_status.lower(),
            "last_validation": report.timestamp.isoformat(),
            "atc_coverage": round(report.atc_coverage_percent, 2),
            "provenance_coverage": round(report.provenance_coverage_percent, 2),
            "structure_validity": round(report.structure_validity_percent, 2),
            "total_drugs": report.drug_count,
            "validation_summary": {
                "total_checks": report.total_checks,
                "passed": report.passed_checks,
                "failed": report.failed_checks,
                "critical_failures": report.critical_failures,
            },
            "alerts": report.alerts_triggered,
        }

    async def run_quick_validation(
        self,
        drugs: List[Dict[str, Any]],
    ) -> bool:
        """
        Run quick validation (ATC coverage only).

        Args:
            drugs: List of drugs to validate

        Returns:
            True if validation passes
        """
        report = ValidationReport()
        await self._validate_atc_coverage(drugs, report)

        return report.overall_status == "PASS"
