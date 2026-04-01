#!/usr/bin/env python3
"""Fetch RxNorm normalization records into raw JSONL with request pacing."""

import argparse
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import httpx

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "rxnorm"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "fetch_rxnorm_checkpoint.json"
DRUGS_FILE = DATA_DIR / "drugs.json"

DRUGS_URL = "https://rxnav.nlm.nih.gov/REST/drugs.json"
ALL_RELATED_URL = "https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/allrelated.json"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


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
        if not name:
            continue
        items.append(
            {
                "drug_id": normalize_text(drug.get("id")),
                "drug_name": name,
            }
        )

    if limit is not None and limit > 0:
        return items[:limit]
    return items


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


class RateLimitedClient:
    def __init__(self, client: httpx.AsyncClient, delay_seconds: float = 0.1):
        self.client = client
        self.delay_seconds = delay_seconds
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def get_json(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        async with self._lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.delay_seconds:
                await asyncio.sleep(self.delay_seconds - elapsed)
            self._last_request_time = time.time()

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.warning("RxNorm request failed for %s: %s", url, exc)
            return None


def split_brand_from_name(name: str) -> Tuple[str, str]:
    text = normalize_text(name)
    match = re.search(r"\[(.+?)\]", text)
    if match:
        generic = text.split("[")[0].strip()
        return match.group(1).strip(), generic
    return "", text


def extract_related_names(payload: Any) -> Tuple[str, str, List[str]]:
    brand_names: List[str] = []
    generic_names: List[str] = []
    synonyms: List[str] = []

    groups = ((payload or {}).get("allRelatedGroup") or {}).get("conceptGroup") or []
    for group in groups:
        tty = normalize_text(group.get("tty"))
        for concept in group.get("conceptProperties", []) or []:
            name = normalize_text(concept.get("name"))
            synonym = normalize_text(concept.get("synonym"))
            if synonym and synonym not in synonyms:
                synonyms.append(synonym)
            if name and name not in synonyms:
                synonyms.append(name)

            if tty == "BN" and name and name not in brand_names:
                brand_names.append(name)
            if tty in {"IN", "PIN", "MIN"} and name and name not in generic_names:
                generic_names.append(name)

    return (
        brand_names[0] if brand_names else "",
        generic_names[0] if generic_names else "",
        synonyms,
    )


def parse_drugs_payload(
    payload: Any,
    drug: Dict[str, str],
    related_lookup: Dict[str, Tuple[str, str, List[str]]],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str]] = set()
    groups = ((payload or {}).get("drugGroup") or {}).get("conceptGroup") or []

    for group in groups:
        tty = normalize_text(group.get("tty"))
        for concept in group.get("conceptProperties", []) or []:
            rxcui = normalize_text(concept.get("rxcui"))
            if not rxcui:
                continue
            brand_from_name, generic_from_name = split_brand_from_name(
                concept.get("name") or concept.get("synonym") or ""
            )
            related_brand, related_generic, related_synonyms = related_lookup.get(
                rxcui, ("", "", [])
            )
            brand_name = related_brand or brand_from_name
            generic_name = related_generic or generic_from_name
            synonym = normalize_text(concept.get("synonym")) or normalize_text(
                concept.get("name")
            )
            if not synonym and related_synonyms:
                synonym = related_synonyms[0]

            key = (drug["drug_name"], rxcui, tty)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "drug_name_local": drug["drug_name"],
                    "drug_id_local": drug["drug_id"],
                    "rxcui": rxcui,
                    "brand_name": brand_name,
                    "generic_name": generic_name,
                    "synonym": synonym,
                    "tty": tty,
                    "source_name": "rxnorm",
                    "source_record_id": rxcui,
                    "retrieved_at": utcnow_iso(),
                }
            )
    return records


async def run(limit: Optional[int]) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    drugs = load_local_drugs(limit=limit)
    records: List[Dict[str, Any]] = []
    related_cache: Dict[str, Tuple[str, str, List[str]]] = {}

    async with httpx.AsyncClient(
        timeout=45.0, headers={"Accept": "application/json"}
    ) as client:
        rate_client = RateLimitedClient(client)

        for drug in drugs:
            payload = await rate_client.get_json(DRUGS_URL, {"name": drug["drug_name"]})
            groups = ((payload or {}).get("drugGroup") or {}).get("conceptGroup") or []
            rxcuis = {
                normalize_text(concept.get("rxcui"))
                for group in groups
                for concept in (group.get("conceptProperties") or [])
                if normalize_text(concept.get("rxcui"))
            }

            for rxcui in sorted(rxcuis):
                if rxcui in related_cache:
                    continue
                related_payload = await rate_client.get_json(
                    ALL_RELATED_URL.format(rxcui=rxcui)
                )
                related_cache[rxcui] = extract_related_names(related_payload)

            records.extend(parse_drugs_payload(payload, drug, related_cache))

    output_path = RAW_DIR / "drug_names.jsonl"
    snapshot_path, record_count = write_jsonl_with_snapshot(output_path, records)
    checkpoint = {
        "source_name": "rxnorm",
        "retrieved_at": utcnow_iso(),
        "input_drug_count": len(drugs),
        "record_count": record_count,
        "output_path": str(output_path),
        "snapshot_path": str(snapshot_path),
    }
    write_checkpoint(checkpoint)
    return checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch RxNorm normalization records")
    parser.add_argument("--limit", type=int, default=None, help="Limit local drugs")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    summary = asyncio.run(run(limit=args.limit))
    LOGGER.info("RxNorm extraction complete: %s records", summary["record_count"])


if __name__ == "__main__":
    main()
