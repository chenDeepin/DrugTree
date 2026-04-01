import json
import os
from pathlib import Path
import pytest
from typing import Any, cast

from src.backend.services.graph_queries import GraphQueryService


REPO_ROOT = Path(__file__).resolve().parents[2]


def _first_processed_edge_id(file_name: str) -> str:
    path = REPO_ROOT / "data" / "processed" / file_name
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            return str(json.loads(line)["edge_id"])
    raise AssertionError(f"No edge IDs found in {path}")


class _StubGraphIndex:
    def __init__(self):
        self._edges = {}

    def get_all_edges(self):
        return []


class _StubSnapshot:
    source_hash = "test-hash"
    disease_drug_edges = []
    diseases = []


class _StubSnapshotService:
    def get_snapshot(self, force_refresh: bool = False):
        return _StubSnapshot()


def _stub_graph_service() -> GraphQueryService:
    return GraphQueryService(
        graph_index=cast(Any, _StubGraphIndex()),
        snapshot_service=cast(Any, _StubSnapshotService()),
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _touch(path: Path) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))


@pytest.mark.asyncio
async def test_graph_node_lookup_success(api_client):
    response = await api_client.get("/api/v1/graph/node/drug:atorvastatin")
    assert response.status_code == 200

    body = response.json()
    assert body["node_id"] == "drug:atorvastatin"
    assert body["node_type"] == "drug"
    assert "label" in body


@pytest.mark.asyncio
async def test_graph_node_lookup_not_found(api_client):
    response = await api_client.get("/api/v1/graph/node/drug:__missing__")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_graph_target_node_lookup_not_found(api_client):
    response = await api_client.get("/api/v1/graph/node/target:__missing__")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_graph_neighborhood_endpoint(api_client):
    response = await api_client.get(
        "/api/v1/graph/neighborhood/drug:atorvastatin", params={"max_hops": 1}
    )
    assert response.status_code == 200

    body = response.json()
    assert body["center_node"]["node_id"] == "drug:atorvastatin"
    assert isinstance(body["edges"], list)
    assert isinstance(body["neighbor_nodes"], list)
    assert all(edge.get("evidence") == [] for edge in body["edges"])


@pytest.mark.asyncio
async def test_graph_evidence_endpoint(api_client):
    response = await api_client.get(
        "/api/v1/graph/evidence/simvastatin_to_atorvastatin"
    )
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert "source" in body[0]
    assert "confidence" in body[0]


@pytest.mark.asyncio
async def test_graph_evidence_endpoint_returns_drug_target_evidence(
    api_client, monkeypatch
):
    from src.backend.routers import graph as graph_router

    service = _stub_graph_service()
    monkeypatch.setattr(
        service,
        "_load_drug_target_edges_jsonl",
        lambda: [
            {
                "edge_id": "drug_target:gefitinib:EGFR:inhibitor",
                "confidence": 0.9,
                "extra": {
                    "drug_id": "gefitinib",
                    "target_id": "EGFR",
                    "interaction_type": "inhibitor",
                    "evidence_sources": ["Open Targets"],
                    "clinical_phase": 4,
                    "retrieved_at": "2026-01-01T00:00:00Z",
                },
            }
        ],
    )
    monkeypatch.setattr(service, "_load_target_disease_edges_jsonl", lambda: [])
    monkeypatch.setattr(graph_router, "get_graph_query_service", lambda: service)

    response = await api_client.get(
        "/api/v1/graph/evidence/drug_target:gefitinib:EGFR:inhibitor"
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["source"] == "Open Targets"
    assert body[0]["source_type"] == "database"
    assert body[0]["confidence"] == 0.9
    assert "inhibitor" in body[0]["description"]


@pytest.mark.asyncio
async def test_graph_evidence_endpoint_returns_target_disease_evidence(
    api_client, monkeypatch
):
    from src.backend.routers import graph as graph_router

    service = _stub_graph_service()
    monkeypatch.setattr(service, "_load_drug_target_edges_jsonl", lambda: [])
    monkeypatch.setattr(
        service,
        "_load_target_disease_edges_jsonl",
        lambda: [
            {
                "edge_id": "target_disease:EGFR:glioma:direct",
                "confidence": 0.7,
                "extra": {
                    "target_id": "EGFR",
                    "disease_id": "glioma",
                    "association_score": 82.0,
                    "evidence_type": "direct",
                    "evidence_sources": ["CTD"],
                    "retrieved_at": "2026-01-01T00:00:00Z",
                },
            }
        ],
    )
    monkeypatch.setattr(graph_router, "get_graph_query_service", lambda: service)

    response = await api_client.get(
        "/api/v1/graph/evidence/target_disease:EGFR:glioma:direct"
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["source"] == "CTD"
    assert body[0]["source_type"] == "database"
    assert body[0]["confidence"] == 0.7
    assert "direct" in body[0]["description"]


@pytest.mark.asyncio
async def test_graph_evidence_endpoint_returns_404_for_unknown_edge(api_client):
    response = await api_client.get("/api/v1/graph/evidence/__missing_edge__")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_graph_evidence_endpoint_uses_real_processed_drug_target_edge(api_client):
    edge_id = _first_processed_edge_id("edges_drug_target.jsonl")

    response = await api_client.get(f"/api/v1/graph/evidence/{edge_id}")

    assert response.status_code == 200
    body = response.json()
    assert body
    assert all(entry["source_type"] == "database" for entry in body)


def test_graph_query_service_refreshes_target_nodes_without_restart(
    monkeypatch, tmp_path
):
    service = _stub_graph_service()
    target_path = tmp_path / "nodes_target.jsonl"
    drug_target_path = tmp_path / "edges_drug_target.jsonl"
    target_disease_path = tmp_path / "edges_target_disease.jsonl"

    _write_jsonl(
        target_path,
        [
            {
                "node_id": "EGFR",
                "label": "EGFR",
                "extra": {"name": "EGFR", "disease_ids": []},
            }
        ],
    )
    _write_jsonl(drug_target_path, [])
    _write_jsonl(target_disease_path, [])

    monkeypatch.setattr(service, "_target_nodes_path", lambda: target_path)
    monkeypatch.setattr(service, "_drug_target_edges_path", lambda: drug_target_path)
    monkeypatch.setattr(
        service, "_target_disease_edges_path", lambda: target_disease_path
    )

    assert service.get_node("target:EGFR") is not None
    assert service.get_node("target:ALK") is None

    _write_jsonl(
        target_path,
        [
            {
                "node_id": "ALK",
                "label": "ALK",
                "extra": {"name": "ALK", "disease_ids": []},
            }
        ],
    )
    _touch(target_path)

    assert service.get_node("target:EGFR") is None
    refreshed = service.get_node("target:ALK")
    assert refreshed is not None
    assert refreshed.node_id == "target:ALK"


def test_graph_query_service_refreshes_etl_evidence_without_restart(
    monkeypatch, tmp_path
):
    service = _stub_graph_service()
    target_path = tmp_path / "nodes_target.jsonl"
    drug_target_path = tmp_path / "edges_drug_target.jsonl"
    target_disease_path = tmp_path / "edges_target_disease.jsonl"
    edge_id = "drug_target:gefitinib:EGFR:inhibitor"

    _write_jsonl(target_path, [])
    _write_jsonl(
        drug_target_path,
        [
            {
                "edge_id": edge_id,
                "confidence": 0.4,
                "extra": {
                    "drug_id": "gefitinib",
                    "target_id": "EGFR",
                    "interaction_type": "inhibitor",
                    "evidence_sources": ["Open Targets"],
                },
            }
        ],
    )
    _write_jsonl(target_disease_path, [])

    monkeypatch.setattr(service, "_target_nodes_path", lambda: target_path)
    monkeypatch.setattr(service, "_drug_target_edges_path", lambda: drug_target_path)
    monkeypatch.setattr(
        service, "_target_disease_edges_path", lambda: target_disease_path
    )

    first = service.get_evidence(edge_id)
    assert first[0].confidence == 0.4
    assert first[0].source == "Open Targets"

    _write_jsonl(
        drug_target_path,
        [
            {
                "edge_id": edge_id,
                "confidence": 0.9,
                "extra": {
                    "drug_id": "gefitinib",
                    "target_id": "EGFR",
                    "interaction_type": "inhibitor",
                    "evidence_sources": ["Updated Source"],
                },
            }
        ],
    )
    _touch(drug_target_path)

    refreshed = service.get_evidence(edge_id)
    assert refreshed[0].confidence == 0.9
    assert refreshed[0].source == "Updated Source"


@pytest.mark.asyncio
async def test_graph_subgraph_endpoint(api_client):
    response = await api_client.get(
        "/api/v1/graph/subgraph",
        params={"node_ids": "drug:simvastatin,drug:atorvastatin"},
    )
    assert response.status_code == 200

    body = response.json()
    assert "nodes" in body
    assert "edges" in body
    assert body["total_nodes"] >= 1
    assert body["total_edges"] >= 0
    assert all(edge.get("evidence") == [] for edge in body["edges"])
