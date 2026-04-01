#!/usr/bin/env python3
"""Fetch CTD gene-disease associations into canonical raw JSONL rows."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "ctd"
DOWNLOADS_DIR = RAW_DIR / "downloads"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "fetch_ctd_checkpoint.json"
DISEASES_FILE = DATA_DIR / "diseases.json"

DOWNLOAD_URL = "https://ctdbase.org/reports/CTD_genes_diseases.tsv.gz"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: Any) -> str:
    return normalize_text(value).lower()


def normalize_header(value: Any) -> str:
    value = normalize_key(value).strip()
    value = value.lstrip("#").strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


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


def load_local_disease_lookup() -> Dict[str, Dict[str, str]]:
    if not DISEASES_FILE.exists():
        LOGGER.warning("Canonical diseases file missing: %s", DISEASES_FILE)
        return {}

    payload = json.loads(DISEASES_FILE.read_text(encoding="utf-8"))
    diseases = payload.get("diseases", []) if isinstance(payload, dict) else payload
    lookup: Dict[str, Dict[str, str]] = {}

    for disease in diseases:
        if not isinstance(disease, dict):
            continue

        disease_id = normalize_text(disease.get("id"))
        if not disease_id:
            continue

        entry = {
            "disease_id": disease_id,
            "disease_name": normalize_text(disease.get("canonical_name")) or disease_id,
        }
        values = [
            disease.get("id"),
            disease.get("canonical_name"),
            disease.get("mondo_id"),
            disease.get("mesh_id"),
            disease.get("doid_id"),
            disease.get("efo_id"),
        ]
        values.extend(disease.get("synonyms", []) or [])

        for value in values:
            key = normalize_key(value).replace("_", ":") if value else ""
            if key:
                lookup.setdefault(key, entry)
            plain_key = normalize_key(value)
            if plain_key:
                lookup.setdefault(plain_key, entry)

    return lookup


def parse_ctd_rows(
    raw_bytes: bytes, disease_lookup: Dict[str, Dict[str, str]]
) -> List[Dict[str, Any]]:
    content = gzip.decompress(raw_bytes) if raw_bytes[:2] == b"\x1f\x8b" else raw_bytes
    text = content.decode("utf-8", errors="replace")

    header: Optional[List[str]] = None
    records: List[Dict[str, Any]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if header is None:
            candidate = line.lstrip("#").strip()
            if not candidate:
                continue
            columns = [normalize_text(column) for column in candidate.split("	")]
            normalized_header = [normalize_header(column) for column in columns]
            if {"genesymbol", "diseasename", "diseaseid"}.issubset(
                set(normalized_header)
            ):
                header = normalized_header
            continue

        if line.startswith("#") and "	" not in line:
            continue

        columns = [normalize_text(column) for column in line.split("	")]
        if not columns:
            continue

        row = {
            header[index]: normalize_text(columns[index])
            if index < len(columns)
            else ""
            for index in range(len(header))
        }
        target_symbol = (
            normalize_text(row.get("genesymbol") or row.get("gene_symbol"))
            .lstrip("#")
            .upper()
        )
        disease_name = normalize_text(row.get("diseasename") or row.get("disease_name"))
        disease_source_id = normalize_text(
            row.get("diseaseid") or row.get("disease_id")
        )
        direct_evidence = normalize_text(
            row.get("directevidence") or row.get("direct_evidence")
        )

        if not target_symbol or not disease_name or not disease_source_id:
            continue

        canonical_disease = (
            disease_lookup.get(normalize_key(disease_source_id).replace("_", ":"))
            or disease_lookup.get(normalize_key(disease_source_id))
            or disease_lookup.get(normalize_key(disease_name))
        )
        if canonical_disease is None:
            continue

        records.append(
            {
                "target_id": target_symbol,
                "target_symbol": target_symbol,
                "disease_id": canonical_disease["disease_id"],
                "disease_name": canonical_disease["disease_name"],
                "disease_source_id": disease_source_id,
                "evidence_type": "direct" if direct_evidence else "inferred",
                "source_name": "ctd",
                "source_record_id": f"{target_symbol}:{disease_source_id}",
                "retrieved_at": utcnow_iso(),
            }
        )

    return records


async def safe_get_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        LOGGER.warning("CTD download failed for %s: %s", url, exc)
        return None


async def run() -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    output_path = RAW_DIR / "disease_edges.jsonl"
    checkpoint: Dict[str, Any] = {
        "source_name": "ctd",
        "retrieved_at": utcnow_iso(),
        "download_url": DOWNLOAD_URL,
        "record_count": 0,
    }

    disease_lookup = load_local_disease_lookup()

    async with httpx.AsyncClient(timeout=120.0, headers={"Accept": "*/*"}) as client:
        content = await safe_get_bytes(client, DOWNLOAD_URL)

    if not content:
        checkpoint["status"] = "preserved_previous_outputs"
        if output_path.exists():
            checkpoint["output_path"] = str(output_path)
        write_checkpoint(checkpoint)
        return checkpoint

    filename = Path(httpx.URL(DOWNLOAD_URL).path).name or "CTD_genes_diseases.tsv.gz"
    download_path = DOWNLOADS_DIR / filename
    download_path.write_bytes(content)
    checkpoint["downloaded_file"] = str(download_path)

    records = parse_ctd_rows(content, disease_lookup)
    if not records:
        checkpoint["status"] = "preserved_previous_outputs"
        if output_path.exists():
            checkpoint["output_path"] = str(output_path)
        write_checkpoint(checkpoint)
        return checkpoint

    snapshot_path, record_count = write_jsonl_with_snapshot(output_path, records)
    checkpoint.update(
        {
            "status": "success",
            "record_count": record_count,
            "output_path": str(output_path),
            "snapshot_path": str(snapshot_path),
        }
    )
    write_checkpoint(checkpoint)
    return checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch CTD gene-disease associations")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    summary = asyncio.run(run())
    LOGGER.info("CTD extraction complete: %s records", summary["record_count"])


if __name__ == "__main__":
    main()
