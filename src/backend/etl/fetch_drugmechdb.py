#!/usr/bin/env python3
"""Fetch DrugMechDB mechanism paths into raw JSONL."""

import argparse
import asyncio
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import httpx

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "drugmechdb"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "fetch_drugmechdb_checkpoint.json"

DOWNLOADS_URL = "https://drugmechdb.org/downloads"
API_URL = "https://drugmechdb.org/api"
FALLBACK_JSON_URL = (
    "https://raw.githubusercontent.com/SuLab/DrugMechDB/main/indication_paths.json"
)
FALLBACK_ZIP_URL = "https://raw.githubusercontent.com/SuLab/DrugMechDB/main/dmdb_indications_grouped.zip"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: Any) -> str:
    return normalize_text(value).lower()


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


async def safe_get_text(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError as exc:
        LOGGER.warning("DrugMechDB text request failed for %s: %s", url, exc)
        return None


async def safe_get_json(client: httpx.AsyncClient, url: str) -> Optional[Any]:
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        LOGGER.warning("DrugMechDB JSON request failed for %s: %s", url, exc)
        return None

    try:
        return response.json()
    except ValueError as exc:
        LOGGER.warning("DrugMechDB JSON parse failed for %s: %s", url, exc)
        return None


async def safe_get_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        LOGGER.warning("DrugMechDB download failed for %s: %s", url, exc)
        return None


def extract_download_links(html: str) -> List[str]:
    links: List[str] = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        href_lower = href.lower()
        if any(
            token in href_lower
            for token in [
                ".json",
                ".zip",
                ".csv",
                ".tsv",
                ".yaml",
                ".yml",
                "indication_paths",
                "drugmechdb",
            ]
        ):
            links.append(str(httpx.URL(DOWNLOADS_URL).join(href)))
    return sorted(dict.fromkeys(links))


def normalize_reference_urls(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = normalize_text(value)
        return [text] if text else []
    if isinstance(value, list):
        output: List[str] = []
        for item in value:
            text = normalize_text(item)
            if text and text not in output:
                output.append(text)
        return output
    if isinstance(value, dict):
        output = []
        for item in value.values():
            text = normalize_text(item)
            if text and text not in output:
                output.append(text)
        return output
    return []


def iter_path_entries(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    if isinstance(payload.get("nodes"), list) and isinstance(
        payload.get("links"), list
    ):
        return [payload]

    for key in ["paths", "data", "items", "records", "results", "indications"]:
        section = payload.get(key)
        if isinstance(section, list):
            return [item for item in section if isinstance(item, dict)]
        if isinstance(section, dict):
            output: List[Dict[str, Any]] = []
            for path_id, value in section.items():
                if not isinstance(value, dict):
                    continue
                entry = dict(value)
                entry.setdefault("path_id", normalize_text(path_id))
                output.append(entry)
            if output:
                return output

    output = []
    for path_id, value in payload.items():
        if not isinstance(value, dict):
            continue
        if not isinstance(value.get("nodes"), list) or not isinstance(
            value.get("links"), list
        ):
            continue
        entry = dict(value)
        entry.setdefault("path_id", normalize_text(path_id))
        output.append(entry)
    return output


def parse_json_payload(payload: Any, source_url: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for entry in iter_path_entries(payload):
        if not isinstance(entry.get("nodes"), list) or not isinstance(
            entry.get("links"), list
        ):
            continue
        path_entry = dict(entry)
        path_entry["_source_url"] = source_url
        entries.append(path_entry)
    return entries


def parse_zip_payload(blob: bytes, source_url: str) -> List[Dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        LOGGER.warning("DrugMechDB zip parse failed for %s: %s", source_url, exc)
        return []

    entries: List[Dict[str, Any]] = []
    for name in archive.namelist():
        name_lower = name.lower()
        if not name_lower.endswith(".json"):
            continue
        try:
            payload = json.loads(archive.read(name).decode("utf-8", errors="replace"))
        except (KeyError, ValueError) as exc:
            LOGGER.warning(
                "DrugMechDB zip member parse failed for %s#%s: %s",
                source_url,
                name,
                exc,
            )
            continue
        entries.extend(parse_json_payload(payload, f"{source_url}#{name}"))
    if not entries:
        LOGGER.warning(
            "DrugMechDB zip at %s did not contain parseable JSON paths", source_url
        )
    return entries


def build_download_candidates(download_links: List[str]) -> List[str]:
    candidates = list(download_links)
    candidates.extend([FALLBACK_JSON_URL, FALLBACK_ZIP_URL])
    return sorted(dict.fromkeys(candidates))


def build_node_lookup(path_entry: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    for node in path_entry.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        node_id = normalize_text(node.get("id"))
        if not node_id:
            continue
        lookup[node_id] = {
            "id": node_id,
            "label": normalize_text(node.get("label")),
            "name": normalize_text(node.get("name")),
        }
    return lookup


def extract_graph_block(path_entry: Dict[str, Any]) -> Dict[str, Any]:
    graph_value = path_entry.get("graph")
    if isinstance(graph_value, dict):
        return dict(graph_value)
    return {}


def resolve_drug_node_id(
    path_entry: Dict[str, Any], nodes_by_id: Dict[str, Dict[str, str]]
) -> str:
    graph = extract_graph_block(path_entry)
    candidates = [
        graph.get("drugbank"),
        graph.get("drug_mesh"),
        graph.get("drug_id"),
        path_entry.get("drugbank"),
        path_entry.get("drug_mesh"),
    ]
    for candidate in candidates:
        node_id = normalize_text(candidate)
        if node_id and node_id in nodes_by_id:
            return node_id
    for node_id, node in nodes_by_id.items():
        if normalize_key(node.get("label")) == "drug":
            return node_id
    return normalize_text(
        graph.get("drugbank") or graph.get("drug_mesh") or graph.get("drug_id")
    )


def collect_pathway_names(
    nodes_by_id: Dict[str, Dict[str, str]], links: List[Dict[str, Any]]
) -> List[str]:
    pathway_ids: List[str] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        for endpoint in [link.get("source"), link.get("target")]:
            node_id = normalize_text(endpoint)
            node = nodes_by_id.get(node_id, {})
            label = normalize_key(node.get("label"))
            if label not in {"pathway", "biologicalprocess", "biological_process"}:
                continue
            if node_id and node_id not in pathway_ids:
                pathway_ids.append(node_id)

    pathways: List[str] = []
    for node_id in pathway_ids:
        name = normalize_text(nodes_by_id.get(node_id, {}).get("name"))
        if name and name not in pathways:
            pathways.append(name)
    return pathways


def collect_target_node_ids(
    drug_node_id: str,
    nodes_by_id: Dict[str, Dict[str, str]],
    links: List[Dict[str, Any]],
) -> List[str]:
    targets: List[str] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        source_id = normalize_text(link.get("source"))
        target_id = normalize_text(link.get("target"))
        if source_id == drug_node_id:
            node = nodes_by_id.get(target_id, {})
            if (
                normalize_key(node.get("label")) == "protein"
                and target_id not in targets
            ):
                targets.append(target_id)
        if target_id == drug_node_id:
            node = nodes_by_id.get(source_id, {})
            if (
                normalize_key(node.get("label")) == "protein"
                and source_id not in targets
            ):
                targets.append(source_id)

    if targets:
        return targets

    for node_id, node in nodes_by_id.items():
        if normalize_key(node.get("label")) == "protein" and node_id not in targets:
            targets.append(node_id)
    return targets


def extract_drug_identifier(
    path_entry: Dict[str, Any],
    nodes_by_id: Dict[str, Dict[str, str]],
    drug_node_id: str,
) -> str:
    graph = extract_graph_block(path_entry)
    return normalize_text(
        graph.get("drugbank")
        or graph.get("drug_mesh")
        or path_entry.get("drugbank")
        or path_entry.get("drug_mesh")
        or drug_node_id
    )


def extract_drug_name(
    path_entry: Dict[str, Any],
    nodes_by_id: Dict[str, Dict[str, str]],
    drug_node_id: str,
) -> str:
    graph = extract_graph_block(path_entry)
    return normalize_text(
        graph.get("drug") or nodes_by_id.get(drug_node_id, {}).get("name") or ""
    )


def extract_disease_name(
    path_entry: Dict[str, Any], nodes_by_id: Dict[str, Dict[str, str]]
) -> str:
    graph = extract_graph_block(path_entry)
    if normalize_text(graph.get("disease")):
        return normalize_text(graph.get("disease"))
    for node in nodes_by_id.values():
        if normalize_key(node.get("label")) == "disease":
            return normalize_text(node.get("name"))
    return ""


def extract_mechanism_type(links: List[Dict[str, Any]]) -> str:
    predicates: List[str] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        predicate = normalize_text(link.get("key") or link.get("predicate"))
        if predicate and predicate not in predicates:
            predicates.append(predicate)
    return " | ".join(predicates)


def infer_target_symbol(node_id: str, target_name: str) -> str:
    accession = normalize_text(node_id.split(":", 1)[-1] if ":" in node_id else node_id)
    if accession:
        return accession
    return normalize_text(target_name)


def infer_evidence_level(reference_urls: List[str]) -> str:
    return "literature_curated" if reference_urls else "curated_path"


def build_records_from_path(
    path_entry: Dict[str, Any],
    retrieved_at: str,
) -> List[Dict[str, Any]]:
    nodes_by_id = build_node_lookup(path_entry)
    links = [
        link for link in path_entry.get("links", []) or [] if isinstance(link, dict)
    ]
    if not nodes_by_id or not links:
        return []

    drug_node_id = resolve_drug_node_id(path_entry, nodes_by_id)
    target_node_ids = collect_target_node_ids(drug_node_id, nodes_by_id, links)
    if not target_node_ids:
        return []

    pathway = " | ".join(collect_pathway_names(nodes_by_id, links))
    mechanism_type = extract_mechanism_type(links)
    reference_urls = normalize_reference_urls(path_entry.get("reference"))
    source_url = (
        reference_urls[0]
        if reference_urls
        else normalize_text(path_entry.get("_source_url"))
    )
    evidence_level = infer_evidence_level(reference_urls)
    drug_id = extract_drug_identifier(path_entry, nodes_by_id, drug_node_id)
    drug_name = extract_drug_name(path_entry, nodes_by_id, drug_node_id)
    disease_name = extract_disease_name(path_entry, nodes_by_id)

    records: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str, str]] = set()
    for target_node_id in target_node_ids:
        target = nodes_by_id.get(target_node_id, {})
        target_name = normalize_text(target.get("name"))
        target_symbol = infer_target_symbol(target_node_id, target_name)
        key = (drug_id, target_symbol, pathway, disease_name, mechanism_type)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "drug_id": drug_id,
                "drug_name": drug_name,
                "target_symbol": target_symbol,
                "target_name": target_name,
                "pathway": pathway,
                "disease_name": disease_name,
                "mechanism_type": mechanism_type,
                "evidence_level": evidence_level,
                "source_url": source_url,
                "retrieved_at": retrieved_at,
            }
        )
    return records


async def fetch_api_entries(
    client: httpx.AsyncClient,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    entries: List[Dict[str, Any]] = []
    attempted_urls: List[str] = []

    for url in [
        API_URL,
        f"{API_URL}/paths",
        f"{API_URL}/indications",
        f"{API_URL}/indication_paths",
    ]:
        attempted_urls.append(url)
        payload = await safe_get_json(client, url)
        if payload is None:
            continue
        entries.extend(parse_json_payload(payload, url))
        if entries:
            break

    return entries, attempted_urls


async def fetch_download_entries(
    client: httpx.AsyncClient,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    attempted_urls: List[str] = [DOWNLOADS_URL]
    entries: List[Dict[str, Any]] = []

    html = await safe_get_text(client, DOWNLOADS_URL)
    download_links = extract_download_links(html) if html else []
    candidate_urls = build_download_candidates(download_links)

    for url in candidate_urls:
        attempted_urls.append(url)
        url_lower = url.lower()
        if url_lower.endswith(".json"):
            payload = await safe_get_json(client, url)
            if payload is None:
                continue
            entries.extend(parse_json_payload(payload, url))
        elif url_lower.endswith(".zip"):
            blob = await safe_get_bytes(client, url)
            if blob is None:
                continue
            entries.extend(parse_zip_payload(blob, url))
        else:
            text = await safe_get_text(client, url)
            if text and "{" in text:
                try:
                    payload = json.loads(text)
                except ValueError:
                    LOGGER.warning("DrugMechDB unsupported download format at %s", url)
                    continue
                entries.extend(parse_json_payload(payload, url))
        if entries:
            break

    return entries, attempted_urls


async def run(limit: Optional[int]) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    retrieved_at = utcnow_iso()
    entries: List[Dict[str, Any]] = []
    api_attempts: List[str] = []
    download_attempts: List[str] = []
    selected_source = ""

    async with httpx.AsyncClient(
        timeout=90.0,
        headers={"Accept": "application/json, text/html;q=0.9, */*;q=0.8"},
    ) as client:
        entries, api_attempts = await fetch_api_entries(client)
        if entries:
            selected_source = "api"
        else:
            entries, download_attempts = await fetch_download_entries(client)
            if entries:
                selected_source = "download"

    records: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str, str]] = set()
    for entry in entries:
        for record in build_records_from_path(entry, retrieved_at=retrieved_at):
            key = (
                normalize_text(record.get("drug_id")),
                normalize_text(record.get("target_symbol")),
                normalize_text(record.get("pathway")),
                normalize_text(record.get("disease_name")),
                normalize_text(record.get("mechanism_type")),
            )
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
            if limit is not None and limit > 0 and len(records) >= limit:
                break
        if limit is not None and limit > 0 and len(records) >= limit:
            break

    if not records:
        LOGGER.warning(
            "DrugMechDB data was unavailable or unparseable; writing empty output with checkpoint"
        )

    output_path = RAW_DIR / "mechanism_paths.jsonl"
    output_snapshot, record_count = write_jsonl_with_snapshot(output_path, records)
    checkpoint = {
        "source_name": "drugmechdb",
        "retrieved_at": retrieved_at,
        "selected_source": selected_source or "none",
        "path_entry_count": len(entries),
        "record_count": record_count,
        "limit": limit,
        "api_attempts": api_attempts,
        "download_attempts": download_attempts,
        "output_path": str(output_path),
        "snapshot_path": str(output_snapshot),
    }
    write_checkpoint(checkpoint)
    return checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch DrugMechDB mechanism paths")
    parser.add_argument("--limit", type=int, default=None, help="Limit output records")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    summary = asyncio.run(run(limit=args.limit))
    LOGGER.info("DrugMechDB extraction complete: %s records", summary["record_count"])


if __name__ == "__main__":
    main()
