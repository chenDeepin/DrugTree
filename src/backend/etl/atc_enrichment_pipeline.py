"""Canonical ATC enrichment pipeline implementation."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

try:
    from .atc_enrichment_models import (
        ATCResolution,
        DATA_DIR,
        DEFAULT_DRUGS_FILE,
        DEFAULT_REPORTS_DIR,
        DrugEnrichmentOutcome,
        KEGG_DBLINK_FIELD_MAP,
    )
    from .atc_lookup_service import ATCCode, ATCOrchestrator, utcnow_iso
    from .atc_utils import (
        ATC_CODE_PATTERN,
        is_placeholder_atc_code,
        is_specific_atc_code,
        load_drug_payload,
        merge_external_ids,
        write_drug_payload,
    )
    from .atc_batch_chembl import ChEMBLBatchProcessor
    from .atc_batch_pubchem import PubChemBatchProcessor
    from .atc_kegg_brite_lookup import KEGGBRITEATCLookup
    from .classify_remaining_drugs import (
        classify_by_body_region,
        classify_by_indication,
        classify_by_name,
    )
except ImportError:  # pragma: no cover - direct script fallback
    from src.backend.etl.atc_enrichment_models import (
        ATCResolution,
        DATA_DIR,
        DEFAULT_DRUGS_FILE,
        DEFAULT_REPORTS_DIR,
        DrugEnrichmentOutcome,
        KEGG_DBLINK_FIELD_MAP,
    )
    from src.backend.etl.atc_lookup_service import ATCCode, ATCOrchestrator, utcnow_iso
    from src.backend.etl.atc_utils import (
        ATC_CODE_PATTERN,
        is_placeholder_atc_code,
        is_specific_atc_code,
        load_drug_payload,
        merge_external_ids,
        write_drug_payload,
    )
    from src.backend.etl.atc_batch_chembl import ChEMBLBatchProcessor
    from src.backend.etl.atc_batch_pubchem import PubChemBatchProcessor
    from src.backend.etl.atc_kegg_brite_lookup import KEGGBRITEATCLookup
    from src.backend.etl.classify_remaining_drugs import (
        classify_by_body_region,
        classify_by_indication,
        classify_by_name,
    )

class ATCEnrichmentPipeline:
    """
    Single ATC enrichment pipeline for canonical drug data.

    Resolution order:
    1. Preserve existing valid ATC codes
    2. KEGG DBLINKS recovery for missing external IDs
    3. KEGG direct ATC lookup
    4. PubChem ATC lookup
    5. ChEMBL ATC lookup
    6. WHO name lookup
    7. KEGG BRITE local lookup
    8. Name/indication/body fallback
    """

    def __init__(
        self,
        drugs_file: Path = DEFAULT_DRUGS_FILE,
        reports_dir: Path = DEFAULT_REPORTS_DIR,
        cache_dir: Path = DATA_DIR / "checkpoints" / "atc-cache",
        enable_network: bool = True,
        enable_kegg_brite: bool = True,
        enable_fallback: bool = True,
        enable_who: bool = True,
        request_timeout: float = 20.0,
    ):
        self.drugs_file = Path(drugs_file)
        self.reports_dir = Path(reports_dir)
        self.cache_dir = Path(cache_dir)
        self.enable_network = enable_network
        self.enable_kegg_brite = enable_kegg_brite
        self.enable_fallback = enable_fallback
        self.enable_who = enable_who
        self.request_timeout = request_timeout
        self.max_network_concurrency = 5
        self.network_cache_hits = 0
        self.network_cache_misses = 0

        self._kegg_entry_cache: Dict[str, Optional[str]] = {}
        self._brite_lookup: Optional[KEGGBRITEATCLookup] = None
        self._brite_lookup_ready = False
        self._network_semaphores: Dict[int, asyncio.Semaphore] = {}

    def _get_network_semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        semaphore = self._network_semaphores.get(loop_id)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self.max_network_concurrency)
            self._network_semaphores[loop_id] = semaphore
        return semaphore

    def run(
        self,
        limit: Optional[int] = None,
        dry_run: bool = False,
        placeholder_only: bool = False,
    ) -> Dict[str, Any]:
        payload, drugs = load_drug_payload(self.drugs_file)

        updated_drugs: List[Dict[str, Any]] = []
        outcomes: List[DrugEnrichmentOutcome] = []
        unresolved: List[Dict[str, Any]] = []
        processed_drugs: List[Dict[str, Any]] = []
        processed = 0

        for drug in drugs:
            should_process = not placeholder_only or is_placeholder_atc_code(
                drug.get("atc_code")
            )
            if not should_process:
                updated_drugs.append(deepcopy(drug))
                continue

            if limit is not None and processed >= limit:
                updated_drugs.append(deepcopy(drug))
                continue

            updated_drug, outcome = self.enrich_drug(drug)
            updated_drugs.append(updated_drug)
            outcomes.append(outcome)
            processed_drugs.append(drug)
            processed += 1

            if is_placeholder_atc_code(updated_drug.get("atc_code")):
                unresolved.append(
                    {
                        "id": updated_drug.get("id"),
                        "name": updated_drug.get("name"),
                        "atc_code": updated_drug.get("atc_code"),
                        "atc_category": updated_drug.get("atc_category"),
                        "atc_source": updated_drug.get("atc_source"),
                        "atc_confidence": updated_drug.get("atc_confidence"),
                        "atc_resolution_method": updated_drug.get(
                            "atc_resolution_method"
                        ),
                        "kegg_id": updated_drug.get("kegg_id"),
                        "chembl_id": updated_drug.get("chembl_id"),
                        "pubchem_cid": updated_drug.get("pubchem_cid"),
                        "drugbank_id": updated_drug.get("drugbank_id"),
                    }
                )

        report = self._build_report(
            original_drugs=drugs,
            updated_drugs=updated_drugs,
            processed_drugs=processed_drugs,
            outcomes=outcomes,
            unresolved=unresolved,
            processed_count=processed,
            dry_run=dry_run,
            placeholder_only=placeholder_only,
        )

        if not dry_run:
            write_drug_payload(self.drugs_file, payload, updated_drugs)
            self._write_reports(report, unresolved)

        return report

    def enrich_drug(
        self, drug: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], DrugEnrichmentOutcome]:
        updated = deepcopy(drug)

        if is_specific_atc_code(updated.get("atc_code")):
            updated.setdefault("atc_source", "existing")
            updated.setdefault("atc_confidence", 1.0)
            updated.setdefault("atc_resolution_method", "preserved_existing")
            return updated, DrugEnrichmentOutcome(
                drug_id=updated.get("id", ""),
                status="preserved",
                source=updated.get("atc_source", "existing"),
                method=updated.get("atc_resolution_method", "preserved_existing"),
                atc_code=updated.get("atc_code"),
            )

        updated, recovered_ids = merge_external_ids(
            updated, self._recover_external_ids_from_kegg_dblinks(updated)
        )

        for resolver in (
            self._resolve_from_kegg_direct,
            self._resolve_from_pubchem,
            self._resolve_from_chembl,
            self._resolve_from_who_lookup,
            self._resolve_from_kegg_brite,
        ):
            resolution = resolver(updated)
            if not resolution:
                continue

            updated, merged_ids = merge_external_ids(updated, resolution.external_ids)
            all_recovered_ids = {**recovered_ids, **merged_ids}

            if not is_specific_atc_code(resolution.atc_code):
                continue

            updated["atc_code"] = resolution.atc_code
            updated["atc_category"] = resolution.atc_category or (
                resolution.atc_code[0] if resolution.atc_code else None
            )
            updated["atc_source"] = resolution.source
            updated["atc_confidence"] = resolution.confidence
            updated["atc_resolution_method"] = resolution.method

            return updated, DrugEnrichmentOutcome(
                drug_id=updated.get("id", ""),
                status="resolved",
                source=resolution.source,
                method=resolution.method,
                atc_code=resolution.atc_code,
                external_ids_recovered=all_recovered_ids,
            )

        fallback = self._resolve_from_fallback(updated)
        if fallback:
            updated, merged_ids = merge_external_ids(updated, fallback.external_ids)
            all_recovered_ids = {**recovered_ids, **merged_ids}
            original_atc_code = str(updated.get("atc_code", "")).upper()

            if fallback.atc_code and (
                not updated.get("atc_code") or original_atc_code.startswith("V99")
            ):
                updated["atc_code"] = fallback.atc_code
            if fallback.atc_category and (
                not updated.get("atc_category") or original_atc_code.startswith("V99")
            ):
                updated["atc_category"] = fallback.atc_category

            updated["atc_source"] = fallback.source
            updated["atc_confidence"] = fallback.confidence
            updated["atc_resolution_method"] = fallback.method

            return updated, DrugEnrichmentOutcome(
                drug_id=updated.get("id", ""),
                status="placeholder",
                source=fallback.source,
                method=fallback.method,
                atc_code=updated.get("atc_code"),
                external_ids_recovered=all_recovered_ids,
            )

        updated["atc_source"] = "unresolved"
        updated["atc_confidence"] = 0.0
        updated["atc_resolution_method"] = "placeholder_unresolved"

        return updated, DrugEnrichmentOutcome(
            drug_id=updated.get("id", ""),
            status="placeholder",
            source="unresolved",
            method="placeholder_unresolved",
            atc_code=updated.get("atc_code"),
            external_ids_recovered=recovered_ids,
        )

    async def _fetch_kegg_entry_text_async(self, kegg_id: Optional[str]) -> Optional[str]:
        if not self.enable_network or not kegg_id:
            return None

        normalized = str(kegg_id).strip().replace("drug:", "").replace("dr:", "")
        if not normalized:
            return None

        if normalized in self._kegg_entry_cache:
            return self._kegg_entry_cache[normalized]

        url = f"https://rest.kegg.jp/get/drug:{normalized}"
        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                response = await client.get(url)
            if response.status_code != 200:
                self._kegg_entry_cache[normalized] = None
                return None
            self._kegg_entry_cache[normalized] = response.text
            return response.text
        except httpx.HTTPError:
            self._kegg_entry_cache[normalized] = None
            return None

    def _fetch_kegg_entry_text(self, kegg_id: Optional[str]) -> Optional[str]:
        """Compatibility wrapper around the async KEGG entry fetcher."""
        return asyncio.run(self._fetch_kegg_entry_text_async(kegg_id))

    def _extract_atc_codes_from_kegg_text(self, text: str) -> List[str]:
        matches: List[str] = []
        for line in text.splitlines():
            if "ATC" not in line.upper():
                continue
            for code in ATC_CODE_PATTERN.findall(line.upper()):
                if is_specific_atc_code(code):
                    matches.append(code)
        return list(dict.fromkeys(matches))

    def _parse_kegg_dblinks(self, text: str) -> Dict[str, Any]:
        dblinks: Dict[str, Any] = {}
        current_section = ""

        for raw_line in text.splitlines():
            section = raw_line[:12].strip()
            value = raw_line[12:].strip()

            if section:
                current_section = section

            if current_section != "DBLINKS" or not value or ":" not in value:
                continue

            label, raw_values = value.split(":", 1)
            field_name = KEGG_DBLINK_FIELD_MAP.get(label.strip())
            if not field_name:
                continue

            entries = [
                entry.strip().rstrip(";") for entry in raw_values.split() if entry
            ]
            if not entries:
                continue

            selected_value: Any = entries[0]
            if field_name == "pubchem_cid":
                match = re.search(r"\d+", selected_value)
                if not match:
                    continue
                selected_value = match.group(0)

            dblinks[field_name] = selected_value

        return dblinks

    def _recover_external_ids_from_kegg_dblinks(
        self, drug: Dict[str, Any]
    ) -> Dict[str, Any]:
        text = self._fetch_kegg_entry_text(drug.get("kegg_id"))
        if not text:
            return {}
        return self._parse_kegg_dblinks(text)

    def _resolve_from_kegg_direct(
        self, drug: Dict[str, Any]
    ) -> Optional[ATCResolution]:
        text = self._fetch_kegg_entry_text(drug.get("kegg_id"))
        if not text:
            return None

        atc_codes = self._extract_atc_codes_from_kegg_text(text)
        if not atc_codes:
            return None

        return ATCResolution(
            atc_code=atc_codes[0],
            atc_category=atc_codes[0][0],
            source="kegg",
            confidence=1.0,
            method="kegg_direct",
            evidence={"alternatives": atc_codes[1:]},
        )

    async def _lookup_pubchem_async(self, drug: Dict[str, Any]) -> Dict[str, Any]:
        async with self._get_network_semaphore():
            processor = PubChemBatchProcessor()
            try:
                return await processor.lookup_atc_for_drug(drug)
            finally:
                client = getattr(processor, "_client", None)
                if client is not None:
                    await client.aclose()

    def _resolve_from_pubchem(self, drug: Dict[str, Any]) -> Optional[ATCResolution]:
        if not self.enable_network:
            return None

        result = asyncio.run(self._lookup_pubchem_async(drug))
        if not is_specific_atc_code(result.get("atc_code")):
            return None

        return ATCResolution(
            atc_code=result.get("atc_code"),
            atc_category=result.get("atc_category"),
            source="pubchem",
            confidence=float(result.get("confidence") or 0.8),
            method="pubchem_lookup",
            external_ids={"pubchem_cid": result.get("pubchem_cid")},
            evidence={"alternatives": result.get("alternatives", [])},
        )

    async def _lookup_chembl_async(self, drug: Dict[str, Any]) -> Dict[str, Any]:
        async with self._get_network_semaphore():
            processor = ChEMBLBatchProcessor()
            try:
                return await processor.lookup_atc_for_drug(drug)
            finally:
                client = getattr(processor, "_client", None)
                if client is not None:
                    await client.aclose()

    def _resolve_from_chembl(self, drug: Dict[str, Any]) -> Optional[ATCResolution]:
        if not self.enable_network:
            return None

        result = asyncio.run(self._lookup_chembl_async(drug))
        if not is_specific_atc_code(result.get("atc_code")):
            return None

        return ATCResolution(
            atc_code=result.get("atc_code"),
            atc_category=result.get("atc_category"),
            source="chembl",
            confidence=float(result.get("confidence") or 0.9),
            method="chembl_lookup",
            external_ids={"chembl_id": result.get("chembl_id")},
            evidence={"alternatives": result.get("alternatives", [])},
        )

    async def _lookup_who_async(self, drug_name: str) -> Optional[ATCCode]:
        async with self._get_network_semaphore():
            async with ATCOrchestrator(
                cache_dir=str(self.cache_dir), request_timeout=self.request_timeout
            ) as orchestrator:
                result = await orchestrator._lookup_who(drug_name)
                self.network_cache_hits += orchestrator._cache_hits
                self.network_cache_misses += orchestrator._cache_misses
                return result

    def _resolve_from_who_lookup(self, drug: Dict[str, Any]) -> Optional[ATCResolution]:
        if not self.enable_network or not self.enable_who or not drug.get("name"):
            return None

        result = asyncio.run(self._lookup_who_async(drug["name"]))
        if not result or not is_specific_atc_code(result.code):
            return None

        return ATCResolution(
            atc_code=result.code,
            atc_category=result.code[0],
            source="who",
            confidence=float(result.confidence),
            method="who_name_lookup",
            evidence={"who_url": result.who_url},
        )

    def _ensure_brite_lookup(self) -> Optional[KEGGBRITEATCLookup]:
        if self._brite_lookup_ready:
            return self._brite_lookup

        self._brite_lookup_ready = True
        if not self.enable_kegg_brite:
            return None

        try:
            lookup = KEGGBRITEATCLookup()
            lookup.parse()
            self._brite_lookup = lookup
        except FileNotFoundError:
            self._brite_lookup = None

        return self._brite_lookup

    def _resolve_from_kegg_brite(self, drug: Dict[str, Any]) -> Optional[ATCResolution]:
        lookup = self._ensure_brite_lookup()
        if not lookup:
            return None

        kegg_id = drug.get("kegg_id")
        if kegg_id:
            code = lookup.lookup_by_kegg_id(kegg_id)
            if is_specific_atc_code(code):
                return ATCResolution(
                    atc_code=code,
                    atc_category=code[0] if code else None,
                    source="kegg_brite",
                    confidence=0.85,
                    method="kegg_brite_kegg_id",
                )

        name = drug.get("name")
        if name:
            code = lookup.lookup_by_name(name)
            if is_specific_atc_code(code):
                return ATCResolution(
                    atc_code=code,
                    atc_category=code[0] if code else None,
                    source="kegg_brite",
                    confidence=0.75,
                    method="kegg_brite_name",
                )

        return None

    def _resolve_from_fallback(self, drug: Dict[str, Any]) -> Optional[ATCResolution]:
        if not self.enable_fallback:
            return None

        atc_code, atc_category = classify_by_indication(drug)
        if atc_code:
            return ATCResolution(
                atc_code=atc_code,
                atc_category=atc_category,
                source="fallback",
                confidence=0.35,
                method="fallback_indication",
            )

        atc_code, atc_category = classify_by_name(drug)
        if atc_code:
            return ATCResolution(
                atc_code=atc_code,
                atc_category=atc_category,
                source="fallback",
                confidence=0.3,
                method="fallback_name",
            )

        atc_code, atc_category = classify_by_body_region(drug)
        if atc_code:
            return ATCResolution(
                atc_code=atc_code,
                atc_category=atc_category,
                source="fallback",
                confidence=0.2,
                method="fallback_body_region",
            )

        return None

    def _build_report(
        self,
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
            1
            for drug in processed_drugs
            if is_placeholder_atc_code(drug.get("atc_code"))
        )
        total_input_placeholder_count = sum(
            1
            for drug in original_drugs
            if is_placeholder_atc_code(drug.get("atc_code"))
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
            "drugs_file": str(self.drugs_file),
            "processed_count": processed_count,
            "total_drugs": len(updated_drugs),
            "dry_run": dry_run,
            "selection_mode": "placeholder_only"
            if placeholder_only
            else "full_dataset",
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
                1
                for drug in updated_drugs
                if is_placeholder_atc_code(drug.get("atc_code"))
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
                "cache_dir": str(self.cache_dir),
                "max_concurrency": self.max_network_concurrency,
                "cache_hits": self.network_cache_hits,
                "cache_misses": self.network_cache_misses,
                "partial_failure_reports": True,
            },
        }

    def _write_reports(
        self, report: Dict[str, Any], unresolved: List[Dict[str, Any]]
    ) -> None:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / "atc_enrichment_summary.json").write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        (self.reports_dir / "atc_unresolved_drugs.json").write_text(
            json.dumps({"generated_at": utcnow_iso(), "drugs": unresolved}, indent=2),
            encoding="utf-8",
        )
