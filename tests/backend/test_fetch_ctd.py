from __future__ import annotations

import gzip
import json

import pytest

from src.backend.etl import fetch_ctd as mod


def _write_canonical_diseases(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "diseases": [
                    {
                        "id": "glioma",
                        "canonical_name": "Glioma",
                        "synonyms": ["Glioblastoma"],
                        "mesh_id": "MESH:D005910",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _gzip_text(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"))


def _canonical_lookup():
    return {
        "mesh:d005910": {
            "disease_id": "glioma",
            "disease_name": "Glioma",
        }
    }


def test_parse_ctd_rows_supports_flexible_header_and_normalizes_hash_prefixed_symbols():
    raw_bytes = _gzip_text("""
# CTD gene-disease associations
#   GeneSymbol	GeneID	DiseaseName	DiseaseID	DirectEvidence
#EGFR	1956	Glioma	MESH:D005910	marker
# this line should be skipped as a comment
TP53	7157	Glioblastoma	MESH:D005910	
""")

    # Header intentionally includes comment-like prefix and extra spacing
    rows = mod.parse_ctd_rows(raw_bytes, _canonical_lookup())

    assert len(rows) == 2
    assert rows[0]["target_id"] == "EGFR"
    assert rows[0]["target_symbol"] == "EGFR"
    assert rows[0]["evidence_type"] == "direct"
    assert rows[1]["target_id"] == "TP53"
    assert rows[1]["disease_id"] == "glioma"
    assert rows[1]["evidence_type"] == "inferred"


def test_parse_ctd_rows_skips_malformed_rows():
    raw_bytes = _gzip_text("""
GeneSymbol	GeneID	DiseaseName	DiseaseID	DirectEvidence
EGFR	1956	Glioma	MESH:D005910	marker
BAD			

TP53	7157	Unknown		marker
# comment only should be ignored
""")

    rows = mod.parse_ctd_rows(raw_bytes, _canonical_lookup())

    assert len(rows) == 1
    assert rows[0]["target_id"] == "EGFR"


@pytest.mark.asyncio
async def test_valid_gene_disease_fixture(monkeypatch, tmp_path):
    raw_dir = tmp_path / "raw" / "ctd"
    downloads_dir = raw_dir / "downloads"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_ctd_checkpoint.json"
    diseases_file = tmp_path / "data" / "diseases.json"
    _write_canonical_diseases(diseases_file)

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "DOWNLOADS_DIR", downloads_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)
    monkeypatch.setattr(mod, "DISEASES_FILE", diseases_file)

    async def fake_safe_get_bytes(client, url):
        return _gzip_text(
            """# CTD gene-disease associations
# GeneSymbol	GeneID	DiseaseName	DiseaseID	DirectEvidence	InferenceChemicalName	InferenceScore	OmimIDs	PubMedIDs
EGFR	1956	Glioma	MESH:D005910	marker/mechanism			12345
TP53	7157	Glioblastoma	MESH:D005910		Lead	0.8		67890
ALK	238	Unknown disease	MESH:UNKNOWN	therapeutic			99999
"""
        )

    monkeypatch.setattr(mod, "safe_get_bytes", fake_safe_get_bytes)

    summary = await mod.run()

    assert summary["status"] == "success"
    assert summary["record_count"] == 2
    output_path = raw_dir / "disease_edges.jsonl"
    assert output_path.exists()
    assert checkpoint_file.exists()

    rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [
        {
            "target_id": "EGFR",
            "target_symbol": "EGFR",
            "disease_id": "glioma",
            "disease_name": "Glioma",
            "disease_source_id": "MESH:D005910",
            "evidence_type": "direct",
            "source_name": "ctd",
            "source_record_id": "EGFR:MESH:D005910",
            "retrieved_at": rows[0]["retrieved_at"],
        },
        {
            "target_id": "TP53",
            "target_symbol": "TP53",
            "disease_id": "glioma",
            "disease_name": "Glioma",
            "disease_source_id": "MESH:D005910",
            "evidence_type": "inferred",
            "source_name": "ctd",
            "source_record_id": "TP53:MESH:D005910",
            "retrieved_at": rows[1]["retrieved_at"],
        },
    ]


@pytest.mark.asyncio
async def test_preserve_outputs_on_empty_download(monkeypatch, tmp_path):
    raw_dir = tmp_path / "raw" / "ctd"
    downloads_dir = raw_dir / "downloads"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_ctd_checkpoint.json"
    diseases_file = tmp_path / "data" / "diseases.json"
    output_path = raw_dir / "disease_edges.jsonl"

    _write_canonical_diseases(diseases_file)
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text('{"preserved": true}\n', encoding="utf-8")

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "DOWNLOADS_DIR", downloads_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)
    monkeypatch.setattr(mod, "DISEASES_FILE", diseases_file)

    async def fake_safe_get_bytes(client, url):
        return _gzip_text("""# comment only
# still empty
""")

    monkeypatch.setattr(mod, "safe_get_bytes", fake_safe_get_bytes)

    summary = await mod.run()

    assert summary["status"] == "preserved_previous_outputs"
    assert summary["record_count"] == 0
    assert summary["output_path"] == str(output_path)
    assert output_path.read_text(encoding="utf-8") == '{"preserved": true}\n'


@pytest.mark.asyncio
async def test_preserve_outputs_when_parse_yields_no_valid_records(
    monkeypatch, tmp_path
):
    raw_dir = tmp_path / "raw" / "ctd"
    downloads_dir = raw_dir / "downloads"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_ctd_checkpoint.json"
    diseases_file = tmp_path / "data" / "diseases.json"
    output_path = raw_dir / "disease_edges.jsonl"

    _write_canonical_diseases(diseases_file)
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text('{"kept": true}\n', encoding="utf-8")

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "DOWNLOADS_DIR", downloads_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)
    monkeypatch.setattr(mod, "DISEASES_FILE", diseases_file)

    async def fake_safe_get_bytes(client, url):
        return _gzip_text(
            """# GeneSymbol	GeneID	DiseaseName	DiseaseID	DirectEvidence
EGFR	1956	Unknown disease	MESH:UNKNOWN	marker
TP53	7157	Unknown disease		marker
# comment only should be skipped
"""
        )

    monkeypatch.setattr(mod, "safe_get_bytes", fake_safe_get_bytes)

    summary = await mod.run()

    assert summary["status"] == "preserved_previous_outputs"
    assert summary["record_count"] == 0
    assert summary["output_path"] == str(output_path)
    assert output_path.read_text(encoding="utf-8") == '{"kept": true}\n'
