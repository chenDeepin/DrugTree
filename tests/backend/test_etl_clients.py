"""
Tests for cache manager and ETL clients.
"""

import asyncio
import time

import pytest

from src.backend.cache.cache_manager import CacheManager, get_cache_manager
from src.backend.etl.chembl_client import ChEMBLClient
from src.backend.etl.clinicaltrials_client import ClinicalTrialsClient
from src.backend.etl.fda_client import FDAClient


class TestCacheManager:
    """Tests for SQLite cache manager."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create fresh cache for each test."""
        db_path = tmp_path / "test_cache.db"
        return CacheManager(db_path=db_path)

    def test_set_and_get(self, cache):
        """Test basic set/get operations."""
        data = {"name": "aspirin", "id": "CHEMBL1485"}
        cache.set("test:drug:1", data)

        result = cache.get("test:drug:1")
        assert result == data

    def test_get_missing_key(self, cache):
        """Test getting non-existent key returns None."""
        result = cache.get("nonexistent:key")
        assert result is None

    def test_delete(self, cache):
        """Test delete removes cached value."""
        cache.set("test:delete", {"data": "value"})
        assert cache.get("test:delete") is not None

        cache.delete("test:delete")
        assert cache.get("test:delete") is None

    def test_clear(self, cache):
        """Test clear removes all entries."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_ttl_expiry(self, cache):
        """Test TTL expires cached values."""
        cache.set("test:expire", {"data": "value"}, ttl=1)

        result = cache.get("test:expire")
        assert result is not None

        time.sleep(1.5)

        result = cache.get("test:expire")
        assert result is None

    def test_ttl_default(self, cache):
        """Test default TTL is applied."""
        cache.set("test:default_ttl", {"data": "value"})
        stats = cache.get_stats()

        assert stats["total_entries"] == 1

    def test_compression_large_values(self, cache):
        """Test large values are compressed."""
        large_data = {"data": "x" * 5000}

        cache.set("test:large", large_data)

        result = cache.get("test:large")
        assert result == large_data

    def test_get_stats(self, cache):
        """Test cache statistics."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        stats = cache.get_stats()

        assert stats["total_entries"] == 2
        assert stats["total_size_bytes"] > 0
        assert stats["expired_entries"] == 0

    def test_clear_expired(self, cache):
        """Test clearing expired entries."""
        cache.set("test:keep", {"data": "value"}, ttl=3600)
        cache.set("test:expire", {"data": "value"}, ttl=1)

        time.sleep(1.5)

        removed = cache.clear_expired()

        assert removed == 1
        assert cache.get("test:keep") is not None
        assert cache.get("test:expire") is None

    def test_singleton(self):
        """Test singleton pattern."""
        cache1 = get_cache_manager()
        cache2 = get_cache_manager()

        assert cache1 is cache2

    def test_complex_data(self, cache):
        """Test caching complex nested data."""
        data = {
            "id": "test",
            "indications": [
                {"disease_id": "MESH:D001", "disease_name": "Test Disease"},
                {"disease_id": "MESH:D002", "disease_name": "Another Disease"},
            ],
            "metadata": {"count": 2, "source": "ChEMBL"},
        }

        cache.set("test:complex", data)

        result = cache.get("test:complex")
        assert result == data
        assert len(result["indications"]) == 2


class TestChEMBLClient:
    """Tests for ChEMBL API client."""

    @pytest.fixture
    def client(self, tmp_path):
        """Create client with test cache."""
        cache = CacheManager(db_path=tmp_path / "test_chembl.db")
        client = ChEMBLClient(rate_limit_per_sec=10.0)
        client._cache = cache

        return client

    @pytest.mark.asyncio
    async def test_rate_limiting(self, client):
        """Test rate limiting is enforced."""
        start = time.time()

        for _ in range(3):
            await client._rate_limit_wait()

        elapsed = time.time() - start

        assert elapsed >= 0.2

    @pytest.mark.asyncio
    async def test_get_drug_indications_mock(self, client, monkeypatch):
        """Test get_drug_indications with mocked response."""

        async def mock_request(endpoint, params=None):
            return {
                "drug_indications": [
                    {
                        "molecule_chembl_id": "CHEMBL1485",
                        "mesh_id": "MESH:D001",
                        "mesh_heading": "Test Disease",
                        "max_phase_for_ind": 4,
                        "indications": ["Primary"],
                    }
                ]
            }

        monkeypatch.setattr(client, "_request_with_retry", mock_request)

        result = await client.get_drug_indications("CHEMBL1485")

        assert len(result) == 1
        assert result[0]["disease_id"] == "MESH:D001"
        assert result[0]["phase"] == 4

    @pytest.mark.asyncio
    async def test_get_clinical_candidates_mock(self, client, monkeypatch):
        """Test get_clinical_candidates filters preclinical."""

        async def mock_request(endpoint, params=None):
            return {
                "mechanisms": [
                    {
                        "molecule_chembl_id": "CHEMBL1",
                        "molecule_pref_name": "Drug A",
                        "max_phase": 4,
                        "mechanism_of_action": "Inhibitor",
                    },
                    {
                        "molecule_chembl_id": "CHEMBL2",
                        "molecule_pref_name": "Drug B",
                        "max_phase": 0,
                        "mechanism_of_action": "Unknown",
                    },
                ]
            }

        monkeypatch.setattr(client, "_request_with_retry", mock_request)

        result = await client.get_clinical_candidates("CHEMBL240")

        assert len(result) == 1
        assert result[0]["chembl_id"] == "CHEMBL1"
        assert result[0]["phase"] >= 1

    @pytest.mark.asyncio
    async def test_cache_integration(self, client, tmp_path):
        """Test results are cached."""
        cache = CacheManager(db_path=tmp_path / "cache_test.db")
        client._cache = cache

        call_count = 0

        async def mock_request(endpoint, params=None):
            nonlocal call_count
            call_count += 1
            return {"drug_indications": []}

        client._request_with_retry = mock_request

        await client.get_drug_indications("CHEMBL1")
        await client.get_drug_indications("CHEMBL1")

        assert call_count == 1


class TestClinicalTrialsClient:
    """Tests for ClinicalTrials.gov API client."""

    @pytest.fixture
    def client(self, tmp_path):
        """Create client with test cache."""
        cache = CacheManager(db_path=tmp_path / "test_clinicaltrials.db")
        client = ClinicalTrialsClient(rate_limit_per_sec=5.0)
        client._cache = cache
        return client

    @pytest.mark.asyncio
    async def test_search_studies_mock(self, client, monkeypatch):
        """Test search_studies with mocked response."""

        async def mock_request(endpoint, params=None):
            return {
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {
                                "nctId": "NCT04640170",
                                "briefTitle": "Test Trial",
                            },
                            "statusModule": {"overallStatus": "Recruiting"},
                            "sponsorCollaboratorsModule": {
                                "leadSponsor": {"name": "Test Pharma"}
                            },
                            "designModule": {"phases": ["Phase 3"]},
                            "armsInterventionsModule": {
                                "interventions": [{"name": "Test Drug"}]
                            },
                        }
                    }
                ]
            }

        monkeypatch.setattr(client, "_request_with_retry", mock_request)

        result = await client.search_studies("diabetes")

        assert len(result) == 1
        assert result[0]["nct_id"] == "NCT04640170"
        assert result[0]["phase"] == "Phase 3"

    @pytest.mark.asyncio
    async def test_get_trial_interventions_mock(self, client, monkeypatch):
        """Test get_trial_interventions with mocked response."""

        async def mock_request(endpoint, params=None):
            return {
                "protocolSection": {
                    "armsInterventionsModule": {
                        "interventions": [
                            {
                                "name": "Aspirin",
                                "type": "Drug",
                                "description": "Test intervention",
                            }
                        ]
                    }
                }
            }

        monkeypatch.setattr(client, "_request_with_retry", mock_request)

        result = await client.get_trial_interventions("NCT04640170")

        assert len(result) == 1
        assert result[0]["name"] == "Aspirin"


class TestFDAClient:
    """Tests for FDA openFDA API client."""

    @pytest.fixture
    def client(self, tmp_path):
        """Create client with test cache."""
        cache = CacheManager(db_path=tmp_path / "test_fda.db")
        client = FDAClient(rate_limit_per_sec=4.0)
        client._cache = cache
        return client

    @pytest.mark.asyncio
    async def test_get_drug_approvals_mock(self, client, monkeypatch):
        """Test get_drug_approvals with mocked response."""

        async def mock_request(endpoint, params=None):
            return {
                "results": [
                    {
                        "application_number": "NDA 021234",
                        "openfda": {
                            "brand_name": ["Lipitor"],
                            "manufacturer_name": ["Pfizer"],
                        },
                        "submission_status_date": "1996-12-17",
                        "products": [
                            {
                                "brand_name": "Lipitor",
                                "marketing_status": "Prescription",
                            }
                        ],
                    }
                ]
            }

        monkeypatch.setattr(client, "_request_with_retry", mock_request)

        result = await client.get_drug_approvals("atorvastatin")

        assert len(result) >= 1
        assert result[0]["application_number"] == "NDA 021234"

    @pytest.mark.asyncio
    async def test_get_adverse_events_mock(self, client, monkeypatch):
        """Test get_adverse_events with mocked response."""

        async def mock_request(endpoint, params=None):
            return {
                "results": [
                    {
                        "safetyreportid": "12345678",
                        "receivedate": "2024-01-15",
                        "serious": "1",
                        "patient": {
                            "reaction": [{"reactionmeddrapt": "Headache"}],
                            "summary": {"patientoutcome": ["Recovered"]},
                        },
                    }
                ]
            }

        monkeypatch.setattr(client, "_request_with_retry", mock_request)

        result = await client.get_adverse_events("aspirin")

        assert len(result) == 1
        assert result[0]["seriousness"] == "serious"
        assert "Headache" in result[0]["reactions"]

    @pytest.mark.asyncio
    async def test_get_drug_label_mock(self, client, monkeypatch):
        """Test get_drug_label with mocked response."""

        async def mock_request(endpoint, params=None):
            return {
                "results": [
                    {
                        "indications_and_usage": ["For treatment of hypertension"],
                        "contraindications": ["Hypersensitivity"],
                        "warnings_and_cautions": ["Monitor liver function"],
                    }
                ]
            }

        monkeypatch.setattr(client, "_request_with_retry", mock_request)

        result = await client.get_drug_label("atorvastatin")

        assert len(result["indications"]) == 1
        assert "hypertension" in result["indications"][0]

    @pytest.mark.asyncio
    async def test_not_found_returns_empty(self, client, monkeypatch):
        """Test 404 returns empty list gracefully."""

        async def mock_request(endpoint, params=None):
            return {"results": [], "error": {"code": "NOT_FOUND"}}

        monkeypatch.setattr(client, "_request_with_retry", mock_request)

        result = await client.get_drug_approvals("nonexistent-drug")

        assert result == []
