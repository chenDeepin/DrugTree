"""
Disease Universe API Tests

Tests for disease endpoints, filtering, and statistics.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json

from src.backend.main import app
from src.backend.models.disease import Disease, PrevalenceTier, EvidenceLevel


client = TestClient(app)


@pytest.fixture
def sample_diseases():
    return [
        Disease(
            id="glioma",
            canonical_name="Glioma",
            synonyms=["brain tumor", "glioblastoma"],
            body_region="brain_cns",
            anatomy_nodes=["brain", "cerebrum"],
            orphan_flag=False,
            prevalence_tier=PrevalenceTier.UNCOMMON,
            prevalence_count=300000,
            evidence_level=EvidenceLevel.APPROVED,
            target_count=15,
            approved_drug_count=3,
            clinical_drug_count=12,
        ),
        Disease(
            id="alzheimers_disease",
            canonical_name="Alzheimer's Disease",
            synonyms=["AD", "dementia"],
            body_region="brain_cns",
            anatomy_nodes=["brain"],
            orphan_flag=False,
            prevalence_tier=PrevalenceTier.COMMON,
            prevalence_count=55000000,
            evidence_level=EvidenceLevel.APPROVED,
            target_count=8,
            approved_drug_count=7,
            clinical_drug_count=25,
        ),
        Disease(
            id="cystic_fibrosis",
            canonical_name="Cystic Fibrosis",
            synonyms=["CF", "mucoviscidosis"],
            body_region="lung_respiratory",
            anatomy_nodes=["lung", "tracheobronchial_tree"],
            orphan_flag=True,
            prevalence_tier=PrevalenceTier.RARE,
            prevalence_count=70000,
            evidence_level=EvidenceLevel.APPROVED,
            target_count=4,
            approved_drug_count=12,
            clinical_drug_count=8,
        ),
    ]


class TestDiseaseEndpoints:
    def test_list_diseases_empty(self):
        with patch("src.backend.routers.diseases.load_diseases", return_value=[]):
            response = client.get("/api/v1/diseases")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert data["diseases"] == []

    def test_list_diseases_with_data(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 3
            assert len(data["diseases"]) == 3

    def test_filter_by_region(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases?region=brain_cns")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            for d in data["diseases"]:
                assert d["body_region"] == "brain_cns"

    def test_filter_orphan_only(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases?orphan_only=true")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["diseases"][0]["id"] == "cystic_fibrosis"

    def test_filter_has_approved_drugs(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases?has_approved_drugs=true")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 3

    def test_search_by_name(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases?search=alzheimer")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["diseases"][0]["id"] == "alzheimers_disease"

    def test_search_by_synonym(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases?search=CF")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["diseases"][0]["id"] == "cystic_fibrosis"

    def test_pagination(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases?limit=2&offset=0")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 3
            assert len(data["diseases"]) == 2

    def test_get_disease_by_id(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases/glioma")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "glioma"
            assert data["canonical_name"] == "Glioma"

    def test_get_disease_not_found(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases/nonexistent")
            assert response.status_code == 404

    def test_get_diseases_by_region(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases/region/brain_cns")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2

    def test_get_orphan_diseases(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases/orphan")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["diseases"][0]["orphan_flag"] == True

    def test_search_endpoint(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = client.get("/api/v1/diseases/search/brain")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1

    def test_stats_endpoint(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            with patch(
                "src.backend.routers.diseases.load_body_ontology", return_value={}
            ):
                response = client.get("/api/v1/diseases/stats")
                assert response.status_code == 200
                data = response.json()
                assert data["total_diseases"] == 3
                assert data["orphan_diseases"] == 1
                assert data["total_targets"] == 27
                assert data["total_approved_drugs"] == 22


class TestDiseaseModel:
    def test_prevalence_tier_enum(self):
        assert PrevalenceTier.ULTRA_RARE.value == "ultra_rare"
        assert PrevalenceTier.RARE.value == "rare"
        assert PrevalenceTier.COMMON.value == "common"

    def test_evidence_level_enum(self):
        assert EvidenceLevel.APPROVED.value == "approved"
        assert EvidenceLevel.PHASE_III.value == "phase_iii"

    def test_disease_model_validation(self):
        disease = Disease(
            id="test_disease",
            canonical_name="Test Disease",
            body_region="test_region",
        )
        assert disease.id == "test_disease"
        assert disease.orphan_flag == False
        assert disease.prevalence_tier == PrevalenceTier.UNKNOWN

    def test_disease_model_with_all_fields(self):
        disease = Disease(
            id="full_disease",
            canonical_name="Full Disease",
            synonyms=["alias1", "alias2"],
            body_region="brain_cns",
            anatomy_nodes=["brain"],
            orphan_flag=True,
            prevalence_tier=PrevalenceTier.RARE,
            prevalence_count=50000,
            evidence_level=EvidenceLevel.APPROVED,
            mechanism_summary="This is a test mechanism.",
            mechanism_citation="PMID:123456",
            target_count=5,
            approved_drug_count=2,
            clinical_drug_count=3,
            mondo_id="MONDO:0000001",
            doid_id="DOID:0000001",
            icd10_code="C71.9",
        )
        assert disease.id == "full_disease"
        assert disease.orphan_flag == True
        assert disease.prevalence_count == 50000


class TestFilterParams:
    def test_filter_params_defaults(self):
        from src.backend.models.disease import DiseaseFilterParams

        params = DiseaseFilterParams()
        assert params.limit == 100
        assert params.offset == 0
        assert params.orphan_only == False

    def test_filter_params_validation(self):
        from src.backend.models.disease import DiseaseFilterParams
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DiseaseFilterParams(limit=0)
        with pytest.raises(ValidationError):
            DiseaseFilterParams(limit=1001)
