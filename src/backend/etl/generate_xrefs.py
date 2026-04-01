#!/usr/bin/env python3
"""Generate cross-reference tables from canonical data and raw extractions."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_DIR = DATA_DIR / "processed"


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _dedupe_sorted_xrefs(
    rows: List[Dict[str, Any]], entity_key: str
) -> List[Dict[str, Any]]:
    deduped: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    for row in rows:
        entity_id = row.get(entity_key, "")
        source_name = row.get("source_name", "")
        source_id = row.get("source_id", "")
        if not entity_id or not source_name or not source_id:
            continue
        deduped[(entity_id, source_name, source_id)] = row

    return sorted(
        deduped.values(),
        key=lambda row: (
            row.get(entity_key, ""),
            0 if row.get("is_primary") else 1,
            row.get("source_name", ""),
            row.get("source_id", ""),
        ),
    )


def _load_drug_name_lookup() -> Dict[str, str]:
    drugs_path = DATA_DIR / "drugs.json"
    payload = _load_json(drugs_path)
    drugs = payload.get("drugs", []) if isinstance(payload, dict) else payload
    lookup: Dict[str, str] = {}

    for drug in drugs:
        drug_id = drug.get("id", "")
        if not drug_id:
            continue
        names = [drug.get("name", "")]
        names.extend(drug.get("synonyms", []) or [])
        for name in names:
            key = str(name or "").strip().lower()
            if key:
                lookup.setdefault(key, drug_id)

    return lookup


def generate_drug_xrefs() -> int:
    drugs_path = DATA_DIR / "drugs.json"
    payload = _load_json(drugs_path)
    drugs = payload.get("drugs", []) if isinstance(payload, dict) else payload

    xrefs: List[Dict[str, Any]] = []
    drug_lookup = _load_drug_name_lookup()
    for drug in drugs:
        drug_id = drug.get("id", "")
        if not drug_id:
            continue
        if drug.get("chembl_id"):
            xrefs.append(
                {
                    "drug_id": drug_id,
                    "source_name": "ChEMBL",
                    "source_id": drug["chembl_id"],
                    "source_url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{drug['chembl_id']}",
                    "is_primary": True,
                }
            )
        if drug.get("kegg_id"):
            xrefs.append(
                {
                    "drug_id": drug_id,
                    "source_name": "KEGG",
                    "source_id": drug["kegg_id"],
                    "source_url": f"https://www.kegg.jp/entry/{drug['kegg_id']}",
                    "is_primary": False,
                }
            )
        if drug.get("pubchem_cid"):
            xrefs.append(
                {
                    "drug_id": drug_id,
                    "source_name": "PubChem",
                    "source_id": str(drug["pubchem_cid"]),
                    "source_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{drug['pubchem_cid']}",
                    "is_primary": False,
                }
            )

    rxnorm_path = RAW_DIR / "rxnorm" / "drug_names.jsonl"
    for rec in _load_jsonl(rxnorm_path):
        drug_id = rec.get("drug_name_local", "")
        rxcui = rec.get("rxcui", "")
        if drug_id and rxcui:
            xrefs.append(
                {
                    "drug_id": drug_id,
                    "source_name": "RxNorm",
                    "source_id": rxcui,
                    "source_url": f"https://mor.nlm.nih.gov/RxNav/search?searchByRxcui={rxcui}",
                    "is_primary": False,
                }
            )

    dc_path = RAW_DIR / "drugcentral" / "drugs.json"
    dc_data = _load_json(dc_path)
    if isinstance(dc_data, list):
        for rec in dc_data:
            dc_id = rec.get("drugcentral_id", "")
            name = rec.get("name", "")
            if dc_id and name:
                drug_id = (
                    rec.get("drug_id_local", "")
                    or drug_lookup.get(name.lower(), "")
                    or name.lower()
                )
                xrefs.append(
                    {
                        "drug_id": drug_id,
                        "source_name": "DrugCentral",
                        "source_id": dc_id,
                        "is_primary": False,
                    }
                )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    xrefs = _dedupe_sorted_xrefs(xrefs, "drug_id")
    output_path = OUTPUT_DIR / "drug_xrefs.json"
    with open(output_path, "w") as f:
        json.dump(
            {"xrefs": xrefs, "count": len(xrefs)}, f, indent=2, ensure_ascii=False
        )

    logger.info("Wrote %d drug xrefs to %s", len(xrefs), output_path)
    return len(xrefs)


def generate_target_xrefs() -> int:
    xrefs: List[Dict[str, Any]] = []

    ttd_path = RAW_DIR / "ttd" / "targets.json"
    ttd_data = _load_json(ttd_path)
    if isinstance(ttd_data, list):
        for rec in ttd_data:
            symbol = rec.get("gene_symbol", "").upper()
            if not symbol:
                continue
            if rec.get("uniprot_id"):
                xrefs.append(
                    {
                        "target_id": symbol,
                        "source_name": "UniProt",
                        "source_id": rec["uniprot_id"],
                        "source_url": f"https://www.uniprot.org/uniprotkb/{rec['uniprot_id']}",
                        "is_primary": True,
                    }
                )
            if rec.get("ensembl_id"):
                xrefs.append(
                    {
                        "target_id": symbol,
                        "source_name": "Ensembl",
                        "source_id": rec["ensembl_id"],
                        "source_url": f"https://www.ensembl.org/id/{rec['ensembl_id']}",
                        "is_primary": False,
                    }
                )
            if rec.get("ttd_target_id"):
                xrefs.append(
                    {
                        "target_id": symbol,
                        "source_name": "TTD",
                        "source_id": rec["ttd_target_id"],
                        "is_primary": False,
                    }
                )

    ot_path = RAW_DIR / "opentargets" / "drug_target_edges.jsonl"
    for rec in _load_jsonl(ot_path):
        symbol = rec.get("target_symbol", "").upper()
        ensembl_id = rec.get("target_ensembl_id", "")
        if symbol and ensembl_id:
            xrefs.append(
                {
                    "target_id": symbol,
                    "source_name": "Ensembl",
                    "source_id": ensembl_id,
                    "source_url": f"https://www.ensembl.org/id/{ensembl_id}",
                    "is_primary": False,
                }
            )

    dgidb_path = RAW_DIR / "dgidb" / "drug_gene_interactions.jsonl"
    dgidb_symbols: set = set()
    for rec in _load_jsonl(dgidb_path):
        symbol = rec.get("gene_symbol", "").upper()
        dgidb_id = rec.get("dgidb_gene_id", "")
        if symbol and dgidb_id and symbol not in dgidb_symbols:
            dgidb_symbols.add(symbol)
            xrefs.append(
                {
                    "target_id": symbol,
                    "source_name": "DGIdb",
                    "source_id": dgidb_id,
                    "is_primary": False,
                }
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    xrefs = _dedupe_sorted_xrefs(xrefs, "target_id")
    output_path = OUTPUT_DIR / "target_xrefs.json"
    with open(output_path, "w") as f:
        json.dump(
            {"xrefs": xrefs, "count": len(xrefs)}, f, indent=2, ensure_ascii=False
        )

    logger.info("Wrote %d target xrefs to %s", len(xrefs), output_path)
    return len(xrefs)


def generate_all_xrefs() -> Dict[str, int]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "drug_xrefs": generate_drug_xrefs(),
        "target_xrefs": generate_target_xrefs(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    counts = generate_all_xrefs()
    for name, count in counts.items():
        logger.info("%s: %d xrefs", name, count)
