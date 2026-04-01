#!/usr/bin/env python3
"""Generate canonical JSONL edge files from processed nodes and raw extractions."""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = PROCESSED_DIR


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


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _slugify(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return slug or "unknown"


def _normalize_association_confidence(score: Any, default: float = 1.0) -> float:
    if score is None:
        return default
    try:
        value = float(score)
    except (TypeError, ValueError):
        return default
    normalized = value / 100.0 if value > 1.0 else value
    return max(0.0, min(normalized, 1.0))


def _load_drug_ids() -> Set[str]:
    drugs_path = DATA_DIR / "drugs.json"
    payload = _load_json(drugs_path)
    drugs = payload.get("drugs", []) if isinstance(payload, dict) else payload
    return {d.get("id", "") for d in drugs if d.get("id")}


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


def _load_disease_ids() -> Set[str]:
    diseases_path = DATA_DIR / "diseases.json"
    payload = _load_json(diseases_path)
    diseases = payload.get("diseases", []) if isinstance(payload, dict) else payload
    return {d.get("id", "") for d in diseases if d.get("id")}


def _load_disease_lookup() -> Dict[str, str]:
    diseases_path = DATA_DIR / "diseases.json"
    payload = _load_json(diseases_path)
    diseases = payload.get("diseases", []) if isinstance(payload, dict) else payload
    lookup: Dict[str, str] = {}

    for disease in diseases:
        disease_id = disease.get("id", "")
        if not disease_id:
            continue
        names = [disease.get("canonical_name", "")]
        names.extend(disease.get("synonyms", []) or [])
        for name in names:
            key = str(name or "").strip().lower()
            if key:
                lookup.setdefault(key, disease_id)

    return lookup


def _load_ttd_target_lookup() -> Dict[str, str]:
    path = RAW_DIR / "ttd" / "targets.json"
    payload = _load_json(path)
    if not isinstance(payload, list):
        return {}

    lookup: Dict[str, str] = {}
    for rec in payload:
        target_key = rec.get("ttd_target_id", "")
        symbol = str(rec.get("gene_symbol", "") or "").upper()
        if target_key and symbol:
            lookup[target_key] = symbol
    return lookup


def _load_json_array(path: Path) -> List[Dict[str, Any]]:
    payload = _load_json(path)
    return payload if isinstance(payload, list) else []


def _clinical_status_to_phase(value: Any) -> Optional[int]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if "approved" in text or "approval" in text or "withdrawn" in text:
        return 4
    match = re.search(r"phase\s*([1234])", text)
    if match:
        return int(match.group(1))
    return None


def generate_drug_target_edges() -> int:
    path = OUTPUT_DIR / "edges_drug_target.jsonl"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    valid_drugs = _load_drug_ids()
    drug_lookup = _load_drug_name_lookup()
    ttd_target_lookup = _load_ttd_target_lookup()

    seen: set[str] = set()
    edges: List[Dict[str, Any]] = []

    def add_edge(
        drug_id: str,
        target_symbol: str,
        interaction_type: str,
        evidence_sources: List[str],
        confidence: float,
        clinical_phase: Optional[int],
        retrieved_at: Optional[str],
    ) -> None:
        if not drug_id or not target_symbol or drug_id not in valid_drugs:
            return

        edge_id = f"drug_target:{drug_id}:{target_symbol}:{_slugify(interaction_type)}"
        if edge_id in seen:
            return
        seen.add(edge_id)

        edges.append(
            {
                "edge_id": edge_id,
                "edge_type": "drug_target",
                "source_id": f"drug:{drug_id}",
                "target_id": f"target:{target_symbol}",
                "confidence": confidence,
                "extra": {
                    "drug_id": drug_id,
                    "target_id": target_symbol,
                    "interaction_type": interaction_type,
                    "evidence_sources": evidence_sources,
                    "clinical_phase": clinical_phase,
                    "retrieved_at": retrieved_at,
                },
            }
        )

    for rec in _load_jsonl(RAW_DIR / "opentargets" / "drug_target_edges.jsonl"):
        association_score = rec.get("association_score")
        add_edge(
            rec.get("drug_id", ""),
            rec.get("target_symbol", "").upper(),
            rec.get("mechanism_of_action", "unknown") or "unknown",
            rec.get("evidence_sources", ["Open Targets"]),
            _normalize_association_confidence(association_score, default=1.0),
            rec.get("clinical_phase"),
            rec.get("retrieved_at"),
        )

    for rec in _load_jsonl(RAW_DIR / "dgidb" / "drug_gene_interactions.jsonl"):
        interaction_types = rec.get("interaction_types") or ["unknown"]
        for interaction_type in interaction_types:
            add_edge(
                rec.get("drug_id_local", ""),
                rec.get("gene_symbol", "").upper(),
                interaction_type or "unknown",
                ["DGIdb"],
                0.8,
                None,
                rec.get("retrieved_at"),
            )

    for rec in _load_json_array(RAW_DIR / "ttd" / "drug_target_edges.json"):
        clinical_status = rec.get("clinical_status", "")
        add_edge(
            rec.get("drug_id_local", "")
            or drug_lookup.get(str(rec.get("drug_name", "")).strip().lower(), ""),
            ttd_target_lookup.get(rec.get("ttd_target_id", ""), ""),
            clinical_status or "ttd_association",
            ["TTD"],
            0.75 if clinical_status else 0.65,
            _clinical_status_to_phase(clinical_status),
            rec.get("retrieved_at"),
        )

    with open(path, "w") as f:
        for edge in edges:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")

    logger.info("Wrote %d drug-target edges to %s", len(edges), path)
    return len(edges)


def generate_target_disease_edges() -> int:
    path = OUTPUT_DIR / "edges_target_disease.jsonl"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    valid_diseases = _load_disease_ids()
    disease_lookup = _load_disease_lookup()
    ttd_target_lookup = _load_ttd_target_lookup()

    seen: set[str] = set()
    edges: List[Dict[str, Any]] = []

    def add_edge(
        target_symbol: str,
        disease_id: str,
        evidence_type: str,
        evidence_sources: List[str],
        association_score: Optional[float],
        confidence: float,
        retrieved_at: Optional[str],
    ) -> None:
        if not target_symbol or not disease_id or disease_id not in valid_diseases:
            return

        edge_id = (
            f"target_disease:{target_symbol}:{disease_id}:{_slugify(evidence_type)}"
        )
        if edge_id in seen:
            return
        seen.add(edge_id)

        edges.append(
            {
                "edge_id": edge_id,
                "edge_type": "target_disease",
                "source_id": f"target:{target_symbol}",
                "target_id": f"disease:{disease_id}",
                "confidence": confidence,
                "extra": {
                    "target_id": target_symbol,
                    "disease_id": disease_id,
                    "association_score": association_score,
                    "evidence_type": evidence_type,
                    "evidence_sources": evidence_sources,
                    "retrieved_at": retrieved_at,
                },
            }
        )

    for rec in _load_jsonl(RAW_DIR / "opentargets" / "target_disease_edges.jsonl"):
        association_score = rec.get("association_score")
        add_edge(
            rec.get("target_symbol", "").upper(),
            rec.get("disease_id", ""),
            rec.get("evidence_type", "genetic_association") or "genetic_association",
            ["Open Targets"],
            association_score,
            _normalize_association_confidence(association_score, default=0.8),
            rec.get("retrieved_at"),
        )

    for rec in _load_jsonl(RAW_DIR / "ctd" / "disease_edges.jsonl"):
        add_edge(
            rec.get("target_id", "").upper() or rec.get("target_symbol", "").upper(),
            rec.get("disease_id", ""),
            rec.get("evidence_type", "unknown") or "unknown",
            ["CTD"],
            None,
            0.7,
            rec.get("retrieved_at"),
        )

    for rec in _load_json_array(RAW_DIR / "ttd" / "disease_target_edges.json"):
        add_edge(
            ttd_target_lookup.get(rec.get("ttd_target_id", ""), ""),
            rec.get("disease_id", "")
            or disease_lookup.get(str(rec.get("disease_name", "")).strip().lower(), ""),
            rec.get("evidence_type", "ttd_association") or "ttd_association",
            ["TTD"],
            None,
            0.75,
            rec.get("retrieved_at"),
        )

    with open(path, "w") as f:
        for edge in edges:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")

    logger.info("Wrote %d target-disease edges to %s", len(edges), path)
    return len(edges)


def generate_drug_disease_edges() -> int:
    path = OUTPUT_DIR / "edges_drug_disease.jsonl"
    valid_drugs = _load_drug_ids()
    valid_diseases = _load_disease_ids()

    dd_edges_path = DATA_DIR / "disease_drug_edges.json"
    payload = _load_json(dd_edges_path)
    raw_edges = payload.get("edges", []) if isinstance(payload, dict) else payload

    edges: List[Dict[str, Any]] = []
    for rec in raw_edges:
        drug_id = rec.get("drug_id", "")
        disease_id = rec.get("disease_id", "")
        if not drug_id or not disease_id:
            continue
        if drug_id not in valid_drugs or disease_id not in valid_diseases:
            continue

        edge: Dict[str, Any] = {
            "edge_id": f"disease_drug:{disease_id}:{drug_id}",
            "edge_type": "disease_drug",
            "source_id": f"disease:{disease_id}",
            "target_id": f"drug:{drug_id}",
            "confidence": rec.get("confidence", 1.0),
            "extra": {
                "drug_id": drug_id,
                "disease_id": disease_id,
                "indication_type": rec.get("indication_type", "primary"),
                "evidence_source": rec.get("evidence_source", ""),
                "evidence_level": rec.get("evidence_level", "unknown"),
                "phase_context": rec.get("phase_context"),
            },
        }
        edges.append(edge)

    with open(path, "w") as f:
        for edge in edges:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")

    logger.info("Wrote %d drug-disease edges to %s", len(edges), path)
    return len(edges)


def generate_drug_lineage_edges() -> int:
    path = OUTPUT_DIR / "edges_drug_lineage.jsonl"
    lineage_path = PROCESSED_DIR / "lineage_edges.json"
    payload = _load_json(lineage_path)
    raw_edges = payload.get("edges", []) if isinstance(payload, dict) else payload

    valid_drugs = _load_drug_ids()
    edges: List[Dict[str, Any]] = []
    for rec in raw_edges:
        from_id = rec.get("from_drug_id", "")
        to_id = rec.get("to_drug_id", "")
        if from_id not in valid_drugs or to_id not in valid_drugs:
            continue

        edge: Dict[str, Any] = {
            "edge_id": rec.get("edge_id", f"lineage:{from_id}:{to_id}"),
            "edge_type": "lineage",
            "source_id": f"drug:{from_id}",
            "target_id": f"drug:{to_id}",
            "confidence": rec.get("confidence", 1.0),
            "extra": {
                "from_drug_id": from_id,
                "to_drug_id": to_id,
                "edge_type": rec.get("edge_type", "follow_on"),
                "score_breakdown": rec.get("score_breakdown", {}),
                "provenance": rec.get("provenance", "auto"),
                "explanation": rec.get("explanation", ""),
            },
        }
        edges.append(edge)

    with open(path, "w") as f:
        for edge in edges:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")

    logger.info("Wrote %d lineage edges to %s", len(edges), path)
    return len(edges)


def generate_all_edges() -> Dict[str, int]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "drug_target": generate_drug_target_edges(),
        "target_disease": generate_target_disease_edges(),
        "drug_disease": generate_drug_disease_edges(),
        "drug_lineage": generate_drug_lineage_edges(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    counts = generate_all_edges()
    for name, count in counts.items():
        logger.info("%s: %d edges", name, count)
    logger.info("Total: %d edges", sum(counts.values()))
