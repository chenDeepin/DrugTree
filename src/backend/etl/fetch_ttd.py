#!/usr/bin/env python3
"""Best-effort TTD raw extraction into target and edge JSON artifacts."""

import argparse
import asyncio
import csv
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "ttd"
DOWNLOADS_DIR = RAW_DIR / "downloads"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "fetch_ttd_checkpoint.json"

TEMPLATE_FILES_URL = "https://ttd.idrblab.cn/api/ttd/api-template-file"
DOWNLOAD_PAGES = [
    "https://idrblab.org/ttd/download",
    "https://db.idrblab.net/ttd/download",
    "https://ttd.idrblab.cn/full-data-download",
]
DOWNLOAD_BASES = [
    "https://ttd.idrblab.cn/files/",
    "https://ttd.idrblab.cn/files/download/",
    "https://ttd.idrblab.cn/files/full-data-download/",
    "https://ttd.idrblab.cn/download/",
]

TARGET_ID_FIELDS = {
    "ttd_target_id",
    "target_id",
    "targetid",
    "ttd_targetid",
    "target_no",
}
TARGET_METADATA_FIELDS = {
    "gene_symbol",
    "symbol",
    "genesymbol",
    "gene",
    "gene_name",
    "name",
    "target_name",
    "uniprot_id",
    "uniprot",
    "uniprot_accession",
}
DRUG_EDGE_FIELDS = {"drug_name", "drug", "drugname"}
DISEASE_EDGE_FIELDS = {"disease_name", "disease", "indication", "diseaseexp"}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_header(value: Any) -> str:
    return normalize_text(value).lower().replace(" ", "_").replace("-", "_")


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


def first_value(row: Dict[str, Any], names: Iterable[str]) -> str:
    for name in names:
        value = normalize_text(row.get(name))
        if value:
            return value
    return ""


def to_bool(value: Any) -> bool:
    text = normalize_text(value).lower()
    return text in {"1", "true", "yes", "validated", "approved", "y"}


def parse_table_text(text: str) -> List[Dict[str, str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    delimiter = "\t" if "\t" in lines[0] else ","
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    rows: List[Dict[str, str]] = []
    for row in reader:
        normalized = {
            normalize_header(key): normalize_text(value) for key, value in row.items()
        }
        rows.append(normalized)
    return rows


def rows_match_supported_column_families(rows: List[Dict[str, str]]) -> bool:
    if not rows:
        return False

    headers = {key for row in rows for key in row.keys() if key}
    if not headers.intersection(TARGET_ID_FIELDS):
        return False

    return any(
        headers.intersection(field_family)
        for field_family in (
            TARGET_METADATA_FIELDS,
            DRUG_EDGE_FIELDS,
            DISEASE_EDGE_FIELDS,
        )
    )


def classify_parseable_text(
    filename: str, text: str
) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]]:
    prefix = text.lstrip()[:256].lower()
    if not prefix or prefix.startswith("<html") or prefix.startswith("<!doctype html"):
        return None

    rows = parse_table_text(text)
    if not rows or not rows_match_supported_column_families(rows):
        return None

    classified = classify_rows(filename, rows)
    if not any(classified):
        return None

    return classified


def extract_records_from_download(
    filename: str, content: bytes
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    targets: List[Dict[str, Any]] = []
    drug_edges: List[Dict[str, Any]] = []
    disease_edges: List[Dict[str, Any]] = []
    parseable = False

    if zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                try:
                    data = archive.read(member).decode("utf-8", errors="replace")
                except KeyError:
                    continue

                classified = classify_parseable_text(member, data)
                if classified is None:
                    continue

                parseable = True
                t_rows, d_rows, di_rows = classified
                targets.extend(t_rows)
                drug_edges.extend(d_rows)
                disease_edges.extend(di_rows)

        return targets, drug_edges, disease_edges, parseable

    if filename.lower().endswith((".txt", ".csv", ".tsv")):
        classified = classify_parseable_text(
            filename, content.decode("utf-8", errors="replace")
        )
        if classified is None:
            return [], [], [], False

        t_rows, d_rows, di_rows = classified
        return t_rows, d_rows, di_rows, True

    return [], [], [], False


def classify_rows(
    filename: str, rows: List[Dict[str, str]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    targets: List[Dict[str, Any]] = []
    drug_edges: List[Dict[str, Any]] = []
    disease_edges: List[Dict[str, Any]] = []
    lower_name = filename.lower()

    for row in rows:
        target_id = first_value(
            row, ["ttd_target_id", "target_id", "targetid", "ttd_targetid", "target_no"]
        )
        gene_symbol = first_value(row, ["gene_symbol", "symbol", "genesymbol", "gene"])
        gene_name = first_value(row, ["gene_name", "name", "target_name"])
        uniprot_id = first_value(row, ["uniprot_id", "uniprot", "uniprot_accession"])
        ensembl_id = first_value(row, ["ensembl_id", "ensembl_gene_id"])
        pathway_value = first_value(
            row, ["pathway_ids", "pathway_id", "pathway", "pathways"]
        )
        drug_count = first_value(
            row, ["drug_count", "approved_drug_count", "count_of_drugs"]
        )
        validated = first_value(
            row, ["is_validated", "validated", "validation_status", "target_status"]
        )
        drug_name = first_value(row, ["drug_name", "drug", "drugname"])
        clinical_status = first_value(
            row, ["clinical_status", "status", "approval_status"]
        )
        disease_name = first_value(
            row, ["disease_name", "disease", "indication", "diseaseexp"]
        )

        if (
            target_id
            and (gene_symbol or gene_name or uniprot_id)
            and ("target" in lower_name or not drug_name and not disease_name)
        ):
            targets.append(
                {
                    "ttd_target_id": target_id,
                    "gene_symbol": gene_symbol,
                    "gene_name": gene_name,
                    "uniprot_id": uniprot_id,
                    "ensembl_id": ensembl_id,
                    "pathway_ids": [
                        item.strip()
                        for item in pathway_value.split(";")
                        if item.strip()
                    ]
                    if pathway_value
                    else [],
                    "drug_count": int(drug_count) if drug_count.isdigit() else None,
                    "is_validated": to_bool(validated),
                    "source_name": "ttd",
                    "source_record_id": target_id,
                    "retrieved_at": utcnow_iso(),
                }
            )

        if (
            target_id
            and drug_name
            and ("drugtarget" in lower_name or "drug" in lower_name)
        ):
            drug_edges.append(
                {
                    "ttd_target_id": target_id,
                    "drug_name": drug_name,
                    "drug_id_local": "",
                    "clinical_status": clinical_status,
                    "source_name": "ttd",
                    "source_record_id": f"{target_id}:{drug_name}",
                    "retrieved_at": utcnow_iso(),
                }
            )

        if (
            target_id
            and disease_name
            and ("disease" in lower_name or "biomarker" in lower_name)
        ):
            disease_edges.append(
                {
                    "ttd_target_id": target_id,
                    "disease_name": disease_name,
                    "source_name": "ttd",
                    "source_record_id": f"{target_id}:{disease_name}",
                    "retrieved_at": utcnow_iso(),
                }
            )

    return targets, drug_edges, disease_edges


async def safe_get_json(client: httpx.AsyncClient, url: str) -> Optional[Any]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.warning("TTD JSON request failed for %s: %s", url, exc)
        return None


async def safe_get_text(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError as exc:
        LOGGER.warning("TTD text request failed for %s: %s", url, exc)
        return None


async def safe_get_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        LOGGER.warning("TTD download failed for %s: %s", url, exc)
        return None


async def discover_downloads(client: httpx.AsyncClient) -> List[str]:
    discovered: List[str] = []
    payload = await safe_get_json(client, TEMPLATE_FILES_URL)
    for item in (payload or {}).get("result") or []:
        filename = normalize_text(item.get("filename"))
        if not filename:
            continue
        for base in DOWNLOAD_BASES:
            discovered.append(base + filename)

    for page in DOWNLOAD_PAGES:
        text = await safe_get_text(client, page)
        if not text:
            continue
        for marker in ['href="', "href='"]:
            parts = text.split(marker)
            for part in parts[1:]:
                href = part.split(marker[-1], 1)[0]
                if any(
                    token in href.lower()
                    for token in [".xlsx", ".txt", ".csv", ".tsv", ".zip"]
                ):
                    discovered.append(str(httpx.URL(page).join(href)))

    return sorted(dict.fromkeys(discovered))


async def run(download_limit: int) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    targets: List[Dict[str, Any]] = []
    drug_edges: List[Dict[str, Any]] = []
    disease_edges: List[Dict[str, Any]] = []
    downloaded_files: List[str] = []
    parseable_download_count = 0
    failed_or_unparseable_download_count = 0

    async with httpx.AsyncClient(timeout=120.0, headers={"Accept": "*/*"}) as client:
        candidate_urls = await discover_downloads(client)
        manifest_path = RAW_DIR / "download_links.json"
        manifest_snapshot = write_json_with_snapshot(
            manifest_path,
            {
                "source_name": "ttd",
                "retrieved_at": utcnow_iso(),
                "links": candidate_urls,
            },
        )

        attempted_urls = candidate_urls[: max(0, download_limit)]

        for url in attempted_urls:
            content = await safe_get_bytes(client, url)
            if not content:
                failed_or_unparseable_download_count += 1
                continue

            filename = Path(httpx.URL(url).path).name or f"ttd_{len(downloaded_files)}"
            target_path = DOWNLOADS_DIR / filename
            target_path.write_bytes(content)
            downloaded_files.append(str(target_path))

            t_rows, d_rows, di_rows, parseable = extract_records_from_download(
                filename, content
            )
            if parseable:
                parseable_download_count += 1
                targets.extend(t_rows)
                drug_edges.extend(d_rows)
                disease_edges.extend(di_rows)
            else:
                failed_or_unparseable_download_count += 1

    targets_path = RAW_DIR / "targets.json"
    drug_edges_path = RAW_DIR / "drug_target_edges.json"
    disease_edges_path = RAW_DIR / "disease_target_edges.json"

    if not candidate_urls:
        status = "no_candidate_urls"
    elif parseable_download_count == 0:
        status = "downloaded_but_unparseable"
    elif parseable_download_count < len(attempted_urls):
        status = "partial"
    else:
        status = "success"

    checkpoint: Dict[str, Any] = {
        "source_name": "ttd",
        "retrieved_at": utcnow_iso(),
        "status": status,
        "download_manifest_path": str(RAW_DIR / "download_links.json"),
        "download_manifest_snapshot_path": str(manifest_snapshot),
        "candidate_url_count": len(candidate_urls),
        "attempted_download_count": len(candidate_urls[: max(0, download_limit)]),
        "parseable_download_count": parseable_download_count,
        "failed_or_unparseable_download_count": failed_or_unparseable_download_count,
        "downloaded_files": downloaded_files,
        "targets": {"count": len(targets)},
        "drug_target_edges": {"count": len(drug_edges)},
        "disease_target_edges": {"count": len(disease_edges)},
    }

    if status in {"success", "partial"}:
        targets_snapshot = write_json_with_snapshot(targets_path, targets)
        drug_edges_snapshot = write_json_with_snapshot(drug_edges_path, drug_edges)
        disease_edges_snapshot = write_json_with_snapshot(
            disease_edges_path, disease_edges
        )

        checkpoint["targets"].update(
            {
                "output_path": str(targets_path),
                "snapshot_path": str(targets_snapshot),
            }
        )
        checkpoint["drug_target_edges"].update(
            {
                "output_path": str(drug_edges_path),
                "snapshot_path": str(drug_edges_snapshot),
            }
        )
        checkpoint["disease_target_edges"].update(
            {
                "output_path": str(disease_edges_path),
                "snapshot_path": str(disease_edges_snapshot),
            }
        )
    else:
        if targets_path.exists():
            checkpoint["targets"]["output_path"] = str(targets_path)
        if drug_edges_path.exists():
            checkpoint["drug_target_edges"]["output_path"] = str(drug_edges_path)
        if disease_edges_path.exists():
            checkpoint["disease_target_edges"]["output_path"] = str(disease_edges_path)

    write_checkpoint(checkpoint)
    return checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch TTD raw extracts")
    parser.add_argument(
        "--download-limit",
        type=int,
        default=20,
        help="Maximum discovered download URLs to attempt",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    summary = asyncio.run(run(download_limit=args.download_limit))
    LOGGER.info(
        "TTD extraction complete: %s targets, %s drug-target, %s disease-target",
        summary["targets"]["count"],
        summary["drug_target_edges"]["count"],
        summary["disease_target_edges"]["count"],
    )


if __name__ == "__main__":
    main()
