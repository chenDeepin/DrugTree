#!/usr/bin/env python3
"""Build file-safe frontend JS globals from the canonical JSON/SVG assets."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "src" / "frontend"
FRONTEND_DATA_DIR = FRONTEND_ROOT / "data"


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

    write_json(FRONTEND_DATA_DIR / "drugs.json", drugs)
    write_json(FRONTEND_DATA_DIR / "diseases.json", diseases)
    write_json(FRONTEND_DATA_DIR / "disease-drug-edges.json", disease_drug_edges)
    write_json(FRONTEND_DATA_DIR / "body-ontology.json", body_ontology)

    write_global(FRONTEND_DATA_DIR / "drugs.js", "DRUGTREE_DRUGS_DATA", drugs)
    write_global(FRONTEND_DATA_DIR / "diseases.js", "DRUGTREE_DISEASES_DATA", diseases)
    write_global(
        FRONTEND_DATA_DIR / "disease-drug-edges.js",
        "DRUGTREE_DISEASE_DRUG_EDGES",
        disease_drug_edges,
    )
    write_global(
        FRONTEND_DATA_DIR / "body-ontology.js",
        "DRUGTREE_BODY_ONTOLOGY",
        body_ontology,
    )
    write_global(
        FRONTEND_ROOT / "assets" / "human-body-svg.js",
        "DRUGTREE_HUMAN_BODY_SVG",
        human_body_svg,
    )


if __name__ == "__main__":
    main()
