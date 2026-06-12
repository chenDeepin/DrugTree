import pytest

from src.backend.routers import admin as admin_router


@pytest.mark.asyncio
async def test_request_timing_header_is_exposed(api_client):
    response = await api_client.get("/api/v1/drugs", params={"limit": 5})

    assert response.status_code == 200
    assert "X-DrugTree-Request-Ms" in response.headers
    assert float(response.headers["X-DrugTree-Request-Ms"]) >= 0.0


@pytest.mark.asyncio
async def test_admin_performance_endpoint_returns_snapshot_and_metrics(api_client):
    await api_client.get("/api/v1/drugs", params={"limit": 5})
    response = await api_client.get("/api/v1/admin/performance")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_hash"]
    assert "request_metrics" in body
    assert "/api/v1/drugs" in body["request_metrics"]


@pytest.mark.asyncio
async def test_admin_refresh_endpoint_refreshes_snapshot_graph_and_query_cache(
    api_client, monkeypatch
):
    class Refreshable:
        def __init__(self):
            self.calls = 0

        def refresh(self):
            self.calls += 1

    snapshot = Refreshable()
    graph_index = Refreshable()
    graph_queries = Refreshable()

    monkeypatch.setattr(
        admin_router,
        "get_data_snapshot_service",
        lambda: snapshot,
        raising=False,
    )
    monkeypatch.setattr(
        admin_router,
        "get_graph_index",
        lambda: graph_index,
        raising=False,
    )
    monkeypatch.setattr(
        admin_router,
        "get_graph_query_service",
        lambda: graph_queries,
        raising=False,
    )

    response = await api_client.post("/api/v1/admin/refresh")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert snapshot.calls == 1
    assert graph_index.calls == 1
    assert graph_queries.calls == 1
