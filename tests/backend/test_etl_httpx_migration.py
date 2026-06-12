from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_REQUESTS_FILES = [
    "src/backend/etl/atc_orchestrator.py",
    "src/backend/etl/drug_etl.py",
    "src/backend/etl/fetch_atc_from_chembl.py",
    "src/backend/etl/fetch_atc_from_kegg.py",
    "src/backend/etl/atc_kegg_api_lookup.py",
]


def test_legacy_requests_etl_files_use_httpx_instead():
    for relative_path in SYNC_REQUESTS_FILES:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert "import requests" not in source
        assert "requests." not in source
        assert "import httpx" in source
        assert "httpx.get(" not in source
        assert "httpx.post(" not in source
        assert "time.sleep(" not in source
        assert "ThreadPoolExecutor" not in source
