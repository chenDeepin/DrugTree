from __future__ import annotations

import json
import sqlite3

from src.backend.etl import load_graph_edges as mod


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_loads_processed_edge_files(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    processed_dir = data_dir / "processed"
    db_path = tmp_path / "graph.sqlite"

    monkeypatch.setattr(mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(mod, "PROCESSED_DIR", processed_dir)

    _write_json(
        data_dir / "drugs.json",
        {"drugs": [{"id": "gefitinib", "name": "Gefitinib"}]},
    )
    _write_json(
        data_dir / "diseases.json",
        {
            "diseases": [
                {"id": "glioma", "canonical_name": "Glioma", "body_region": "brain_cns"}
            ]
        },
    )
    _write_jsonl(
        processed_dir / "nodes_target.jsonl",
        [
            {
                "node_id": "EGFR",
                "node_type": "target",
                "label": "Epidermal growth factor receptor",
                "extra": {
                    "name": "Epidermal growth factor receptor",
                    "modality": "protein",
                    "disease_ids": ["glioma"],
                    "uniprot_id": "P00533",
                    "hgnc_id": None,
                    "entrez_id": 1956,
                    "ensembl_gene_id": "ENSG00000146648",
                    "gene_type": "protein_coding",
                    "pathway_ids": ["R-HSA-177929"],
                    "druggability": "known",
                    "is_validated_target": True,
                },
            }
        ],
    )
    _write_jsonl(
        processed_dir / "edges_drug_target.jsonl",
        [
            {
                "edge_id": "drug_target:gefitinib:EGFR:inhibitor",
                "edge_type": "drug_target",
                "source_id": "drug:gefitinib",
                "target_id": "target:EGFR",
                "confidence": 0.9,
                "extra": {
                    "drug_id": "gefitinib",
                    "target_id": "EGFR",
                    "interaction_type": "inhibitor",
                    "mechanism_of_action": "inhibitor",
                    "evidence_sources": ["Open Targets"],
                    "clinical_phase": 4,
                    "retrieved_at": "2026-01-01T00:00:00Z",
                },
            }
        ],
    )
    _write_jsonl(
        processed_dir / "edges_target_disease.jsonl",
        [
            {
                "edge_id": "target_disease:EGFR:glioma:genetic_association",
                "edge_type": "target_disease",
                "source_id": "target:EGFR",
                "target_id": "disease:glioma",
                "confidence": 0.82,
                "extra": {
                    "target_id": "EGFR",
                    "disease_id": "glioma",
                    "association_score": 82.0,
                    "evidence_type": "genetic_association",
                    "evidence_sources": ["Open Targets"],
                    "retrieved_at": "2026-01-01T00:00:00Z",
                },
            }
        ],
    )
    _write_jsonl(
        processed_dir / "edges_drug_disease.jsonl",
        [
            {
                "edge_id": "disease_drug:glioma:gefitinib",
                "edge_type": "disease_drug",
                "source_id": "disease:glioma",
                "target_id": "drug:gefitinib",
                "confidence": 1.0,
                "extra": {
                    "drug_id": "gefitinib",
                    "disease_id": "glioma",
                    "indication_type": "primary",
                    "evidence_source": "curated_seed",
                    "evidence_level": "approved",
                    "phase_context": "IV",
                },
            }
        ],
    )

    counts = mod.load_all(str(db_path))

    assert counts["drug_target_edges"] == 1
    assert counts["target_disease_edges"] == 1
    assert counts["drug_disease_edges"] == 1

    with sqlite3.connect(db_path) as conn:
        drug_target = conn.execute(
            "SELECT drug_id, target_id, interaction_type, mechanism_of_action, clinical_phase FROM drug_target_edges"
        ).fetchone()
        target_disease = conn.execute(
            "SELECT target_id, disease_id, evidence_type, association_score FROM target_disease_edges"
        ).fetchone()
        drug_disease = conn.execute(
            "SELECT drug_id, disease_id, indication_type, evidence_source FROM drug_disease_edges"
        ).fetchone()

    assert drug_target == ("gefitinib", "EGFR", "inhibitor", "inhibitor", "4")
    assert target_disease == ("EGFR", "glioma", "genetic_association", 82.0)
    assert drug_disease == ("gefitinib", "glioma", "primary", "curated_seed")


def test_rejects_raw_disease_drug_as_canonical_source(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    processed_dir = data_dir / "processed"
    db_path = tmp_path / "graph.sqlite"

    monkeypatch.setattr(mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(mod, "PROCESSED_DIR", processed_dir)

    _write_json(
        data_dir / "drugs.json",
        {
            "drugs": [
                {"id": "processed-drug", "name": "Processed Drug"},
                {"id": "raw-drug", "name": "Raw Drug"},
            ]
        },
    )
    _write_json(
        data_dir / "diseases.json",
        {
            "diseases": [
                {"id": "glioma", "canonical_name": "Glioma", "body_region": "brain_cns"}
            ]
        },
    )
    _write_jsonl(processed_dir / "nodes_target.jsonl", [])
    _write_jsonl(processed_dir / "edges_drug_target.jsonl", [])
    _write_jsonl(processed_dir / "edges_target_disease.jsonl", [])
    _write_jsonl(
        processed_dir / "edges_drug_disease.jsonl",
        [
            {
                "edge_id": "disease_drug:glioma:processed-drug",
                "edge_type": "disease_drug",
                "source_id": "disease:glioma",
                "target_id": "drug:processed-drug",
                "confidence": 1.0,
                "extra": {
                    "drug_id": "processed-drug",
                    "disease_id": "glioma",
                    "indication_type": "primary",
                    "evidence_source": "processed",
                    "evidence_level": "approved",
                    "phase_context": "IV",
                },
            }
        ],
    )
    _write_json(
        data_dir / "disease_drug_edges.json",
        {
            "edges": [
                {
                    "drug_id": "raw-drug",
                    "disease_id": "glioma",
                    "indication_type": "primary",
                    "evidence_source": "raw",
                    "evidence_level": "approved",
                    "confidence": 1.0,
                }
            ]
        },
    )

    mod.load_all(str(db_path))

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT drug_id, disease_id, evidence_source FROM drug_disease_edges ORDER BY drug_id"
        ).fetchall()

    assert rows == [("processed-drug", "glioma", "processed")]
