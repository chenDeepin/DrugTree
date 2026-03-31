import pytest


@pytest.mark.asyncio
async def test_root_returns_html_landing_page_for_browser_requests(api_client):
    response = await api_client.get(
        "/",
        headers={
            "accept": "text/html",
            "host": "127.0.0.1:8000",
        },
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "This address serves the API, not the atlas UI." in response.text
    assert "Open the DrugTree frontend" in response.text
    assert "cd src/frontend" in response.text


@pytest.mark.asyncio
async def test_root_keeps_json_payload_for_api_clients(api_client):
    response = await api_client.get("/", headers={"accept": "application/json"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "name": "DrugTree API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "drugs": "/api/v1/drugs",
            "diseases": "/api/v1/diseases",
            "health": "/health",
            "search": "/api/v1/drugs/search",
        },
    }
