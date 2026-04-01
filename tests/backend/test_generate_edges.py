from __future__ import annotations

import json

from src.backend.etl import generate_edges as mod


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _load_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_consumes_ttd_and_ctd_sources(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"

    monkeypatch.setattr(mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(mod, "OUTPUT_DIR", processed_dir)

    _write_json(
        data_dir / "drugs.json",
        {
            "drugs": [
                {"id": "gefitinib", "name": "Gefitinib", "synonyms": ["Iressa"]},
                {"id": "erlotinib", "name": "Erlotinib", "synonyms": ["Tarceva"]},
            ]
        },
    )
    _write_json(
        data_dir / "diseases.json",
        {
            "diseases": [
                {
                    "id": "glioma",
                    "canonical_name": "Glioma",
                    "synonyms": ["Glioblastoma"],
                }
            ]
        },
    )
    _write_json(
        raw_dir / "ttd" / "targets.json",
        [{"ttd_target_id": "T1", "gene_symbol": "EGFR"}],
    )
    _write_json(
        raw_dir / "ttd" / "drug_target_edges.json",
        [
            {
                "ttd_target_id": "T1",
                "drug_name": "Gefitinib",
                "drug_id_local": "",
                "clinical_status": "Approved",
            }
        ],
    )
    _write_json(
        raw_dir / "ttd" / "disease_target_edges.json",
        [{"ttd_target_id": "T1", "disease_name": "Glioblastoma"}],
    )
    _write_jsonl(
        raw_dir / "opentargets" / "drug_target_edges.jsonl",
        [
            {
                "drug_id": "gefitinib",
                "target_symbol": "EGFR",
                "mechanism_of_action": "inhibitor",
                "evidence_sources": ["Open Targets"],
                "association_score": 0.9,
                "clinical_phase": 4,
                "retrieved_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    _write_jsonl(
        raw_dir / "opentargets" / "target_disease_edges.jsonl",
        [
            {
                "target_symbol": "EGFR",
                "disease_id": "glioma",
                "evidence_type": "genetic_association",
                "association_score": 0.82,
                "retrieved_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    _write_jsonl(
        raw_dir / "dgidb" / "drug_gene_interactions.jsonl",
        [
            {
                "drug_id_local": "erlotinib",
                "gene_symbol": "EGFR",
                "interaction_types": ["antagonist"],
                "retrieved_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    _write_jsonl(
        raw_dir / "ctd" / "disease_edges.jsonl",
        [
            {
                "target_id": "EGFR",
                "disease_id": "glioma",
                "evidence_type": "direct",
                "retrieved_at": "2026-01-01T00:00:00Z",
            }
        ],
    )

    drug_target_count = mod.generate_drug_target_edges()
    target_disease_count = mod.generate_target_disease_edges()

    assert drug_target_count == 3
    assert target_disease_count == 3

    drug_target_edges = _load_jsonl(processed_dir / "edges_drug_target.jsonl")
    target_disease_edges = _load_jsonl(processed_dir / "edges_target_disease.jsonl")

    ttd_drug_edge = next(
        edge
        for edge in drug_target_edges
        if edge["extra"]["evidence_sources"] == ["TTD"]
    )
    ctd_disease_edge = next(
        edge
        for edge in target_disease_edges
        if edge["extra"]["evidence_sources"] == ["CTD"]
    )
    ttd_disease_edge = next(
        edge
        for edge in target_disease_edges
        if edge["extra"]["evidence_sources"] == ["TTD"]
    )
    ot_drug_edge = next(
        edge
        for edge in drug_target_edges
        if edge["extra"]["evidence_sources"] == ["Open Targets"]
    )
    ot_disease_edge = next(
        edge
        for edge in target_disease_edges
        if edge["extra"]["evidence_sources"] == ["Open Targets"]
    )

    assert ttd_drug_edge["source_id"] == "drug:gefitinib"
    assert ttd_drug_edge["target_id"] == "target:EGFR"
    assert ttd_drug_edge["confidence"] == 0.75
    assert ttd_drug_edge["edge_id"].startswith("drug_target:gefitinib:EGFR:")
    assert ot_drug_edge["confidence"] == 0.9
    assert ot_disease_edge["confidence"] == 0.82

    assert ctd_disease_edge["source_id"] == "target:EGFR"
    assert ctd_disease_edge["target_id"] == "disease:glioma"
    assert ctd_disease_edge["confidence"] == 0.7
    assert ctd_disease_edge["extra"]["evidence_type"] == "direct"

    assert ttd_disease_edge["source_id"] == "target:EGFR"
    assert ttd_disease_edge["target_id"] == "disease:glioma"
    assert ttd_disease_edge["confidence"] == 0.75


def test_dedupes_duplicate_edge_ids(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"

    monkeypatch.setattr(mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(mod, "OUTPUT_DIR", processed_dir)

    _write_json(data_dir / "drugs.json", {"drugs": []})
    _write_json(
        data_dir / "diseases.json",
        {"diseases": [{"id": "glioma", "canonical_name": "Glioma", "synonyms": []}]},
    )
    _write_json(
        raw_dir / "ttd" / "targets.json",
        [{"ttd_target_id": "T1", "gene_symbol": "EGFR"}],
    )
    _write_json(raw_dir / "ttd" / "disease_target_edges.json", [])
    _write_jsonl(raw_dir / "opentargets" / "target_disease_edges.jsonl", [])
    _write_jsonl(
        raw_dir / "ctd" / "disease_edges.jsonl",
        [
            {
                "target_id": "EGFR",
                "disease_id": "glioma",
                "evidence_type": "direct",
                "retrieved_at": "2026-01-01T00:00:00Z",
            },
            {
                "target_id": "EGFR",
                "disease_id": "glioma",
                "evidence_type": "direct",
                "retrieved_at": "2026-01-01T00:00:00Z",
            },
            {
                "target_id": "EGFR",
                "disease_id": "glioma",
                "evidence_type": "inferred",
                "retrieved_at": "2026-01-01T00:00:00Z",
            },
        ],
    )

    count = mod.generate_target_disease_edges()

    assert count == 2
    edges = _load_jsonl(processed_dir / "edges_target_disease.jsonl")
    edge_ids = [edge["edge_id"] for edge in edges]
    assert len(edge_ids) == len(set(edge_ids))
    assert sorted(edge["extra"]["evidence_type"] for edge in edges) == [
        "direct",
        "inferred",
    ]
