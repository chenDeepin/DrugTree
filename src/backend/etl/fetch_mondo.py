#!/usr/bin/env python3
"""Fetch Mondo disease ontology and extract disease hierarchy/mappings."""

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import asyncio

import httpx

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "mondo"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "fetch_mondo_checkpoint.json"
DISEASES_FILE = DATA_DIR / "diseases.json"

MONDO_OBO_URL = (
    "https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.obo"
)
MONDO_JSON_URL = (
    "https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.json"
)
DOID_OBO_URL = "http://purl.obolibrary.org/obo/doid.obo"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def load_local_diseases() -> List[Dict[str, Any]]:
    if not DISEASES_FILE.exists():
        LOGGER.warning("Canonical diseases file missing: %s", DISEASES_FILE)
        return []
    payload = json.loads(DISEASES_FILE.read_text(encoding="utf-8"))
    return payload.get("diseases", []) if isinstance(payload, dict) else payload


def parse_obo_term(lines: List[str], start_idx: int) -> Tuple[Dict[str, Any], int]:
    term: Dict[str, Any] = {"xrefs": [], "synonyms": [], "parents": [], "children": []}
    i = start_idx
    while i < len(lines):
        line = lines[i].strip()
        if (
            line == "[Term]"
            or line == "[Typedef]"
            or (line.startswith("[") and line.endswith("]"))
        ):
            break
        if line.startswith("id: "):
            term["id"] = line[4:].strip()
        elif line.startswith("name: "):
            term["name"] = line[6:].strip().strip('"')
        elif line.startswith("def: "):
            defn = line[5:].strip().strip('"')
            term["definition"] = defn
        elif line.startswith("synonym: "):
            syn_match = re.search(r'"([^"]*)"', line)
            if syn_match:
                term["synonyms"].append(syn_match.group(1))
        elif line.startswith("xref: "):
            xref_text = line[6:].strip()
            term["xrefs"].append(xref_text)
        elif line.startswith("is_a: "):
            parent_text = line[6:].strip().split("!")[0].strip()
            term["parents"].append(parent_text)
        elif line.startswith("property_value:"):
            pass
        i += 1
    return term, i


def parse_obo(text: str) -> List[Dict[str, Any]]:
    lines = text.split("\n")
    terms: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line == "[Term]":
            term, i = parse_obo_term(lines, i + 1)
            if "id" in term and "name" in term:
                terms.append(term)
        else:
            i += 1
    return terms


def extract_doid_from_xrefs(xrefs: List[str]) -> Optional[str]:
    for xref in xrefs:
        if xref.startswith("DOID:"):
            return xref.split(":")[1] if ":" in xref else xref
        match = re.match(r"DOID[:\s]+(\d+)", xref)
        if match:
            return match.group(1)
    return None


def extract_icd10_from_xrefs(xrefs: List[str]) -> Optional[str]:
    for xref in xrefs:
        match = re.search(
            r"ICD10[CME]?[:\s]+([A-Z]\d{2}(?:\.\d+)?)", xref, re.IGNORECASE
        )
        if match:
            return match.group(1)
    return None


def match_disease_name(mondo_name: str, local_disease: Dict[str, Any]) -> bool:
    local_name = normalize_text(local_disease.get("canonical_name", "")).lower()
    if not local_name:
        return False
    mondo_lower = mondo_name.lower()
    if mondo_lower == local_name:
        return True
    if local_name.replace(" ", "_") in mondo_lower.replace(" ", "_"):
        return True
    if mondo_lower in local_name or local_name in mondo_lower:
        return True
    for syn in local_disease.get("synonyms", []):
        syn_lower = normalize_text(syn).lower()
        if syn_lower and syn_lower in mondo_lower or mondo_lower in syn_lower:
            return True
    return False


async def fetch_obo(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        LOGGER.info("Fetching OBO from: %s", url)
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except (httpx.HTTPError, Exception) as e:
        LOGGER.warning("Failed to fetch %s: %s", url, e)
        return None


async def run(limit: Optional[int]) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    local_diseases = load_local_diseases()
    local_names = {
        normalize_text(d.get("canonical_name", "")).lower(): d for d in local_diseases
    }

    mappings: List[Dict[str, Any]] = []
    hierarchy: List[Dict[str, Any]] = []
    disease_terms: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        obo_text = await fetch_obo(client, MONDO_OBO_URL)
        if not obo_text:
            LOGGER.warning("Mondo OBO fetch failed, trying JSON fallback")
            return _empty_checkpoint("Mondo OBO fetch failed")

        LOGGER.info("Parsing Mondo OBO (%d chars)...", len(obo_text))
        terms = parse_obo(obo_text)
        LOGGER.info("Parsed %d Mondo terms", len(terms))

        id_to_term: Dict[str, Dict[str, Any]] = {}
        for t in terms:
            if t["id"].startswith("MONDO:"):
                id_to_term[t["id"]] = t

        for t in terms:
            if not t["id"].startswith("MONDO:"):
                continue

            doid = extract_doid_from_xrefs(t["xrefs"])
            icd10 = extract_icd10_from_xrefs(t["xrefs"])
            mondo_num = t["id"].replace("MONDO:", "")

            disease_terms.append(
                {
                    "mondo_id": t["id"],
                    "mondo_number": mondo_num,
                    "label": t["name"],
                    "definition": t.get("definition", ""),
                    "synonyms": t["synonyms"][:20],
                    "doid": doid,
                    "icd10_code": icd10,
                    "parent_ids": t["parents"],
                    "xref_count": len(t["xrefs"]),
                    "source_name": "mondo",
                    "retrieved_at": utcnow_iso(),
                }
            )

            matched_local = None
            for local_d in local_diseases:
                if match_disease_name(t["name"], local_d):
                    matched_local = local_d
                    break

            if matched_local:
                mapping: Dict[str, Any] = {
                    "disease_id": matched_local.get("id", ""),
                    "mondo_id": t["id"],
                    "mondo_label": t["name"],
                    "doid": doid,
                    "icd10_code": icd10,
                    "match_method": "name",
                    "source_name": "mondo",
                    "retrieved_at": utcnow_iso(),
                }
                mappings.append(mapping)

            for parent_id in t["parents"]:
                if parent_id.startswith("MONDO:"):
                    hierarchy.append(
                        {
                            "child_id": t["id"],
                            "parent_id": parent_id,
                            "source_name": "mondo",
                            "retrieved_at": utcnow_iso(),
                        }
                    )

            if limit and len(mappings) >= limit:
                break

    terms_path = RAW_DIR / "disease_terms.jsonl"
    mappings_path = RAW_DIR / "disease_mappings.json"
    hierarchy_path = RAW_DIR / "disease_hierarchy.jsonl"

    with open(terms_path, "w", encoding="utf-8") as f:
        for t in disease_terms:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    with open(mappings_path, "w", encoding="utf-8") as f:
        json.dump(
            {"mappings": mappings, "count": len(mappings)},
            f,
            indent=2,
            ensure_ascii=False,
        )
    with open(hierarchy_path, "w", encoding="utf-8") as f:
        for h in hierarchy:
            f.write(json.dumps(h, ensure_ascii=False) + "\n")

    checkpoint = {
        "source_name": "mondo",
        "retrieved_at": utcnow_iso(),
        "local_disease_count": len(local_diseases),
        "mondo_terms_parsed": len(terms),
        "mondo_disease_terms": len(disease_terms),
        "local_matches": len(mappings),
        "hierarchy_edges": len(hierarchy),
        "outputs": {
            "disease_terms": str(terms_path),
            "disease_mappings": str(mappings_path),
            "disease_hierarchy": str(hierarchy_path),
        },
    }

    CHECKPOINT_FILE.write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return checkpoint


def _empty_checkpoint(reason: str) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    cp = {
        "source_name": "mondo",
        "retrieved_at": utcnow_iso(),
        "error": reason,
        "mondo_terms_parsed": 0,
        "local_matches": 0,
        "hierarchy_edges": 0,
    }
    CHECKPOINT_FILE.write_text(
        json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return cp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Mondo disease ontology")
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit matching diseases"
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    summary = asyncio.run(run(limit=args.limit))
    LOGGER.info(
        "Mondo extraction complete: %s terms, %s local matches, %s hierarchy edges",
        summary.get("mondo_disease_terms", 0),
        summary.get("local_matches", 0),
        summary.get("hierarchy_edges", 0),
    )


if __name__ == "__main__":
    main()
