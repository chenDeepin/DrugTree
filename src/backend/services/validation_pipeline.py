"""DrugTree - Validation Pipeline Service.

Compatibility wrapper for the validation models and core pipeline modules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .validation_models import (
    ValidationReport,
    ValidationResult,
    ValidationSeverity,
    ValidationType,
)
from .validation_pipeline_core import ValidationPipeline

_pipeline: Optional[ValidationPipeline] = None


def get_validation_pipeline() -> ValidationPipeline:
    """Get or create singleton validation pipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = ValidationPipeline()
    return _pipeline


async def run_validation(
    drugs: List[Dict[str, Any]],
    provenance_records: Optional[List[Dict[str, Any]]] = None,
    sync_job_id: Optional[str] = None,
) -> ValidationReport:
    """
    Convenience function to run validation using singleton pipeline.

    Args:
        drugs: List of drugs to validate
        provenance_records: List of provenance records
        sync_job_id: ID of sync job

    Returns:
        ValidationReport
    """
    return await get_validation_pipeline().run_validation(
        drugs=drugs,
        provenance_records=provenance_records,
        sync_job_id=sync_job_id,
    )
