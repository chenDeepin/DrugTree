import json
import pytest
from pathlib import Path

from src.backend.etl import load_graph_edges
from src.backend.routers import targets as targets_router
from src.backend.routers.targets import (
    TargetDetailResponse,
    TargetListResponse,
    TargetResponse,
)


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
async def test_targets_list_runs_sqlite_work_in_threadpool(monkeypatch):
    calls = []

    async def fake_run_in_threadpool(func, *args, **kwargs):
        calls.append(func.__name__)
        return TargetListResponse(
            total=1,
            targets=[TargetResponse(id="T1", symbol="T1", name="Target 1")],
        )

    monkeypatch.setattr(
        targets_router, "run_in_threadpool", fake_run_in_threadpool, raising=False
    )

    response = await targets_router.list_targets(limit=1, offset=0)

    assert response.total == 1
    assert calls == ["_list_targets_sync"]


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


def test_target_detail_sync_uses_one_compound_execute(monkeypatch):
    execute_calls = []
    target_row = {
        "row_kind": "target",
        "id": "T1",
        "symbol": "T1",
        "name": "Target 1",
        "modality": "protein",
        "disease_ids": "[]",
        "uniprot_id": None,
        "hgnc_id": None,
        "entrez_id": None,
        "ensembl_gene_id": None,
        "gene_type": "protein_coding",
        "pathway_ids": "[]",
        "druggability": "unknown",
        "is_validated_target": 1,
        "drug_id": None,
        "drug_name": None,
        "interaction_type": None,
        "mechanism_of_action": None,
        "drug_confidence": None,
        "associated_disease_id": None,
        "disease_name": None,
        "association_score": None,
        "evidence_type": None,
        "disease_confidence": None,
        "source_name": None,
        "source_id": None,
        "source_url": None,
    }

    class FakeCursor:
        def fetchall(self):
            return [target_row]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params):
            execute_calls.append((query, params))
            return FakeCursor()

    monkeypatch.setattr(targets_router, "get_db_connection", lambda: FakeConnection())

    response = targets_router._get_target_sync("T1")

    assert response.id == "T1"
    assert len(execute_calls) == 1
    assert "WITH target AS" in execute_calls[0][0]


@pytest.mark.asyncio
async def test_target_detail_runs_sqlite_work_in_one_threadpool_call(monkeypatch):
    calls = []

    async def fake_run_in_threadpool(func, *args, **kwargs):
        calls.append(func.__name__)
        return TargetDetailResponse(
            id="T1",
            symbol="T1",
            name="Target 1",
            drug_connections=[],
            disease_associations=[],
            xrefs=[],
        )

    monkeypatch.setattr(
        targets_router, "run_in_threadpool", fake_run_in_threadpool, raising=False
    )

    response = await targets_router.get_target("T1")

    assert response.id == "T1"
    assert calls == ["_get_target_sync"]


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
