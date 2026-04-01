#!/usr/bin/env python3
"""Merge all-source disease records into canonical nodes_disease.jsonl."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
CANONICAL_DISEASES_PATH = DATA_DIR / "diseases.json"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_PATH = DATA_DIR / "processed" / "nodes_disease.jsonl"


def _load_canonical_diseases() -> List[Dict[str, Any]]:
    if not CANONICAL_DISEASES_PATH.exists():
        logger.warning(
            "Canonical diseases.json not found at %s", CANONICAL_DISEASES_PATH
        )
        return []
    with open(CANONICAL_DISEASES_PATH) as f:
        payload = json.load(f)
    return payload.get("diseases", []) if isinstance(payload, dict) else payload


def _load_raw_mondo() -> Dict[str, Dict[str, Any]]:
    path = RAW_DIR / "mondo" / "diseases.json"
    if not path.exists():
        return {}
    with open(path) as f:
        content = f.read().strip()
    if not content:
        return {}
    data = json.loads(content)
    if not isinstance(data, list):
        return {}
    records = data
    lookup: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        mondo_id = rec.get("mondo_id", "")
        name = rec.get("name", "").lower()
        lookup[name] = rec
        if mondo_id:
            lookup[mondo_id] = rec
    return lookup


def _load_raw_ctd() -> Dict[str, Dict[str, Any]]:
    path = RAW_DIR / "ctd" / "disease_edges.jsonl"
    if not path.exists():
        return {}
    lookup: Dict[str, Dict[str, Any]] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            disease_name = rec.get("disease_name", "").lower()
            if disease_name not in lookup:
                lookup[disease_name] = {"target_ids": [], "evidence_types": []}
            lookup[disease_name]["target_ids"].append(rec.get("target_id", ""))
            lookup[disease_name]["evidence_types"].append(rec.get("evidence_type", ""))
    return lookup


def _merge_disease(
    canonical: Dict[str, Any],
    mondo: Optional[Dict[str, Any]],
    ctd: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    node: Dict[str, Any] = {
        "node_id": canonical.get("id", ""),
        "node_type": "disease",
        "label": canonical.get("canonical_name", canonical.get("id", "")),
        "extra": {
            "id": canonical.get("id", ""),
            "canonical_name": canonical.get("canonical_name", ""),
            "synonyms": canonical.get("synonyms", []),
            "body_region": canonical.get("body_region"),
            "anatomy_nodes": canonical.get("anatomy_nodes", []),
            "orphan_flag": canonical.get("orphan_flag", False),
            "prevalence_tier": canonical.get("prevalence_tier", "unknown"),
            "prevalence_count": canonical.get("prevalence_count"),
            "evidence_level": canonical.get("evidence_level", "unknown"),
            "mechanism_summary": canonical.get("mechanism_summary"),
            "mechanism_citation": canonical.get("mechanism_citation"),
            "target_count": canonical.get("target_count", 0),
            "approved_drug_count": canonical.get("approved_drug_count", 0),
            "clinical_drug_count": canonical.get("clinical_drug_count", 0),
            "mondo_id": canonical.get("mondo_id"),
            "doid_id": canonical.get("doid_id"),
            "icd10_code": canonical.get("icd10_code"),
            "disease_hierarchy": [],
        },
    }

    if mondo:
        extra = node["extra"]
        if not extra.get("mondo_id"):
            extra["mondo_id"] = mondo.get("mondo_id")
        if not extra.get("doid_id"):
            extra["doid_id"] = mondo.get("doid_id")
        hierarchy = mondo.get("disease_hierarchy", [])
        if hierarchy:
            extra["disease_hierarchy"] = hierarchy
        mondo_synonyms = mondo.get("synonyms", [])
        if mondo_synonyms:
            existing = set(extra.get("synonyms", []))
            extra["synonyms"] = list(existing | set(mondo_synonyms))

    if ctd:
        extra = node["extra"]
        ctd_targets = ctd.get("target_ids", [])
        if ctd_targets:
            extra["target_count"] = max(
                extra.get("target_count", 0), len(set(ctd_targets))
            )

    return node


def normalize_diseases() -> int:
    canonical_diseases = _load_canonical_diseases()
    mondo_lookup = _load_raw_mondo()
    ctd_lookup = _load_raw_ctd()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(OUTPUT_PATH, "w") as out:
        for disease in canonical_diseases:
            disease_name = disease.get("canonical_name", "").lower()
            disease_id = disease.get("id", "")

            mondo = mondo_lookup.get(disease_name) or mondo_lookup.get(
                disease.get("mondo_id", "")
            )
            ctd = ctd_lookup.get(disease_name)

            node = _merge_disease(disease, mondo, ctd)
            out.write(json.dumps(node, ensure_ascii=False) + "\n")
            count += 1

    logger.info("Wrote %d disease nodes to %s", count, OUTPUT_PATH)
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    normalize_diseases()
