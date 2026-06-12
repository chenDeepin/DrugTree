"""Canonical ATC enrichment entrypoint for DrugTree.

This module preserves the historical public import path while the lookup service
and enrichment pipeline live in focused modules.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import List, Optional

try:
    from .atc_utils import is_placeholder_atc_code, is_specific_atc_code
    from .atc_lookup_service import ATCCode, ATCLookupError, ATCNotFoundError, ATCOrchestrator
    from .atc_enrichment_pipeline import (
        ATCEnrichmentPipeline,
        ATCResolution,
        DrugEnrichmentOutcome,
        DEFAULT_DRUGS_FILE,
        DEFAULT_REPORTS_DIR,
    )
except ImportError:  # pragma: no cover - direct script fallback
    from src.backend.etl.atc_utils import is_placeholder_atc_code, is_specific_atc_code
    from src.backend.etl.atc_lookup_service import ATCCode, ATCLookupError, ATCNotFoundError, ATCOrchestrator
    from src.backend.etl.atc_enrichment_pipeline import (
        ATCEnrichmentPipeline,
        ATCResolution,
        DrugEnrichmentOutcome,
        DEFAULT_DRUGS_FILE,
        DEFAULT_REPORTS_DIR,
    )


async def lookup_atc(drug_name: str) -> Optional[ATCCode]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.lookup(drug_name)


async def lookup_atc_by_class(
    drug_class: str,
    indication: Optional[str] = None,
) -> Optional[ATCCode]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.lookup_by_class(drug_class, indication)


async def search_atc(query: str) -> List[ATCCode]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.search(query)


async def validate_atc(code: str) -> tuple[bool, str]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.validate_atc_code(code)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DrugTree canonical ATC enrichment")
    parser.add_argument(
        "--input",
        default=str(DEFAULT_DRUGS_FILE),
        help="Canonical drug dataset to enrich",
    )
    parser.add_argument(
        "--reports-dir",
        default=str(DEFAULT_REPORTS_DIR),
        help="Directory for unresolved/statistics reports",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N selected drugs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute enrichment without writing data or reports",
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="Disable KEGG, PubChem, ChEMBL, and WHO network lookups",
    )
    parser.add_argument(
        "--skip-brite",
        action="store_true",
        help="Disable local KEGG BRITE matching",
    )
    parser.add_argument(
        "--skip-fallback",
        action="store_true",
        help="Disable placeholder fallback classification",
    )
    parser.add_argument(
        "--skip-who",
        action="store_true",
        help="Disable WHO name lookup while keeping other live resolvers enabled",
    )
    parser.add_argument(
        "--placeholder-only",
        action="store_true",
        help="Only process drugs whose current ATC code is still a placeholder",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    pipeline = ATCEnrichmentPipeline(
        drugs_file=Path(args.input),
        reports_dir=Path(args.reports_dir),
        enable_network=not args.no_network,
        enable_kegg_brite=not args.skip_brite,
        enable_fallback=not args.skip_fallback,
        enable_who=not args.skip_who,
    )
    report = pipeline.run(
        limit=args.limit,
        dry_run=args.dry_run,
        placeholder_only=args.placeholder_only,
    )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
