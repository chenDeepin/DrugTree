#!/usr/bin/env python3
"""Build fallback-safe graph artifacts under data/graph from canonical DrugTree data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
GRAPH_DIR = DATA_DIR / "graph"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build_graph_artifacts() -> None:
    drugs_payload = read_json(DATA_DIR / "drugs.json")
    diseases_payload = read_json(DATA_DIR / "diseases.json")
    disease_edges_payload = read_json(DATA_DIR / "disease_drug_edges.json")
    families_payload = read_json(DATA_DIR / "processed" / "drug_families.json")
    lineage_payload = read_json(DATA_DIR / "processed" / "lineage_edges.json")

    drugs = (
        drugs_payload.get("drugs", [])
        if isinstance(drugs_payload, dict)
        else drugs_payload
    )
    diseases = (
        diseases_payload.get("diseases", [])
        if isinstance(diseases_payload, dict)
        else diseases_payload
    )
    disease_edges = (
        disease_edges_payload.get("edges", [])
        if isinstance(disease_edges_payload, dict)
        else disease_edges_payload
    )
    families = (
        families_payload.get("families", [])
        if isinstance(families_payload, dict)
        else families_payload
    )
    lineage_edges = (
        lineage_payload.get("edges", [])
        if isinstance(lineage_payload, dict)
        else lineage_payload
    )

    graph_drugs = {
        "nodes": [
            {
                "node_id": f"drug:{drug['id']}",
                "node_type": "drug",
                "label": drug.get("name") or drug["id"],
                "extra": drug,
            }
            for drug in drugs
            if drug.get("id")
        ]
    }
    graph_diseases = {
        "nodes": [
            {
                "node_id": f"disease:{disease['id']}",
                "node_type": "disease",
                "label": disease.get("canonical_name") or disease["id"],
                "extra": disease,
            }
            for disease in diseases
            if disease.get("id")
        ]
    }
    graph_clusters = {
        "nodes": [
            {
                "node_id": f"cluster:{family['family_id']}",
                "node_type": "cluster",
                "label": family.get("label") or family["family_id"],
                "extra": family,
            }
            for family in families
            if family.get("family_id")
        ]
    }

    graph_lineage = {
        "edges": [
            {
                "edge_id": edge["edge_id"],
                "edge_type": "lineage",
                "source_id": f"drug:{edge['from_drug_id']}",
                "target_id": f"drug:{edge['to_drug_id']}",
                "confidence": edge.get("confidence", 1.0),
                "extra": edge,
            }
            for edge in lineage_edges
            if edge.get("edge_id")
            and edge.get("from_drug_id")
            and edge.get("to_drug_id")
        ]
    }
    graph_disease_edges = {
        "edges": [
            {
                "edge_id": f"disease:{edge['disease_id']}_drug:{edge['drug_id']}",
                "edge_type": "disease_drug",
                "source_id": f"disease:{edge['disease_id']}",
                "target_id": f"drug:{edge['drug_id']}",
                "confidence": 1.0,
                "extra": edge,
            }
            for edge in disease_edges
            if edge.get("disease_id") and edge.get("drug_id")
        ]
    }
    family_member_edges = {
        "edges": [
            {
                "edge_id": f"cluster:{family['family_id']}_drug:{member_id}",
                "edge_type": "family_member",
                "source_id": f"cluster:{family['family_id']}",
                "target_id": f"drug:{member_id}",
                "confidence": 1.0,
                "extra": {"family_basis": family.get("family_basis")},
            }
            for family in families
            for member_id in family.get("member_drug_ids", [])
            if family.get("family_id")
        ]
    }

    write_json(GRAPH_DIR / "nodes" / "drugs.json", graph_drugs)
    write_json(GRAPH_DIR / "nodes" / "diseases.json", graph_diseases)
    write_json(GRAPH_DIR / "nodes" / "clusters.json", graph_clusters)
    write_json(GRAPH_DIR / "edges" / "lineage.json", graph_lineage)
    write_json(GRAPH_DIR / "edges" / "disease_drug.json", graph_disease_edges)
    write_json(GRAPH_DIR / "edges" / "family_member.json", family_member_edges)
    write_json(
        GRAPH_DIR / "graph-meta.json",
        {
            "schema_version": "2.0.0",
            "generated_at": utcnow_iso(),
            "node_counts": {
                "drugs": len(graph_drugs["nodes"]),
                "diseases": len(graph_diseases["nodes"]),
                "clusters": len(graph_clusters["nodes"]),
            },
            "edge_counts": {
                "lineage": len(graph_lineage["edges"]),
                "disease_drug": len(graph_disease_edges["edges"]),
                "family_member": len(family_member_edges["edges"]),
            },
            "target_layer_enabled": False,
        },
    )


def main() -> None:
    build_graph_artifacts()


if __name__ == "__main__":
    main()
