#!/usr/bin/env python3
"""Fetch ClinicalTrials.gov raw study records for local drugs and diseases."""

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import httpx

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "clinicaltrials"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "fetch_clinicaltrials_checkpoint.json"
DRUGS_FILE = DATA_DIR / "drugs.json"
DISEASES_FILE = DATA_DIR / "diseases.json"

STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: Any) -> str:
    return normalize_text(value).lower()


def load_local_drugs(limit: Optional[int] = None) -> List[Dict[str, str]]:
    if not DRUGS_FILE.exists():
        LOGGER.warning("Canonical drugs file missing: %s", DRUGS_FILE)
        return []

    payload = json.loads(DRUGS_FILE.read_text(encoding="utf-8"))
    drugs = payload.get("drugs", []) if isinstance(payload, dict) else payload
    items: List[Dict[str, str]] = []
    for drug in drugs:
        if not isinstance(drug, dict):
            continue
        name = normalize_text(drug.get("name"))
        if name:
            items.append({"drug_id": normalize_text(drug.get("id")), "drug_name": name})
    if limit is not None and limit > 0:
        return items[:limit]
    return items


def load_local_diseases(limit: Optional[int] = None) -> List[Dict[str, str]]:
    if not DISEASES_FILE.exists():
        LOGGER.warning("Canonical diseases file missing: %s", DISEASES_FILE)
        return []

    payload = json.loads(DISEASES_FILE.read_text(encoding="utf-8"))
    diseases = payload.get("diseases", []) if isinstance(payload, dict) else payload
    items: List[Dict[str, str]] = []
    for disease in diseases:
        if not isinstance(disease, dict):
            continue
        name = normalize_text(disease.get("canonical_name"))
        if name:
            items.append(
                {"disease_id": normalize_text(disease.get("id")), "disease_name": name}
            )
    if limit is not None and limit > 0:
        return items[:limit]
    return items


def build_name_lookup(
    items: Iterable[Dict[str, str]], name_key: str
) -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    for item in items:
        name = normalize_text(item.get(name_key))
        if name:
            lookup[normalize_key(name)] = item
    return lookup


def write_jsonl_with_snapshot(
    path: Path, records: Iterable[Dict[str, Any]]
) -> Tuple[Path, int]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = path.with_name(f"{path.stem}_{timestamp_tag()}{path.suffix}")
    count = 0

    with (
        path.open("w", encoding="utf-8") as current,
        snapshot.open("w", encoding="utf-8") as stamped,
    ):
        for record in records:
            line = json.dumps(record, ensure_ascii=False)
            current.write(line + "\n")
            stamped.write(line + "\n")
            count += 1

    return snapshot, count


def write_checkpoint(payload: Dict[str, Any]) -> None:
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


class PagedTrialsClient:
    def __init__(self, client: httpx.AsyncClient, rate_limit_per_sec: float = 3.0):
        self.client = client
        self.rate_limit_per_sec = rate_limit_per_sec
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def _wait(self) -> None:
        async with self._lock:
            elapsed = time.time() - self._last_request_time
            wait_time = (1.0 / self.rate_limit_per_sec) - elapsed
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self._last_request_time = time.time()

    async def get_json(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self._wait()
        try:
            response = await self.client.get(STUDIES_URL, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.warning("ClinicalTrials request failed: %s", exc)
            return None


def extract_study_records(
    study: Dict[str, Any],
    seed_kind: str,
    seed_name: str,
    drug_lookup: Dict[str, Dict[str, str]],
    disease_lookup: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    protocol = study.get("protocolSection") or {}
    identification = protocol.get("identificationModule") or {}
    status_module = protocol.get("statusModule") or {}
    design_module = protocol.get("designModule") or {}
    conditions_module = protocol.get("conditionsModule") or {}
    arms_module = protocol.get("armsInterventionsModule") or {}
    enrollment_module = design_module.get("enrollmentInfo") or {}

    nct_id = normalize_text(identification.get("nctId"))
    if not nct_id:
        return []

    phases = design_module.get("phases", []) or []
    phase = phases[0] if phases else ""
    status = normalize_text(status_module.get("overallStatus"))
    enrollment = enrollment_module.get("count")
    conditions = [
        normalize_text(item)
        for item in (conditions_module.get("conditions") or [])
        if normalize_text(item)
    ]
    interventions = [
        normalize_text(item.get("name"))
        for item in (arms_module.get("interventions") or [])
        if normalize_text(item.get("name"))
    ]

    matched_drugs = []
    for intervention in interventions:
        lookup_item = drug_lookup.get(normalize_key(intervention))
        if lookup_item:
            matched_drugs.append(lookup_item["drug_name"])
    matched_diseases = []
    for condition in conditions:
        lookup_item = disease_lookup.get(normalize_key(condition))
        if lookup_item:
            matched_diseases.append(lookup_item["disease_name"])

    if seed_kind == "drug":
        drug_names = [seed_name]
        disease_names = matched_diseases or ([conditions[0]] if conditions else [""])
    else:
        disease_names = [seed_name]
        drug_names = matched_drugs or ([interventions[0]] if interventions else [""])

    records: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str]] = set()
    for drug_name in drug_names:
        for disease_name in disease_names:
            key = (nct_id, drug_name, disease_name)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "nct_id": nct_id,
                    "drug_name_local": normalize_text(drug_name),
                    "disease_name": normalize_text(disease_name),
                    "phase": normalize_text(phase),
                    "status": status,
                    "enrollment": enrollment,
                    "conditions": conditions,
                    "interventions": interventions,
                    "source_name": "clinicaltrials",
                    "source_record_id": nct_id,
                    "retrieved_at": utcnow_iso(),
                }
            )
    return records


async def fetch_seed_records(
    client: PagedTrialsClient,
    seed_kind: str,
    seed_name: str,
    max_results: int,
    drug_lookup: Dict[str, Dict[str, str]],
    disease_lookup: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {"pageSize": min(100, max_results), "format": "json"}
    if seed_kind == "drug":
        params["query.intr"] = seed_name
    else:
        params["query.cond"] = seed_name

    next_page_token: Optional[str] = None
    fetched = 0

    while fetched < max_results:
        request_params = dict(params)
        if next_page_token:
            request_params["pageToken"] = next_page_token
        payload = await client.get_json(request_params)
        if not payload:
            break

        studies = payload.get("studies", []) or []
        if not studies:
            break

        for study in studies:
            records.extend(
                extract_study_records(
                    study,
                    seed_kind=seed_kind,
                    seed_name=seed_name,
                    drug_lookup=drug_lookup,
                    disease_lookup=disease_lookup,
                )
            )
        fetched += len(studies)
        next_page_token = normalize_text(payload.get("nextPageToken")) or None
        if not next_page_token:
            break

    return records


async def run(
    drug_limit: Optional[int],
    disease_limit: Optional[int],
    max_results_per_query: int,
) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    drugs = load_local_drugs(limit=drug_limit)
    diseases = load_local_diseases(limit=disease_limit)
    drug_lookup = build_name_lookup(drugs, "drug_name")
    disease_lookup = build_name_lookup(diseases, "disease_name")

    all_records: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=60.0, headers={"Accept": "application/json"}
    ) as raw_client:
        client = PagedTrialsClient(raw_client)
        for drug in drugs:
            all_records.extend(
                await fetch_seed_records(
                    client,
                    seed_kind="drug",
                    seed_name=drug["drug_name"],
                    max_results=max_results_per_query,
                    drug_lookup=drug_lookup,
                    disease_lookup=disease_lookup,
                )
            )
        for disease in diseases:
            all_records.extend(
                await fetch_seed_records(
                    client,
                    seed_kind="disease",
                    seed_name=disease["disease_name"],
                    max_results=max_results_per_query,
                    drug_lookup=drug_lookup,
                    disease_lookup=disease_lookup,
                )
            )

    seen: Set[Tuple[str, str, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for record in all_records:
        key = (
            normalize_text(record.get("nct_id")),
            normalize_text(record.get("drug_name_local")),
            normalize_text(record.get("disease_name")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)

    output_path = RAW_DIR / "trials.jsonl"
    snapshot_path, record_count = write_jsonl_with_snapshot(output_path, deduped)
    checkpoint = {
        "source_name": "clinicaltrials",
        "retrieved_at": utcnow_iso(),
        "input_drug_count": len(drugs),
        "input_disease_count": len(diseases),
        "record_count": record_count,
        "output_path": str(output_path),
        "snapshot_path": str(snapshot_path),
    }
    write_checkpoint(checkpoint)
    return checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch ClinicalTrials.gov raw study records"
    )
    parser.add_argument(
        "--drug-limit", type=int, default=None, help="Limit local drugs"
    )
    parser.add_argument(
        "--disease-limit", type=int, default=None, help="Limit local diseases"
    )
    parser.add_argument(
        "--max-results-per-query",
        type=int,
        default=1000,
        help="Maximum studies to retrieve per drug/disease query",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    summary = asyncio.run(
        run(
            drug_limit=args.drug_limit,
            disease_limit=args.disease_limit,
            max_results_per_query=args.max_results_per_query,
        )
    )
    LOGGER.info(
        "ClinicalTrials extraction complete: %s records", summary["record_count"]
    )


if __name__ == "__main__":
    main()
