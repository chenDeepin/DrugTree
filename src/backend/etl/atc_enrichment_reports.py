"""Report construction helpers for ATC enrichment."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

try:
    from .atc_enrichment_models import DrugEnrichmentOutcome
    from .atc_lookup_service import ATCOrchestrator, utcnow_iso
    from .atc_utils import is_placeholder_atc_code, is_specific_atc_code
except ImportError:  # pragma: no cover - direct script fallback
    from src.backend.etl.atc_enrichment_models import DrugEnrichmentOutcome
    from src.backend.etl.atc_lookup_service import ATCOrchestrator, utcnow_iso
    from src.backend.etl.atc_utils import is_placeholder_atc_code, is_specific_atc_code


def build_enrichment_report(
    *,
    drugs_file: Path,
    cache_dir: Path,
    max_network_concurrency: int,
    network_cache_hits: int,
    network_cache_misses: int,
    original_drugs: List[Dict[str, Any]],
    updated_drugs: List[Dict[str, Any]],
    processed_drugs: List[Dict[str, Any]],
    outcomes: List[DrugEnrichmentOutcome],
    unresolved: List[Dict[str, Any]],
    processed_count: int,
    dry_run: bool,
    placeholder_only: bool,
) -> Dict[str, Any]:
    input_placeholder_count = sum(
        1 for drug in processed_drugs if is_placeholder_atc_code(drug.get("atc_code"))
    )
    total_input_placeholder_count = sum(
        1 for drug in original_drugs if is_placeholder_atc_code(drug.get("atc_code"))
    )
    output_valid_count = sum(
        1 for drug in updated_drugs if is_specific_atc_code(drug.get("atc_code"))
    )
    source_counts = Counter(outcome.source for outcome in outcomes)
    method_counts = Counter(outcome.method for outcome in outcomes)
    external_id_recoveries = sum(
        1 for outcome in outcomes if outcome.external_ids_recovered
    )
    approved_drugs = [
        drug
        for drug in updated_drugs
        if drug.get("year_approved") is not None
        or str(drug.get("phase", "")).upper() == "IV"
    ]
    approved_with_specific_atc = sum(
        1 for drug in approved_drugs if is_specific_atc_code(drug.get("atc_code"))
    )

    return {
        "generated_at": utcnow_iso(),
        "drugs_file": str(drugs_file),
        "processed_count": processed_count,
        "total_drugs": len(updated_drugs),
        "dry_run": dry_run,
        "selection_mode": "placeholder_only" if placeholder_only else "full_dataset",
        "processed_input_placeholder_count": input_placeholder_count,
        "total_input_placeholder_count": total_input_placeholder_count,
        "resolved_specific_atc_count": sum(
            1 for outcome in outcomes if outcome.status == "resolved"
        ),
        "preserved_valid_count": sum(
            1 for outcome in outcomes if outcome.status == "preserved"
        ),
        "output_valid_specific_atc_count": output_valid_count,
        "output_placeholder_count": sum(
            1 for drug in updated_drugs if is_placeholder_atc_code(drug.get("atc_code"))
        ),
        "processed_unresolved_placeholder_count": len(unresolved),
        "approved_drug_count": len(approved_drugs),
        "approved_drug_specific_atc_count": approved_with_specific_atc,
        "approved_drug_specific_atc_coverage": round(
            (approved_with_specific_atc / len(approved_drugs) * 100)
            if approved_drugs
            else 0.0,
            2,
        ),
        "source_counts": dict(source_counts),
        "method_counts": dict(method_counts),
        "external_id_recoveries": external_id_recoveries,
        "network_guardrails": {
            "rate_limit": ATCOrchestrator.RATE_LIMIT,
            "cache_ttl_hours": ATCOrchestrator.CACHE_TTL_HOURS,
            "cache_dir": str(cache_dir),
            "max_concurrency": max_network_concurrency,
            "cache_hits": network_cache_hits,
            "cache_misses": network_cache_misses,
            "partial_failure_reports": True,
        },
    }


def write_enrichment_reports(
    reports_dir: Path,
    report: Dict[str, Any],
    unresolved: List[Dict[str, Any]],
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "atc_enrichment_summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (reports_dir / "atc_unresolved_drugs.json").write_text(
        json.dumps({"generated_at": utcnow_iso(), "drugs": unresolved}, indent=2),
        encoding="utf-8",
    )
