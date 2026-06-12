from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_REQUESTS_FILES = [
    "src/backend/etl/atc_orchestrator.py",
    "src/backend/etl/drug_etl.py",
    "src/backend/etl/fetch_atc_from_chembl.py",
    "src/backend/etl/fetch_atc_from_kegg.py",
    "src/backend/etl/atc_kegg_api_lookup.py",
]
ASYNC_HTTPX_IMPLEMENTATION_FILES = [
    "src/backend/etl/atc_lookup_service.py",
    "src/backend/etl/atc_enrichment_pipeline.py",
    "src/backend/etl/drug_metadata.py",
    "src/backend/etl/fetch_atc_from_chembl.py",
    "src/backend/etl/fetch_atc_from_kegg.py",
    "src/backend/etl/atc_kegg_api_lookup.py",
]


def test_legacy_requests_etl_files_use_httpx_instead():
    for relative_path in SYNC_REQUESTS_FILES:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert "import requests" not in source
        assert "requests." not in source
        assert "httpx.get(" not in source
        assert "httpx.post(" not in source
        assert "time.sleep(" not in source
        assert "ThreadPoolExecutor" not in source


def test_migrated_etl_http_boundaries_use_async_clients():
    for relative_path in ASYNC_HTTPX_IMPLEMENTATION_FILES:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert "httpx.AsyncClient" in source or "aiohttp.ClientSession" in source
        assert "httpx.get(" not in source
        assert "time.sleep(" not in source
