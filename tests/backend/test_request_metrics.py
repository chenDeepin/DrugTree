import pytest


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
