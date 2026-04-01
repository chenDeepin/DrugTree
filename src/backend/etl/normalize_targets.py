#!/usr/bin/env python3
"""Merge all-source target records into canonical nodes_target.jsonl."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_PATH = DATA_DIR / "processed" / "nodes_target.jsonl"

DISEASES_PATH = DATA_DIR / "diseases.json"


def _load_disease_ids() -> set[str]:
    if not DISEASES_PATH.exists():
        return set()
    with open(DISEASES_PATH) as f:
        payload = json.load(f)
    diseases = payload.get("diseases", []) if isinstance(payload, dict) else payload
    return {d.get("id", "") for d in diseases}


def _load_raw_ttd_targets() -> Dict[str, Dict[str, Any]]:
    path = RAW_DIR / "ttd" / "targets.json"
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        return {}
    records = data
    lookup: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        key = rec.get("gene_symbol", "").upper() or rec.get("ttd_target_id", "")
        lookup[key] = rec
    return lookup


def _load_raw_opentargets() -> Dict[str, Dict[str, Any]]:
    path = RAW_DIR / "opentargets" / "target_disease_edges.jsonl"
    if not path.exists():
        return {}
    lookup: Dict[str, Dict[str, Any]] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            symbol = rec.get("target_symbol", "").upper()
            if symbol not in lookup:
                lookup[symbol] = {"disease_ids": [], "association_scores": []}
            lookup[symbol]["disease_ids"].append(rec.get("disease_id", ""))
            score = rec.get("association_score")
            if score is not None:
                lookup[symbol]["association_scores"].append(score)
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
            symbol = (
                rec.get("target_symbol", "").upper() or rec.get("target_id", "").upper()
            )
            if not symbol:
                continue
            if symbol not in lookup:
                lookup[symbol] = {"disease_ids": []}
            lookup[symbol]["disease_ids"].append(rec.get("disease_id", ""))
    return lookup


def _load_raw_dgidb() -> Dict[str, Dict[str, Any]]:
    path = RAW_DIR / "dgidb" / "drug_gene_interactions.jsonl"
    if not path.exists():
        return {}
    lookup: Dict[str, Dict[str, Any]] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            symbol = rec.get("gene_symbol", "").upper()
            if symbol not in lookup:
                lookup[symbol] = {"drug_ids": [], "interaction_types": set()}
            drug_id = rec.get("drug_id_local", "")
            if drug_id:
                lookup[symbol]["drug_ids"].append(drug_id)
            for it in rec.get("interaction_types", []):
                lookup[symbol]["interaction_types"].add(it)
    for v in lookup.values():
        v["interaction_types"] = list(v["interaction_types"])
    return lookup


def normalize_targets() -> int:
    ttd_lookup = _load_raw_ttd_targets()
    ot_lookup = _load_raw_opentargets()
    ctd_lookup = _load_raw_ctd()
    dgidb_lookup = _load_raw_dgidb()
    known_disease_ids = _load_disease_ids()

    all_symbols = (
        set(ttd_lookup.keys())
        | set(ot_lookup.keys())
        | set(ctd_lookup.keys())
        | set(dgidb_lookup.keys())
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(OUTPUT_PATH, "w") as out:
        for symbol in sorted(all_symbols):
            ttd = ttd_lookup.get(symbol, {})
            ot = ot_lookup.get(symbol, {})
            ctd = ctd_lookup.get(symbol, {})
            dgidb = dgidb_lookup.get(symbol, {})

            disease_ids = sorted(
                set(ot.get("disease_ids", []) + ctd.get("disease_ids", []))
            )
            disease_ids = [d for d in disease_ids if d in known_disease_ids]

            gene_name = ttd.get("gene_name") or symbol
            node: Dict[str, Any] = {
                "node_id": symbol,
                "node_type": "target",
                "label": gene_name,
                "extra": {
                    "id": symbol,
                    "symbol": symbol,
                    "name": gene_name,
                    "uniprot_id": ttd.get("uniprot_id"),
                    "ensembl_gene_id": ttd.get("ensembl_id"),
                    "hgnc_id": None,
                    "entrez_id": None,
                    "gene_type": "protein_coding",
                    "modality": "unknown",
                    "disease_ids": disease_ids,
                    "pathway_ids": ttd.get("pathway_ids", []),
                    "druggability": "unknown",
                    "is_validated_target": bool(ttd.get("is_validated", False)),
                },
            }
            out.write(json.dumps(node, ensure_ascii=False) + "\n")
            count += 1

    logger.info("Wrote %d target nodes to %s", count, OUTPUT_PATH)
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    normalize_targets()
