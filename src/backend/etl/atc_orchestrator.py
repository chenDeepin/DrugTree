"""
Canonical ATC enrichment entrypoint for DrugTree.

This module keeps the lightweight async lookup helpers used elsewhere in the
codebase, and adds a single orchestrated pipeline for ATC enrichment. The
pipeline works against the canonical `data/drugs.json` dataset, preserves
existing valid ATC codes, tracks provenance, recovers external IDs from KEGG
DBLINKS when possible, and emits summary/unresolved reports.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import requests

try:
    from .atc_batch_chembl import ChEMBLBatchProcessor
    from .atc_batch_pubchem import PubChemBatchProcessor
    from .atc_kegg_brite_lookup import KEGGBRITEATCLookup
    from .classify_remaining_drugs import (
        classify_by_body_region,
        classify_by_indication,
        classify_by_name,
    )
except ImportError:  # pragma: no cover - direct script fallback
    from atc_batch_chembl import ChEMBLBatchProcessor
    from atc_batch_pubchem import PubChemBatchProcessor
    from atc_kegg_brite_lookup import KEGGBRITEATCLookup
    from classify_remaining_drugs import (
        classify_by_body_region,
        classify_by_indication,
        classify_by_name,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DRUGS_FILE = DATA_DIR / "drugs.json"
DEFAULT_REPORTS_DIR = DATA_DIR / "reports"

ATC_CODE_PATTERN = re.compile(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
PLACEHOLDER_ATC_PATTERN = re.compile(r"^[A-Z]99XX99$")
KEGG_DBLINK_FIELD_MAP = {
    "PubChem": "pubchem_cid",
    "PubChem Compound": "pubchem_cid",
    "DrugBank": "drugbank_id",
    "ChEMBL": "chembl_id",
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_placeholder_atc_code(code: Optional[str]) -> bool:
    if not code:
        return True

    normalized = str(code).strip().upper()
    return not normalized or bool(PLACEHOLDER_ATC_PATTERN.match(normalized))


def is_specific_atc_code(code: Optional[str]) -> bool:
    if not code:
        return False

    normalized = str(code).strip().upper()
    return bool(ATC_CODE_PATTERN.match(normalized)) and not is_placeholder_atc_code(
        normalized
    )


def load_drug_payload(path: Path) -> Tuple[Any, List[Dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    drugs = payload if isinstance(payload, list) else payload.get("drugs", [])
    if not isinstance(drugs, list):
        raise ValueError(f"Unexpected drug payload format in {path}")
    return payload, drugs


def write_drug_payload(path: Path, payload: Any, drugs: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_payload = drugs if isinstance(payload, list) else {**payload, "drugs": drugs}
    path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")


def merge_external_ids(
    drug: Dict[str, Any], external_ids: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not external_ids:
        return drug, {}

    merged = deepcopy(drug)
    applied: Dict[str, Any] = {}

    for field_name, value in external_ids.items():
        if value in (None, "", []):
            continue

        normalized_value: Any = value
        if field_name == "pubchem_cid":
            try:
                normalized_value = int(str(value).strip())
            except (TypeError, ValueError):
                continue

        existing_value = merged.get(field_name)
        if existing_value in (None, "", []):
            merged[field_name] = normalized_value
            applied[field_name] = normalized_value

    return merged, applied


class ATCLookupError(Exception):
    pass


class ATCNotFoundError(ATCLookupError):
    pass


@dataclass
class ATCCode:
    code: str
    name: str
    level1: str
    level2: str
    level3: str
    level4: str
    level5: str
    level1_name: str
    level2_name: Optional[str] = None
    level3_name: Optional[str] = None
    level4_name: Optional[str] = None
    level5_name: Optional[str] = None
    who_url: Optional[str] = None
    chembl_id: Optional[str] = None
    source: str = "who"
    confidence: float = 1.0


class ATCOrchestrator:
    WHO_ATC_URL = "https://www.whocc.no/api/atc"
    WHO_ATC_SEARCH_URL = "https://www.whocc.no/api/atc/search"
    CHEMBL_URL = "https://www.ebi.ac.uk/chembl/api/data"
    CACHE_TTL_HOURS = 24
    RATE_LIMIT = 5
    RATE_WINDOW = 1.0

    def __init__(self, cache_dir: Optional[str] = None, request_timeout: float = 30.0):
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_timeout = request_timeout
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._cache_dir = cache_dir
        self._request_times: List[float] = []
        self._rate_limit_lock = asyncio.Lock()

        self._level1_categories: Dict[str, str] = {
            "A": "Alimentary tract and metabolism",
            "B": "Blood and blood forming organs",
            "C": "Cardiovascular system",
            "D": "Dermatologicals",
            "G": "Genito-urinary system and sex hormones",
            "H": "Systemic hormonal preparations, excluding sex hormones",
            "J": "Antiinfectives for systemic use",
            "L": "Antineoplastic and immunomodulating agents",
            "M": "Musculo-skeletal system",
            "N": "Nervous system",
            "P": "Antiparasitic products, insecticides and repellents",
            "R": "Respiratory system",
            "S": "Sensory organs",
            "V": "Various",
        }

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None

    async def _enforce_rate_limit(self):
        async with self._rate_limit_lock:
            import time

            now = time.time()
            self._request_times = [
                t for t in self._request_times if now - t < self.RATE_WINDOW
            ]
            if len(self._request_times) >= self.RATE_LIMIT:
                sleep_time = self.RATE_WINDOW - (now - self._request_times[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            self._request_times.append(time.time())

    def _get_cache_key(self, query_type: str, identifier: str) -> str:
        return f"atc:{query_type}:{identifier}"

    async def _get_cached(self, cache_key: str) -> Optional[Any]:
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < timedelta(hours=self.CACHE_TTL_HOURS):
                return data
            del self._cache[cache_key]
        return None

    async def _set_cache(self, cache_key: str, data: Any):
        self._cache[cache_key] = (data, datetime.now())

    def _parse_atc_code(self, code: str) -> ATCCode:
        if not code or len(code) < 1:
            raise ValueError(f"Invalid ATC code: {code}")

        code = code.upper().strip()
        level1 = code[0] if len(code) >= 1 else ""
        level2 = code[1:3] if len(code) >= 3 else ""
        level3 = code[1:4] if len(code) >= 4 else ""
        level4 = code[1:5] if len(code) >= 5 else ""
        level5 = code[1:7] if len(code) >= 7 else ""

        return ATCCode(
            code=code,
            name="",
            level1=level1,
            level2=level2,
            level3=level3,
            level4=level4,
            level5=level5,
            level1_name=self._level1_categories.get(level1, ""),
            source="who",
            confidence=1.0,
        )

    async def lookup(self, drug_name: str) -> Optional[ATCCode]:
        cache_key = self._get_cache_key("name", drug_name.lower())
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        await self._enforce_rate_limit()
        atc_code = await self._lookup_who(drug_name)

        if atc_code:
            await self._set_cache(cache_key, atc_code)
            return atc_code

        atc_code = await self._lookup_chembl(drug_name)
        if atc_code:
            atc_code.source = "chembl"
            atc_code.confidence = 0.7
            await self._set_cache(cache_key, atc_code)
            return atc_code

        return None

    async def lookup_by_class(
        self, drug_class: str, level1_hint: Optional[str] = None
    ) -> Optional[ATCCode]:
        cache_key = self._get_cache_key("class", f"{drug_class}:{level1_hint or ''}")
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        if not level1_hint:
            drug_class_lower = drug_class.lower()
            class_to_atc = {
                "statin": "C",
                "hmg-coa reductase inhibitor": "C",
                "beta blocker": "C",
                "ace inhibitor": "C",
                "arb": "C",
                "calcium channel blocker": "C",
                "diuretic": "C",
                "antibiotic": "J",
                "penicillin": "J",
                "cephalosporin": "J",
                "quinolone": "J",
                "proton pump inhibitor": "A",
                "ppi": "A",
                "nsaid": "M",
                "cox-2 inhibitor": "M",
                "opioid": "N",
                "benzodiazepine": "N",
                "ssri": "N",
                "antidepressant": "N",
                "antipsychotic": "N",
                "corticosteroid": "H",
                "insulin": "H",
                "antihistamine": "R",
                "bronchodilator": "R",
                "antineoplastic": "L",
                "chemotherapy": "L",
            }
            level1_hint = class_to_atc.get(drug_class_lower)

        if level1_hint:
            atc_code = ATCCode(
                code=level1_hint,
                name=drug_class,
                level1=level1_hint,
                level2="",
                level3="",
                level4="",
                level5="",
                level1_name=self._level1_categories.get(level1_hint, ""),
                source="inferred",
                confidence=0.5,
            )
            await self._set_cache(cache_key, atc_code)
            return atc_code

        return None

    async def search(self, query: str) -> List[ATCCode]:
        cache_key = self._get_cache_key("search", query.lower())
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        await self._enforce_rate_limit()
        results = await self._search_who(query)

        if results:
            await self._set_cache(cache_key, results)
            return results

        return []

    async def _lookup_who(self, drug_name: str) -> Optional[ATCCode]:
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with.")

        try:
            url = self.WHO_ATC_SEARCH_URL
            params = {"q": drug_name, "limit": 5}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if "records" in data and len(data["records"]) > 0:
                        record = data["records"][0]
                        atc_code_str = record.get("code", record.get("atc_code", ""))

                        if atc_code_str:
                            atc_code = self._parse_atc_code(atc_code_str)
                            atc_code.name = drug_name
                            atc_code.who_url = (
                                f"https://www.whocc.no/atc_ddd_index/?code={atc_code_str}"
                            )
                            return atc_code

                    return None
                return None
        except aiohttp.ClientError:
            return None

    async def _lookup_chembl(self, drug_name: str) -> Optional[ATCCode]:
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with.")

        try:
            url = f"{self.CHEMBL_URL}/molecule/search"
            params = {"q": drug_name, "limit": 1}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if "molecules" in data and len(data["molecules"]) > 0:
                        molecule = data["molecules"][0]
                        atc_classifications = molecule.get("atc_classifications", [])

                        if atc_classifications and len(atc_classifications) > 0:
                            atc_data = atc_classifications[0]
                            atc_code_str = atc_data.get(
                                "level5", atc_data.get("code", "")
                            )

                            if atc_code_str:
                                atc_code = self._parse_atc_code(atc_code_str)
                                atc_code.name = drug_name
                                atc_code.chembl_id = molecule.get("molecule_chembl_id")
                                return atc_code

                    return None
                return None
        except aiohttp.ClientError:
            return None

    async def _search_who(self, query: str) -> List[ATCCode]:
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with.")

        try:
            url = self.WHO_ATC_SEARCH_URL
            params = {"q": query, "limit": 20}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = []

                    if "records" in data:
                        for record in data["records"]:
                            atc_code_str = record.get(
                                "code", record.get("atc_code", "")
                            )
                            if atc_code_str:
                                atc_code = self._parse_atc_code(atc_code_str)
                                atc_code.name = record.get("name", "")
                                atc_code.who_url = (
                                    f"https://www.whocc.no/atc_ddd_index/?code={atc_code_str}"
                                )
                                results.append(atc_code)

                    return results
                return []
        except aiohttp.ClientError:
            return []

    async def validate_atc_code(self, code: str) -> tuple[bool, str]:
        if is_specific_atc_code(code):
            return True, ""

        try:
            atc_code = self._parse_atc_code(code)
            if atc_code.level1 not in self._level1_categories:
                return False, f"Invalid level 1 code: {atc_code.level1}"
            if is_placeholder_atc_code(code):
                return False, f"Placeholder ATC code: {code}"
            return False, f"Invalid ATC format: {code}"
        except ValueError as exc:
            return False, str(exc)

    def get_level1_name(self, level1: str) -> str:
        return self._level1_categories.get(level1.upper(), "")

    def get_all_level1_categories(self) -> Dict[str, str]:
        return self._level1_categories.copy()


@dataclass
class ATCResolution:
    atc_code: Optional[str]
    atc_category: Optional[str]
    source: str
    confidence: float
    method: str
    external_ids: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DrugEnrichmentOutcome:
    drug_id: str
    status: str
    source: str
    method: str
    atc_code: Optional[str]
    external_ids_recovered: Dict[str, Any] = field(default_factory=dict)


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
        enable_network: bool = True,
        enable_kegg_brite: bool = True,
        enable_fallback: bool = True,
        enable_who: bool = True,
        request_timeout: float = 20.0,
    ):
        self.drugs_file = Path(drugs_file)
        self.reports_dir = Path(reports_dir)
        self.enable_network = enable_network
        self.enable_kegg_brite = enable_kegg_brite
        self.enable_fallback = enable_fallback
        self.enable_who = enable_who
        self.request_timeout = request_timeout

        self._kegg_entry_cache: Dict[str, Optional[str]] = {}
        self._brite_lookup: Optional[KEGGBRITEATCLookup] = None
        self._brite_lookup_ready = False

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
            updated["atc_category"] = (
                resolution.atc_category or resolution.atc_code[0]
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

            if (
                fallback.atc_code
                and (
                    not updated.get("atc_code")
                    or original_atc_code.startswith("V99")
                )
            ):
                updated["atc_code"] = fallback.atc_code
            if fallback.atc_category and (
                not updated.get("atc_category")
                or original_atc_code.startswith("V99")
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

    def _fetch_kegg_entry_text(self, kegg_id: Optional[str]) -> Optional[str]:
        if not self.enable_network or not kegg_id:
            return None

        normalized = str(kegg_id).strip().replace("drug:", "").replace("dr:", "")
        if not normalized:
            return None

        if normalized in self._kegg_entry_cache:
            return self._kegg_entry_cache[normalized]

        url = f"https://rest.kegg.jp/get/drug:{normalized}"
        try:
            response = requests.get(url, timeout=self.request_timeout)
            if response.status_code != 200:
                self._kegg_entry_cache[normalized] = None
                return None
            self._kegg_entry_cache[normalized] = response.text
            return response.text
        except requests.RequestException:
            self._kegg_entry_cache[normalized] = None
            return None

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

            entries = [entry.strip().rstrip(";") for entry in raw_values.split() if entry]
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
        async with ATCOrchestrator(request_timeout=self.request_timeout) as orchestrator:
            return await orchestrator._lookup_who(drug_name)

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

    def _resolve_from_kegg_brite(
        self, drug: Dict[str, Any]
    ) -> Optional[ATCResolution]:
        lookup = self._ensure_brite_lookup()
        if not lookup:
            return None

        kegg_id = drug.get("kegg_id")
        if kegg_id:
            code = lookup.lookup_by_kegg_id(kegg_id)
            if is_specific_atc_code(code):
                return ATCResolution(
                    atc_code=code,
                    atc_category=code[0],
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
                    atc_category=code[0],
                    source="kegg_brite",
                    confidence=0.75,
                    method="kegg_brite_name",
                )

        return None

    def _resolve_from_fallback(
        self, drug: Dict[str, Any]
    ) -> Optional[ATCResolution]:
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
            if drug.get("year_approved") is not None or str(drug.get("phase", "")).upper() == "IV"
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


async def lookup_atc(drug_name: str) -> Optional[ATCCode]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.lookup(drug_name)


async def lookup_atc_by_class(
    drug_class: str, level1_hint: Optional[str] = None
) -> Optional[ATCCode]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.lookup_by_class(drug_class, level1_hint)


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
