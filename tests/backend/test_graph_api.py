import pytest


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
    response = await api_client.get("/api/v1/graph/evidence/simvastatin_to_atorvastatin")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert "source" in body[0]
    assert "confidence" in body[0]


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
