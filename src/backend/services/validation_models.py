"""Validation result models for the validation pipeline service."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

class ValidationSeverity(str, Enum):
    """Severity of validation issues."""

    INFO = "info"  # Informational, no action needed
    WARNING = "warning"  # Potential issue, review recommended
    ERROR = "error"  # Issue detected, action required
    CRITICAL = "critical"  # Severe issue, immediate action required


class ValidationType(str, Enum):
    """Types of validation checks."""

    ATC_COVERAGE = "atc_coverage"
    PROVENANCE_INTEGRITY = "provenance_integrity"
    DATA_CONSISTENCY = "data_consistency"
    DUPLICATE_DETECTION = "duplicate_detection"
    SCHEMA_COMPLIANCE = "schema_compliance"
    RELATIONSHIP_INTEGRITY = "relationship_integrity"
    PHASE_DISTRIBUTION = "phase_distribution"
    STRUCTURE_VALIDITY = "structure_validity"


@dataclass
class ValidationResult:
    """Result of a single validation check."""

    validation_type: ValidationType
    severity: ValidationSeverity
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    affected_count: int = 0
    affected_items: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "validation_type": self.validation_type.value,
            "severity": self.severity.value,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
            "affected_count": self.affected_count,
            "affected_items": self.affected_items[:50],  # Limit items
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ValidationReport:
    """Complete validation report for a sync operation."""

    report_id: str = field(
        default_factory=lambda: (
            f"val_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        )
    )
    sync_job_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    results: List[ValidationResult] = field(default_factory=list)

    # Summary statistics
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    critical_failures: int = 0

    # Metrics
    drug_count: int = 0
    atc_coverage_percent: float = 0.0
    provenance_coverage_percent: float = 0.0
    structure_validity_percent: float = 0.0

    # Alert flags
    alerts_triggered: List[str] = field(default_factory=list)

    def add_result(self, result: ValidationResult) -> None:
        """Add a validation result to the report."""
        self.results.append(result)
        self.total_checks += 1

        if result.passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1
            if result.severity == ValidationSeverity.CRITICAL:
                self.critical_failures += 1

    @property
    def pass_rate(self) -> float:
        """Percentage of passed checks."""
        if self.total_checks == 0:
            return 100.0
        return (self.passed_checks / self.total_checks) * 100

    @property
    def overall_status(self) -> str:
        """Overall validation status."""
        if self.critical_failures > 0:
            return "CRITICAL"
        elif self.failed_checks > 0:
            return "WARNING"
        else:
            return "PASS"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "report_id": self.report_id,
            "sync_job_id": self.sync_job_id,
            "timestamp": self.timestamp.isoformat(),
            "overall_status": self.overall_status,
            "summary": {
                "total_checks": self.total_checks,
                "passed": self.passed_checks,
                "failed": self.failed_checks,
                "critical_failures": self.critical_failures,
                "pass_rate_percent": round(self.pass_rate, 2),
            },
            "metrics": {
                "drug_count": self.drug_count,
                "atc_coverage_percent": round(self.atc_coverage_percent, 2),
                "provenance_coverage_percent": round(
                    self.provenance_coverage_percent, 2
                ),
                "structure_validity_percent": round(self.structure_validity_percent, 2),
            },
            "alerts_triggered": self.alerts_triggered,
            "results": [r.to_dict() for r in self.results],
        }

    def save(self, path: Path) -> None:
        """Save report to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info(f"Validation report saved to {path}")
