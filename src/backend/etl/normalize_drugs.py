#!/usr/bin/env python3
"""Merge all-source drug records into canonical nodes_drug.jsonl."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
CANONICAL_DRUGS_PATH = DATA_DIR / "drugs.json"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_PATH = DATA_DIR / "processed" / "nodes_drug.jsonl"


def _load_canonical_drugs() -> List[Dict[str, Any]]:
    if not CANONICAL_DRUGS_PATH.exists():
        logger.warning("Canonical drugs.json not found at %s", CANONICAL_DRUGS_PATH)
        return []
    with open(CANONICAL_DRUGS_PATH) as f:
        payload = json.load(f)
    return payload.get("drugs", []) if isinstance(payload, dict) else payload


def _load_raw_drugcentral() -> Dict[str, Dict[str, Any]]:
    path = RAW_DIR / "drugcentral" / "drugs.json"
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        return {}
    records = data
    lookup: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        key = rec.get("drugcentral_id") or rec.get("name", "").lower()
        lookup[key] = rec
    return lookup


def _load_raw_rxnorm() -> Dict[str, List[Dict[str, Any]]]:
    path = RAW_DIR / "rxnorm" / "drug_names.jsonl"
    if not path.exists():
        return {}
    lookup: Dict[str, List[Dict[str, Any]]] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            drug_key = rec.get("drug_name_local", "").lower()
            lookup.setdefault(drug_key, []).append(rec)
    return lookup


def _merge_drug(
    canonical: Dict[str, Any],
    drugcentral: Optional[Dict[str, Any]],
    rxnorm_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    node: Dict[str, Any] = {
        "node_id": canonical.get("id", ""),
        "node_type": "drug",
        "label": canonical.get("name", canonical.get("id", "")),
        "extra": {
            "id": canonical.get("id", ""),
            "name": canonical.get("name", ""),
            "smiles": canonical.get("smiles"),
            "inchikey": canonical.get("inchikey"),
            "atc_code": canonical.get("atc_code"),
            "atc_category": canonical.get("atc_category"),
            "molecular_weight": canonical.get("molecular_weight"),
            "phase": canonical.get("phase"),
            "year_approved": canonical.get("year_approved"),
            "generation": canonical.get("generation", 1),
            "indication": canonical.get("indication"),
            "targets": canonical.get("targets", []),
            "company": canonical.get("company"),
            "synonyms": canonical.get("synonyms", []),
            "class": canonical.get("class"),
            "body_region": canonical.get("body_region"),
            "secondary_body_regions": canonical.get("secondary_body_regions", []),
            "chembl_id": canonical.get("chembl_id"),
            "kegg_id": canonical.get("kegg_id"),
            "pubchem_cid": canonical.get("pubchem_cid"),
            "clinical_trials": canonical.get("clinical_trials", []),
        },
    }

    if drugcentral:
        extra = node["extra"]
        dc_atc = drugcentral.get("atc_codes", [])
        if dc_atc and not extra.get("atc_code"):
            extra["atc_code"] = dc_atc[0] if dc_atc else None
        dc_synonyms = drugcentral.get("synonyms", [])
        if dc_synonyms:
            existing = set(extra.get("synonyms", []))
            extra["synonyms"] = list(existing | set(dc_synonyms))
        extra["drugcentral_id"] = drugcentral.get("drugcentral_id")
        extra["pharmacologic_actions"] = drugcentral.get("pharmacologic_actions", [])

    if rxnorm_entries:
        extra = node["extra"]
        rxcuis = [e.get("rxcui") for e in rxnorm_entries if e.get("rxcui")]
        if rxcuis:
            extra["rxcui"] = rxcuis[0]
        brand_names = [
            e.get("brand_name") for e in rxnorm_entries if e.get("brand_name")
        ]
        existing_syn = set(extra.get("synonyms", []))
        extra["synonyms"] = list(existing_syn | set(brand_names))

    node["extra"]["provenance"] = canonical.get("provenance", {})
    return node


def normalize_drugs() -> int:
    canonical_drugs = _load_canonical_drugs()
    drugcentral_lookup = _load_raw_drugcentral()
    rxnorm_lookup = _load_raw_rxnorm()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(OUTPUT_PATH, "w") as out:
        for drug in canonical_drugs:
            drug_id = drug.get("id", "")
            drug_name = drug.get("name", "").lower()

            dc = drugcentral_lookup.get(drug_name) or drugcentral_lookup.get(
                drug.get("drugcentral_id", "")
            )
            rxnorm = rxnorm_lookup.get(drug_name, [])

            node = _merge_drug(drug, dc, rxnorm)
            out.write(json.dumps(node, ensure_ascii=False) + "\n")
            count += 1

    logger.info("Wrote %d drug nodes to %s", count, OUTPUT_PATH)
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    normalize_drugs()
