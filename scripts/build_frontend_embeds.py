#!/usr/bin/env python3
"""Build file-safe frontend JS globals from the canonical JSON/SVG assets."""

from __future__ import annotations

import json
import gzip
from pathlib import Path

try:
    import brotli
except ImportError:  # pragma: no cover - optional local optimization dependency
    brotli = None


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "src" / "frontend"
FRONTEND_DATA_DIR = FRONTEND_ROOT / "data"
GRAPH_DATA_DIR = REPO_ROOT / "data" / "graph"


ATC_TO_BODY_REGIONS = {
    "A": [
        "stomach_upper_gi",
        "intestine_colorectal",
        "liver_biliary_pancreas",
        "endocrine_metabolic",
    ],
    "B": ["blood_immune"],
    "C": ["heart_vascular", "blood_immune"],
    "D": ["skin"],
    "G": ["kidney_urinary", "reproductive_breast"],
    "H": ["endocrine_metabolic"],
    "J": [
        "brain_cns",
        "eye_ear",
        "lung_respiratory",
        "heart_vascular",
        "blood_immune",
        "stomach_upper_gi",
        "intestine_colorectal",
        "liver_biliary_pancreas",
        "kidney_urinary",
        "reproductive_breast",
        "bone_joint_muscle",
        "skin",
        "systemic_multiorgan",
    ],
    "L": [
        "brain_cns",
        "eye_ear",
        "lung_respiratory",
        "heart_vascular",
        "blood_immune",
        "stomach_upper_gi",
        "intestine_colorectal",
        "liver_biliary_pancreas",
        "kidney_urinary",
        "reproductive_breast",
        "bone_joint_muscle",
        "skin",
        "systemic_multiorgan",
    ],
    "M": ["bone_joint_muscle"],
    "N": ["brain_cns"],
    "P": ["intestine_colorectal", "blood_immune", "systemic_multiorgan"],
    "R": ["lung_respiratory"],
    "S": ["eye_ear"],
    "V": ["systemic_multiorgan"],
}


def unique(values):
    seen = set()
    ordered = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def resolve_body_regions(drug):
    explicit_regions = unique(
        [drug.get("body_region"), *(drug.get("secondary_body_regions") or [])]
    )
    if explicit_regions:
        return explicit_regions

    return ATC_TO_BODY_REGIONS.get(
        drug.get("atc_category") or "V", ATC_TO_BODY_REGIONS["V"]
    )


def build_search_text(drug):
    haystack = [
        drug.get("id"),
        drug.get("name"),
        drug.get("class"),
        drug.get("indication"),
        drug.get("atc_code"),
        *(drug.get("targets") or []),
        *(drug.get("synonyms") or []),
    ]
    return " ".join(str(value) for value in haystack if value).lower()


def build_drug_shell(drug):
    targets = drug.get("targets") or []
    return {
        "id": drug.get("id"),
        "name": drug.get("name"),
        "smiles": drug.get("smiles"),
        "atc_code": drug.get("atc_code"),
        "atc_category": drug.get("atc_category"),
        "phase": drug.get("phase"),
        "year_approved": drug.get("year_approved"),
        "generation": drug.get("generation"),
        "class": drug.get("class"),
        "targets_preview": targets[:2],
        "public_summary": drug.get("public_summary"),
        "body_regions": resolve_body_regions(drug),
        "search_text": build_search_text(drug),
    }


def write_global(output_path: Path, global_name: str, payload) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"window.{global_name} = {json.dumps(payload, ensure_ascii=False)};\n",
        encoding="utf-8",
    )


def write_json(output_path: Path, payload) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_compressed_asset(source_path: Path) -> None:
    raw = source_path.read_bytes()
    source_path.with_suffix(source_path.suffix + ".gz").write_bytes(
        gzip.compress(raw, compresslevel=9)
    )

    if brotli is not None:
        source_path.with_suffix(source_path.suffix + ".br").write_bytes(
            brotli.compress(raw, quality=11)
        )


def write_compressed_assets(paths) -> None:
    for path in paths:
        if path.exists():
            write_compressed_asset(path)


def load_graph_payload(path: Path, key: str):
    if not path.exists():
        return {key: []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and key in payload:
        return payload
    return {key: payload if isinstance(payload, list) else []}


def slim_graph_node(node):
    if not isinstance(node, dict):
        return None

    node_type = node.get("node_type")
    extra_value = node.get("extra")
    extra = extra_value if isinstance(extra_value, dict) else {}

    if node_type == "drug":
        slim_extra = {
            "id": extra.get("id"),
            "name": extra.get("name"),
        }
    elif node_type == "disease":
        slim_extra = {
            "id": extra.get("id"),
            "canonical_name": extra.get("canonical_name"),
            "body_region": extra.get("body_region"),
            "orphan_flag": extra.get("orphan_flag"),
            "approved_drug_count": extra.get("approved_drug_count"),
            "clinical_drug_count": extra.get("clinical_drug_count"),
        }
    elif node_type == "cluster":
        slim_extra = {
            "family_id": extra.get("family_id"),
            "label": extra.get("label"),
            "family_basis": extra.get("family_basis"),
            "prototype_drug_id": extra.get("prototype_drug_id"),
            "member_drug_ids": extra.get("member_drug_ids") or [],
        }
    else:
        slim_extra = {}

    return {
        "node_id": node.get("node_id"),
        "node_type": node_type,
        "label": node.get("label"),
        "extra": slim_extra,
    }


def slim_graph_edge(edge):
    if not isinstance(edge, dict):
        return None

    slim_edge = {
        "edge_id": edge.get("edge_id"),
        "edge_type": edge.get("edge_type"),
        "source_id": edge.get("source_id"),
        "target_id": edge.get("target_id"),
        "confidence": edge.get("confidence", 1.0),
    }

    if edge.get("edge_type") == "lineage":
        extra = edge.get("extra") if isinstance(edge.get("extra"), dict) else {}
        slim_edge["lineage_type"] = extra.get("edge_type")
        slim_edge["score_breakdown"] = extra.get("score_breakdown") or {}
        slim_edge["provenance"] = extra.get("provenance")
        slim_edge["rationale_tags"] = extra.get("rationale_tags") or []
        slim_edge["explanation"] = extra.get("explanation")

    return slim_edge


def main() -> None:
    # Canonical data sources live under repo-root data/.
    drugs = json.loads((REPO_ROOT / "data" / "drugs.json").read_text(encoding="utf-8"))
    diseases = json.loads(
        (REPO_ROOT / "data" / "diseases.json").read_text(encoding="utf-8")
    )
    disease_drug_edges = json.loads(
        (REPO_ROOT / "data" / "disease_drug_edges.json").read_text(encoding="utf-8")
    )
    body_ontology = json.loads(
        (REPO_ROOT / "data" / "ontology" / "body-ontology.json").read_text(
            encoding="utf-8"
        )
    )
    human_body_svg = (FRONTEND_ROOT / "assets" / "human-body.svg").read_text(
        encoding="utf-8"
    )
    drug_shells = {"drugs": [build_drug_shell(drug) for drug in drugs.get("drugs", [])]}
    graph_nodes = {
        "nodes": [
            node
            for node in (
                slim_graph_node(raw_node)
                for raw_node in [
                    *load_graph_payload(
                        GRAPH_DATA_DIR / "nodes" / "drugs.json", "nodes"
                    ).get("nodes", []),
                    *load_graph_payload(
                        GRAPH_DATA_DIR / "nodes" / "diseases.json", "nodes"
                    ).get("nodes", []),
                    *load_graph_payload(
                        GRAPH_DATA_DIR / "nodes" / "clusters.json", "nodes"
                    ).get("nodes", []),
                ]
            )
            if node is not None
        ]
    }
    graph_edges = {
        "edges": [
            edge
            for edge in (
                slim_graph_edge(raw_edge)
                for raw_edge in [
                    *load_graph_payload(
                        GRAPH_DATA_DIR / "edges" / "lineage.json", "edges"
                    ).get("edges", []),
                    *load_graph_payload(
                        GRAPH_DATA_DIR / "edges" / "disease_drug.json", "edges"
                    ).get("edges", []),
                    *load_graph_payload(
                        GRAPH_DATA_DIR / "edges" / "family_member.json", "edges"
                    ).get("edges", []),
                ]
            )
            if edge is not None
        ]
    }
    graph_meta = (
        json.loads((GRAPH_DATA_DIR / "graph-meta.json").read_text(encoding="utf-8"))
        if (GRAPH_DATA_DIR / "graph-meta.json").exists()
        else None
    )

    generated_paths = [
        FRONTEND_DATA_DIR / "drugs.json",
        FRONTEND_DATA_DIR / "drugs-shell.json",
        FRONTEND_DATA_DIR / "diseases.json",
        FRONTEND_DATA_DIR / "disease-drug-edges.json",
        FRONTEND_DATA_DIR / "body-ontology.json",
        FRONTEND_DATA_DIR / "graph-nodes.json",
        FRONTEND_DATA_DIR / "graph-edges.json",
        FRONTEND_DATA_DIR / "graph-meta.json",
        FRONTEND_DATA_DIR / "drugs.js",
        FRONTEND_DATA_DIR / "drugs-shell.js",
        FRONTEND_DATA_DIR / "diseases.js",
        FRONTEND_DATA_DIR / "disease-drug-edges.js",
        FRONTEND_DATA_DIR / "body-ontology.js",
        FRONTEND_DATA_DIR / "graph-nodes.js",
        FRONTEND_DATA_DIR / "graph-edges.js",
        FRONTEND_DATA_DIR / "graph-meta.js",
        FRONTEND_ROOT / "assets" / "human-body-svg.js",
    ]

    write_json(generated_paths[0], drugs)
    write_json(generated_paths[1], drug_shells)
    write_json(generated_paths[2], diseases)
    write_json(generated_paths[3], disease_drug_edges)
    write_json(generated_paths[4], body_ontology)
    write_json(generated_paths[5], graph_nodes)
    write_json(generated_paths[6], graph_edges)
    write_json(generated_paths[7], graph_meta)

    write_global(generated_paths[8], "DRUGTREE_DRUGS_DATA", drugs)
    write_global(generated_paths[9], "DRUGTREE_DRUGS_SHELL_DATA", drug_shells)
    write_global(generated_paths[10], "DRUGTREE_DISEASES_DATA", diseases)
    write_global(generated_paths[11], "DRUGTREE_DISEASE_DRUG_EDGES", disease_drug_edges)
    write_global(generated_paths[12], "DRUGTREE_BODY_ONTOLOGY", body_ontology)
    write_global(generated_paths[13], "DRUGTREE_GRAPH_NODES", graph_nodes)
    write_global(generated_paths[14], "DRUGTREE_GRAPH_EDGES", graph_edges)
    write_global(generated_paths[15], "DRUGTREE_GRAPH_META", graph_meta)
    write_global(generated_paths[16], "DRUGTREE_HUMAN_BODY_SVG", human_body_svg)
    write_compressed_assets(generated_paths)


if __name__ == "__main__":
    main()
