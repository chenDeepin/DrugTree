from fastapi.testclient import TestClient

from src.backend.main import app


client = TestClient(app)


def test_graph_node_lookup_success():
    response = client.get("/api/v1/graph/node/drug:atorvastatin")
    assert response.status_code == 200

    body = response.json()
    assert body["node_id"] == "drug:atorvastatin"
    assert body["node_type"] == "drug"
    assert "label" in body


def test_graph_node_lookup_not_found():
    response = client.get("/api/v1/graph/node/drug:__missing__")
    assert response.status_code == 404


def test_graph_neighborhood_endpoint():
    response = client.get(
        "/api/v1/graph/neighborhood/drug:atorvastatin", params={"max_hops": 1}
    )
    assert response.status_code == 200

    body = response.json()
    assert body["center_node"]["node_id"] == "drug:atorvastatin"
    assert isinstance(body["edges"], list)
    assert isinstance(body["neighbor_nodes"], list)


def test_graph_evidence_endpoint():
    response = client.get("/api/v1/graph/evidence/simvastatin_to_atorvastatin")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert "source" in body[0]
    assert "confidence" in body[0]


def test_graph_subgraph_endpoint():
    response = client.get(
        "/api/v1/graph/subgraph",
        params={"node_ids": "drug:simvastatin,drug:atorvastatin"},
    )
    assert response.status_code == 200

    body = response.json()
    assert "nodes" in body
    assert "edges" in body
    assert body["total_nodes"] >= 1
    assert body["total_edges"] >= 0
