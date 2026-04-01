from __future__ import annotations

import json

from src.backend.etl import generate_xrefs as mod


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _load_xrefs(path):
    return json.loads(path.read_text(encoding="utf-8"))["xrefs"]


def test_prefers_drug_id_local_for_drugcentral(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    output_dir = data_dir / "processed"

    monkeypatch.setattr(mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "OUTPUT_DIR", output_dir)

    _write_json(
        data_dir / "drugs.json",
        {
            "drugs": [
                {"id": "gefitinib-drug", "name": "Gefitinib", "synonyms": ["Iressa"]}
            ]
        },
    )
    _write_json(
        raw_dir / "drugcentral" / "drugs.json",
        [
            {
                "drugcentral_id": "DC123",
                "name": "Gefitinib",
                "drug_id_local": "gefitinib-drug",
            }
        ],
    )

    mod.generate_drug_xrefs()

    xrefs = _load_xrefs(output_dir / "drug_xrefs.json")
    drugcentral_xref = next(
        xref for xref in xrefs if xref["source_name"] == "DrugCentral"
    )
    assert drugcentral_xref["drug_id"] == "gefitinib-drug"


def test_dedupes_duplicate_composite_keys(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    output_dir = data_dir / "processed"

    monkeypatch.setattr(mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "OUTPUT_DIR", output_dir)

    _write_json(
        data_dir / "drugs.json",
        {
            "drugs": [
                {
                    "id": "gefitinib-drug",
                    "name": "Gefitinib",
                    "synonyms": ["Iressa"],
                    "chembl_id": "CHEMBL939",
                    "kegg_id": "D01977",
                    "pubchem_cid": 1234,
                }
            ]
        },
    )
    _write_jsonl(
        raw_dir / "rxnorm" / "drug_names.jsonl",
        [
            {"drug_name_local": "gefitinib-drug", "rxcui": "111"},
            {"drug_name_local": "gefitinib-drug", "rxcui": "111"},
        ],
    )
    _write_json(
        raw_dir / "drugcentral" / "drugs.json",
        [
            {
                "drugcentral_id": "DC123",
                "name": "Gefitinib",
                "drug_id_local": "gefitinib-drug",
            },
            {
                "drugcentral_id": "DC123",
                "name": "Gefitinib",
                "drug_id_local": "gefitinib-drug",
            },
        ],
    )
    _write_json(
        raw_dir / "ttd" / "targets.json",
        [
            {
                "gene_symbol": "EGFR",
                "uniprot_id": "P00533",
                "ensembl_id": "ENSG00000146648",
                "ttd_target_id": "T1",
            }
        ],
    )
    _write_jsonl(
        raw_dir / "opentargets" / "drug_target_edges.jsonl",
        [
            {"target_symbol": "EGFR", "target_ensembl_id": "ENSG00000146648"},
            {"target_symbol": "EGFR", "target_ensembl_id": "ENSG00000146648"},
        ],
    )
    _write_jsonl(
        raw_dir / "dgidb" / "drug_gene_interactions.jsonl",
        [
            {"gene_symbol": "EGFR", "dgidb_gene_id": "123"},
            {"gene_symbol": "EGFR", "dgidb_gene_id": "123"},
        ],
    )

    counts = mod.generate_all_xrefs()

    assert counts == {"drug_xrefs": 5, "target_xrefs": 4}

    drug_xrefs = _load_xrefs(output_dir / "drug_xrefs.json")
    target_xrefs = _load_xrefs(output_dir / "target_xrefs.json")

    drug_keys = {
        (row["drug_id"], row["source_name"], row["source_id"]) for row in drug_xrefs
    }
    target_keys = {
        (row["target_id"], row["source_name"], row["source_id"]) for row in target_xrefs
    }

    assert len(drug_keys) == len(drug_xrefs)
    assert len(target_keys) == len(target_xrefs)

    assert [row["source_name"] for row in drug_xrefs] == [
        "ChEMBL",
        "DrugCentral",
        "KEGG",
        "PubChem",
        "RxNorm",
    ]
    assert [row["source_name"] for row in target_xrefs] == [
        "UniProt",
        "DGIdb",
        "Ensembl",
        "TTD",
    ]
