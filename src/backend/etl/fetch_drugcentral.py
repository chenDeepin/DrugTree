#!/usr/bin/env python3
"""Fetch DrugCentral raw drug records into data/raw/drugcentral/."""

import argparse
import asyncio
import csv
import gzip
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import httpx

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "drugcentral"
DOWNLOADS_DIR = RAW_DIR / "downloads"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "fetch_drugcentral_checkpoint.json"
DRUGS_FILE = DATA_DIR / "drugs.json"

DOWNLOAD_URL = "https://drugcentral.org/download"
DEFAULT_STRUCTURE_URL = (
    "https://unmtid-dbs.net/download/DrugCentral/2021_09_01/structures.smiles.tsv"
)
DEFAULT_INTERACTIONS_URL = "https://unmtid-dbs.net/download/DrugCentral/2021_09_01/drug.target.interaction.tsv.gz"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: Any) -> str:
    return normalize_text(value).lower()


def normalize_header(value: Any) -> str:
    return normalize_key(value).replace(" ", "_").replace("-", "_")


def normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        output: List[str] = []
        for item in value:
            text = normalize_text(item)
            if text and text not in output:
                output.append(text)
        return output
    text = normalize_text(value)
    return [text] if text else []


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


def write_json_with_snapshot(path: Path, data: Any) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    snapshot = path.with_name(f"{path.stem}_{timestamp_tag()}{path.suffix}")
    snapshot.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return snapshot


def write_checkpoint(payload: Dict[str, Any]) -> None:
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def parse_tsv_rows(raw_bytes: bytes, compressed: bool = False) -> List[Dict[str, str]]:
    content = gzip.decompress(raw_bytes) if compressed else raw_bytes
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    rows: List[Dict[str, str]] = []
    for row in reader:
        normalized = {
            normalize_header(key): normalize_text(value) for key, value in row.items()
        }
        rows.append(normalized)
    return rows


def extract_download_links(html: str) -> List[str]:
    links: List[str] = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        if any(
            token in href.lower() for token in [".tsv", ".csv", ".gz", ".zip", ".sdf"]
        ):
            links.append(str(httpx.URL(DOWNLOAD_URL).join(href)))
    return sorted(dict.fromkeys(links))


async def safe_get_text(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError as exc:
        LOGGER.warning("DrugCentral text request failed for %s: %s", url, exc)
        return None


async def safe_get_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        LOGGER.warning("DrugCentral download failed for %s: %s", url, exc)
        return None


def build_structure_lookup(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        struct_id = normalize_text(row.get("id"))
        name = normalize_text(row.get("inn"))
        if not struct_id or not name:
            continue
        entry = {
            "drugcentral_id": struct_id,
            "name": name,
            "inchikey": normalize_text(row.get("inchikey")),
            "smiles": normalize_text(row.get("smiles")),
            "smiles_canonical": normalize_text(row.get("smiles")),
            "atc_codes": [],
            "synonyms": [],
            "pharmacologic_actions": [],
            "indications": [],
        }
        lookup[normalize_key(name)] = entry
        lookup.setdefault(struct_id, entry)
    return lookup


def merge_interaction_rows(
    lookup: Dict[str, Dict[str, Any]], rows: List[Dict[str, str]]
) -> None:
    for row in rows:
        struct_id = normalize_text(row.get("struct_id"))
        drug_name = normalize_text(row.get("drug_name"))
        entry = lookup.get(struct_id) or lookup.get(normalize_key(drug_name))
        if not entry:
            continue

        target_name = normalize_text(row.get("target_name"))
        gene = normalize_text(row.get("gene"))
        action_type = normalize_text(row.get("action_type"))
        if target_name:
            label = f"{target_name} ({gene})" if gene else target_name
            if label not in entry["pharmacologic_actions"]:
                entry["pharmacologic_actions"].append(label)
        if action_type and action_type not in entry["pharmacologic_actions"]:
            entry["pharmacologic_actions"].append(action_type)


def build_output_records(
    local_drugs: List[Dict[str, str]],
    structure_lookup: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for local in local_drugs:
        entry = structure_lookup.get(normalize_key(local["drug_name"]))
        if not entry:
            continue
        record = dict(entry)
        record["drug_id_local"] = local["drug_id"]
        record["source_name"] = "drugcentral"
        record["source_record_id"] = record["drugcentral_id"]
        record["retrieved_at"] = utcnow_iso()
        key = f"{record['drugcentral_id']}::{normalize_key(record['name'])}"
        if key in seen:
            continue
        seen.add(key)
        records.append(record)

    return records


async def run(limit: Optional[int]) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    local_drugs = load_local_drugs(limit=limit)
    structure_rows: List[Dict[str, str]] = []
    interaction_rows: List[Dict[str, str]] = []
    download_links: List[str] = []

    async with httpx.AsyncClient(timeout=120.0, headers={"Accept": "*/*"}) as client:
        html = await safe_get_text(client, DOWNLOAD_URL)
        if html:
            download_links = extract_download_links(html)

        structure_url = next(
            (
                link
                for link in download_links
                if "structures.smiles.tsv" in link.lower()
            ),
            DEFAULT_STRUCTURE_URL,
        )
        interactions_url = next(
            (
                link
                for link in download_links
                if "drug.target.interaction.tsv.gz" in link.lower()
            ),
            DEFAULT_INTERACTIONS_URL,
        )

        structure_blob = await safe_get_bytes(client, structure_url)
        if structure_blob:
            structure_path = DOWNLOADS_DIR / Path(httpx.URL(structure_url).path).name
            structure_path.write_bytes(structure_blob)
            structure_rows = parse_tsv_rows(structure_blob, compressed=False)

        interactions_blob = await safe_get_bytes(client, interactions_url)
        if interactions_blob:
            interactions_path = (
                DOWNLOADS_DIR / Path(httpx.URL(interactions_url).path).name
            )
            interactions_path.write_bytes(interactions_blob)
            interaction_rows = parse_tsv_rows(interactions_blob, compressed=True)

    link_manifest_path = RAW_DIR / "download_links.json"
    link_manifest_snapshot = write_json_with_snapshot(
        link_manifest_path,
        {
            "source_name": "drugcentral",
            "retrieved_at": utcnow_iso(),
            "links": download_links,
        },
    )

    structure_lookup = build_structure_lookup(structure_rows)
    merge_interaction_rows(structure_lookup, interaction_rows)
    records = build_output_records(local_drugs, structure_lookup)

    output_path = RAW_DIR / "drugs.json"
    output_snapshot = write_json_with_snapshot(output_path, records)
    checkpoint = {
        "source_name": "drugcentral",
        "retrieved_at": utcnow_iso(),
        "input_drug_count": len(local_drugs),
        "record_count": len(records),
        "download_links_path": str(link_manifest_path),
        "download_links_snapshot_path": str(link_manifest_snapshot),
        "structure_row_count": len(structure_rows),
        "interaction_row_count": len(interaction_rows),
        "output_path": str(output_path),
        "snapshot_path": str(output_snapshot),
    }
    write_checkpoint(checkpoint)
    return checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch DrugCentral raw drug records")
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
    LOGGER.info("DrugCentral extraction complete: %s records", summary["record_count"])


if __name__ == "__main__":
    main()
