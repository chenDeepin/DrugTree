from __future__ import annotations

import json

from src.backend.etl import normalize_targets as mod


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _load_nodes(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_merges_ttd_and_ctd_disease_ids(monkeypatch, tmp_path):
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "nodes_target.jsonl"
    diseases_path = tmp_path / "diseases.json"

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(mod, "DISEASES_PATH", diseases_path)

    _write_json(
        diseases_path,
        {
            "diseases": [
                {"id": "glioma"},
                {"id": "alzheimers_disease"},
            ]
        },
    )
    _write_json(
        raw_dir / "ttd" / "targets.json",
        [
            {
                "ttd_target_id": "T1",
                "gene_symbol": "EGFR",
                "gene_name": "Epidermal growth factor receptor",
                "uniprot_id": "P00533",
                "ensembl_id": "ENSG00000146648",
                "pathway_ids": ["R-HSA-177929"],
                "is_validated": True,
            }
        ],
    )
    _write_jsonl(
        raw_dir / "opentargets" / "target_disease_edges.jsonl",
        [
            {
                "target_symbol": "EGFR",
                "disease_id": "glioma",
                "association_score": 88.0,
            }
        ],
    )
    _write_jsonl(
        raw_dir / "ctd" / "disease_edges.jsonl",
        [
            {
                "target_id": "EGFR",
                "target_symbol": "EGFR",
                "disease_id": "alzheimers_disease",
                "evidence_type": "direct",
            }
        ],
    )
    _write_jsonl(
        raw_dir / "dgidb" / "drug_gene_interactions.jsonl",
        [
            {
                "gene_symbol": "EGFR",
                "drug_id_local": "gefitinib",
                "interaction_types": ["inhibitor"],
            }
        ],
    )

    count = mod.normalize_targets()

    assert count == 1
    nodes = _load_nodes(output_path)
    assert len(nodes) == 1
    node = nodes[0]
    assert node["node_id"] == "EGFR"
    assert node["extra"]["symbol"] == "EGFR"
    assert node["extra"]["name"] == "Epidermal growth factor receptor"
    assert node["extra"]["uniprot_id"] == "P00533"
    assert node["extra"]["ensembl_gene_id"] == "ENSG00000146648"
    assert node["extra"]["pathway_ids"] == ["R-HSA-177929"]
    assert node["extra"]["is_validated_target"] is True
    assert node["extra"]["disease_ids"] == ["alzheimers_disease", "glioma"]


def test_filters_unknown_disease_ids(monkeypatch, tmp_path):
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "nodes_target.jsonl"
    diseases_path = tmp_path / "diseases.json"

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(mod, "DISEASES_PATH", diseases_path)

    _write_json(diseases_path, {"diseases": [{"id": "glioma"}]})
    _write_json(
        raw_dir / "ttd" / "targets.json",
        [{"ttd_target_id": "T1", "gene_symbol": "EGFR", "gene_name": "EGFR"}],
    )
    _write_jsonl(
        raw_dir / "opentargets" / "target_disease_edges.jsonl",
        [
            {
                "target_symbol": "EGFR",
                "disease_id": "glioma",
                "association_score": 50.0,
            },
            {
                "target_symbol": "EGFR",
                "disease_id": "unknown_disease",
                "association_score": 25.0,
            },
        ],
    )
    _write_jsonl(
        raw_dir / "ctd" / "disease_edges.jsonl",
        [
            {
                "target_id": "EGFR",
                "target_symbol": "EGFR",
                "disease_id": "unknown_ctd",
                "evidence_type": "inferred",
            }
        ],
    )
    _write_jsonl(
        raw_dir / "dgidb" / "drug_gene_interactions.jsonl",
        [
            {
                "gene_symbol": "EGFR",
                "drug_id_local": "gefitinib",
                "interaction_types": ["inhibitor"],
            }
        ],
    )

    mod.normalize_targets()

    nodes = _load_nodes(output_path)
    assert nodes[0]["extra"]["disease_ids"] == ["glioma"]
