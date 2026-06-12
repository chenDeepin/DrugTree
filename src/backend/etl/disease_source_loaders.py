"""External source loading helpers for disease ETL."""

from __future__ import annotations

import io
import json
import tarfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

try:
    from .chembl_client import ChEMBLClient
    from .disease_etl_helpers import parse_mondo_obographs, parse_orphanet_alignments
except ImportError:  # pragma: no cover - direct script fallback
    from src.backend.etl.chembl_client import ChEMBLClient
    from src.backend.etl.disease_etl_helpers import parse_mondo_obographs, parse_orphanet_alignments

def read_location_bytes(location: str) -> bytes:
    parsed = urlparse(location)
    if parsed.scheme in {"http", "https"}:
        with urlopen(location) as response:  # nosec - official public data sources only
            return response.read()
    return Path(location).read_bytes()


def load_json_like_location(location: Optional[str]) -> Any:
    if not location:
        return None

    raw = read_location_bytes(location)
    lower = location.lower()

    if lower.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            for member in archive.getmembers():
                if member.isfile() and member.name.endswith(".json"):
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        continue
                    return json.loads(extracted.read().decode("utf-8"))
            raise ValueError(f"No JSON payload found in tarball: {location}")

    if lower.endswith(".gz"):
        import gzip

        return json.loads(gzip.decompress(raw).decode("utf-8"))

    return json.loads(raw.decode("utf-8"))


def load_orphanet_records(location: Optional[str]) -> list[dict[str, Any]]:
    payload = load_json_like_location(location)
    if payload is None:
        return []
    return parse_orphanet_alignments(payload)


def load_mondo_records(location: Optional[str]) -> list[dict[str, Any]]:
    payload = load_json_like_location(location)
    if payload is None:
        return []
    return parse_mondo_obographs(payload)


def load_chembl_indication_map(location: Optional[str]) -> dict[str, list[dict[str, Any]]]:
    payload = load_json_like_location(location)
    if payload is None:
        return {}

    if isinstance(payload, dict) and all(isinstance(value, list) for value in payload.values()):
        return payload

    mapping: dict[str, list[dict[str, Any]]] = defaultdict(list)
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return {}

    for item in items:
        if not isinstance(item, dict):
            continue
        chembl_id = item.get("chembl_id") or item.get("molecule_chembl_id")
        indications = item.get("indications") or item.get("drug_indications") or []
        if chembl_id and isinstance(indications, list):
            mapping[str(chembl_id)] = indications

    return dict(mapping)



async def fetch_live_chembl_indication_map(
    drugs: list[dict[str, Any]],
    limit: Optional[int] = None,
    rate_limit_per_sec: float = 1.0,
    client_factory: Any = ChEMBLClient,
) -> dict[str, list[dict[str, Any]]]:
    chembl_ids = []
    for drug in drugs:
        chembl_id = drug.get("chembl_id")
        if chembl_id and chembl_id not in chembl_ids:
            chembl_ids.append(chembl_id)
    if limit is not None:
        chembl_ids = chembl_ids[:limit]

    client = client_factory(rate_limit_per_sec=rate_limit_per_sec)
    results: dict[str, list[dict[str, Any]]] = {}
    try:
        for chembl_id in chembl_ids:
            indications = await client.get_drug_indications(chembl_id)
            if indications:
                results[chembl_id] = indications
    finally:
        await client.close()

    return results
