import json
import pytest
from pathlib import Path

from src.backend.etl import load_graph_edges
from src.backend.routers import targets as targets_router


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_targets_list_endpoint_returns_paginated_results(api_client):
    response = await api_client.get("/api/v1/targets", params={"limit": 5, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert len(body["targets"]) <= 5
    assert body["targets"]
    first_target = body["targets"][0]
    assert "id" in first_target
    assert "symbol" in first_target
    assert "name" in first_target
    assert isinstance(first_target["disease_ids"], list)
    assert isinstance(first_target["pathway_ids"], list)


@pytest.mark.asyncio
async def test_targets_list_endpoint_supports_search(api_client):
    response = await api_client.get("/api/v1/targets", params={"search": "adrb1"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(target["id"] == "ADRB1" for target in body["targets"])


@pytest.mark.asyncio
async def test_target_detail_endpoint_includes_edges(api_client):
    response = await api_client.get("/api/v1/targets/ADRB1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "ADRB1"
    assert body["symbol"] == "ADRB1"
    assert isinstance(body["drug_connections"], list)
    assert isinstance(body["disease_associations"], list)
    assert isinstance(body["xrefs"], list)
    assert body["drug_connections"]
    assert body["disease_associations"]
    assert body["xrefs"]


@pytest.mark.asyncio
async def test_target_detail_endpoint_returns_404_for_missing_target(api_client):
    response = await api_client.get("/api/v1/targets/__missing__")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_target_detail_endpoint_reads_from_smoke_db(
    api_client, monkeypatch, tmp_path
):
    db_path = tmp_path / "smoke.sqlite"

    load_graph_edges.load_all(str(db_path))
    monkeypatch.setattr(targets_router, "DB_PATH", db_path)

    target_path = REPO_ROOT / "data" / "processed" / "nodes_target.jsonl"
    first_target_id = None
    for line in target_path.read_text(encoding="utf-8").splitlines():
        if line:
            first_target_id = json.loads(line)["node_id"]
            break

    assert first_target_id is not None

    response = await api_client.get(f"/api/v1/targets/{first_target_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == first_target_id
