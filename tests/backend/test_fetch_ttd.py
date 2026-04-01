from __future__ import annotations

import io
import json
import zipfile

import pytest

from src.backend.etl import fetch_ttd as mod


def _write_existing_outputs(raw_dir):
    raw_dir.mkdir(parents=True, exist_ok=True)
    targets_path = raw_dir / "targets.json"
    drug_edges_path = raw_dir / "drug_target_edges.json"
    disease_edges_path = raw_dir / "disease_target_edges.json"
    targets_path.write_text('[{"ttd_target_id": "OLD"}]\n', encoding="utf-8")
    drug_edges_path.write_text('[{"drug_name": "Old drug"}]\n', encoding="utf-8")
    disease_edges_path.write_text(
        '[{"disease_name": "Old disease"}]\n', encoding="utf-8"
    )
    return targets_path, drug_edges_path, disease_edges_path


def _build_ttd_zip_payload() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "target_overview.tsv",
            "ttd_target_id\tgene_symbol\tgene_name\tuniprot_id\tvalidated\n"
            "T1\tEGFR\tEpidermal growth factor receptor\tP00533\tyes\n",
        )
        archive.writestr(
            "drugtarget.tsv",
            "ttd_target_id\tdrug_name\tclinical_status\nT1\tGefitinib\tApproved\n",
        )
        archive.writestr(
            "disease_associations.tsv",
            "ttd_target_id\tdisease_name\nT1\tNon-small cell lung cancer\n",
        )
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_discover_downloads_includes_tsv_links_from_html_fallback(monkeypatch):
    async def fake_safe_get_json(client, url):
        return None

    async def fake_safe_get_text(client, url):
        return '<a href="files/TTD_target_download.tsv">download</a>'

    monkeypatch.setattr(mod, "safe_get_json", fake_safe_get_json)
    monkeypatch.setattr(mod, "safe_get_text", fake_safe_get_text)

    async with mod.httpx.AsyncClient() as client:
        urls = await mod.discover_downloads(client)

    assert any(url.endswith("TTD_target_download.tsv") for url in urls)


@pytest.mark.asyncio
async def test_valid_tabular_payload_writes_ttd_outputs(monkeypatch, tmp_path):
    raw_dir = tmp_path / "raw" / "ttd"
    downloads_dir = raw_dir / "downloads"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_ttd_checkpoint.json"

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "DOWNLOADS_DIR", downloads_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)

    async def fake_discover_downloads(client):
        return ["https://example.org/ttd_bundle.zip"]

    async def fake_safe_get_bytes(client, url):
        return _build_ttd_zip_payload()

    monkeypatch.setattr(mod, "discover_downloads", fake_discover_downloads)
    monkeypatch.setattr(mod, "safe_get_bytes", fake_safe_get_bytes)

    summary = await mod.run(download_limit=5)

    assert summary["status"] == "success"
    assert summary["targets"]["count"] == 1
    assert summary["drug_target_edges"]["count"] == 1
    assert summary["disease_target_edges"]["count"] == 1

    targets = json.loads((raw_dir / "targets.json").read_text(encoding="utf-8"))
    drug_edges = json.loads(
        (raw_dir / "drug_target_edges.json").read_text(encoding="utf-8")
    )
    disease_edges = json.loads(
        (raw_dir / "disease_target_edges.json").read_text(encoding="utf-8")
    )

    assert targets[0]["gene_symbol"] == "EGFR"
    assert drug_edges[0]["drug_name"] == "Gefitinib"
    assert disease_edges[0]["disease_name"] == "Non-small cell lung cancer"


@pytest.mark.asyncio
async def test_preserve_outputs_on_no_candidate_urls(monkeypatch, tmp_path):
    raw_dir = tmp_path / "raw" / "ttd"
    downloads_dir = raw_dir / "downloads"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_ttd_checkpoint.json"
    targets_path, drug_edges_path, disease_edges_path = _write_existing_outputs(raw_dir)

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "DOWNLOADS_DIR", downloads_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)

    async def fake_discover_downloads(client):
        return []

    monkeypatch.setattr(mod, "discover_downloads", fake_discover_downloads)

    summary = await mod.run(download_limit=5)

    assert summary["status"] == "no_candidate_urls"
    assert summary["targets"]["output_path"] == str(targets_path)
    assert summary["drug_target_edges"]["output_path"] == str(drug_edges_path)
    assert summary["disease_target_edges"]["output_path"] == str(disease_edges_path)
    assert targets_path.read_text(encoding="utf-8") == '[{"ttd_target_id": "OLD"}]\n'
    assert (
        drug_edges_path.read_text(encoding="utf-8") == '[{"drug_name": "Old drug"}]\n'
    )
    assert (
        disease_edges_path.read_text(encoding="utf-8")
        == '[{"disease_name": "Old disease"}]\n'
    )


@pytest.mark.asyncio
async def test_preserve_outputs_on_unparseable_downloads(monkeypatch, tmp_path):
    raw_dir = tmp_path / "raw" / "ttd"
    downloads_dir = raw_dir / "downloads"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_ttd_checkpoint.json"
    targets_path, drug_edges_path, disease_edges_path = _write_existing_outputs(raw_dir)

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "DOWNLOADS_DIR", downloads_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)

    async def fake_discover_downloads(client):
        return ["https://example.org/unparseable.txt"]

    async def fake_safe_get_bytes(client, url):
        return b"<html><body>blocked</body></html>"

    monkeypatch.setattr(mod, "discover_downloads", fake_discover_downloads)
    monkeypatch.setattr(mod, "safe_get_bytes", fake_safe_get_bytes)

    summary = await mod.run(download_limit=5)

    assert summary["status"] == "downloaded_but_unparseable"
    assert summary["targets"]["output_path"] == str(targets_path)
    assert summary["drug_target_edges"]["output_path"] == str(drug_edges_path)
    assert summary["disease_target_edges"]["output_path"] == str(disease_edges_path)
    assert targets_path.read_text(encoding="utf-8") == '[{"ttd_target_id": "OLD"}]\n'
    assert (
        drug_edges_path.read_text(encoding="utf-8") == '[{"drug_name": "Old drug"}]\n'
    )
    assert (
        disease_edges_path.read_text(encoding="utf-8")
        == '[{"disease_name": "Old disease"}]\n'
    )


@pytest.mark.asyncio
async def test_partial_valid_download_marks_partial_and_writes_outputs(
    monkeypatch, tmp_path
):
    raw_dir = tmp_path / "raw" / "ttd"
    downloads_dir = raw_dir / "downloads"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_ttd_checkpoint.json"

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "DOWNLOADS_DIR", downloads_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)

    async def fake_discover_downloads(client):
        return [
            "https://example.org/ttd_bundle.zip",
            "https://example.org/unparseable.txt",
        ]

    async def fake_safe_get_bytes(client, url):
        if url.endswith("ttd_bundle.zip"):
            return _build_ttd_zip_payload()
        return b"not a tabular dataset"

    monkeypatch.setattr(mod, "discover_downloads", fake_discover_downloads)
    monkeypatch.setattr(mod, "safe_get_bytes", fake_safe_get_bytes)

    summary = await mod.run(download_limit=5)

    assert summary["status"] == "partial"
    assert summary["targets"]["count"] == 1
    assert summary["drug_target_edges"]["count"] == 1
    assert summary["disease_target_edges"]["count"] == 1
    assert (raw_dir / "targets.json").exists()
    assert (raw_dir / "drug_target_edges.json").exists()
    assert (raw_dir / "disease_target_edges.json").exists()
