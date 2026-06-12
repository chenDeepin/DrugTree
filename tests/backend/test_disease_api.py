"""
Disease Universe API Tests

Tests for disease endpoints, filtering, and statistics.
"""

import asyncio

import pytest
from fastapi import HTTPException
from unittest.mock import patch

from src.backend.models.disease import (
    Disease,
    DrugDiseaseEdge,
    EvidenceLevel,
    PrevalenceTier,
)
from src.backend.routers.diseases import (
    get_disease,
    get_disease_stats,
    get_diseases_by_region,
    get_drugs_for_disease,
    get_orphan_diseases,
    list_disease_drug_edges,
    list_diseases,
    search_diseases,
)


def run_async(coro):
    return asyncio.run(coro)


def call_list_diseases(**overrides):
    params = {
        "region": None,
        "orphan_only": False,
        "has_approved_drugs": None,
        "search": None,
        "prevalence_tier": None,
        "limit": 100,
        "offset": 0,
    }
    params.update(overrides)
    return run_async(list_diseases(**params))


def call_get_orphan_diseases(**overrides):
    params = {"limit": 100, "offset": 0}
    params.update(overrides)
    return run_async(get_orphan_diseases(**params))


def call_list_disease_drug_edges(**overrides):
    params = {"disease_id": None, "drug_id": None, "limit": 1000, "offset": 0}
    params.update(overrides)
    return run_async(list_disease_drug_edges(**params))


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
            response = call_list_diseases()
            assert response.total == 0
            assert response.diseases == []

    def test_list_diseases_with_data(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = call_list_diseases()
            assert response.total == 3
            assert len(response.diseases) == 3

    def test_filter_by_region(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = call_list_diseases(region="brain_cns")
            assert response.total == 2
            for disease in response.diseases:
                assert disease.body_region == "brain_cns"

    def test_filter_orphan_only(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = call_list_diseases(orphan_only=True)
            assert response.total == 1
            assert response.diseases[0].id == "cystic_fibrosis"

    def test_filter_has_approved_drugs(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = call_list_diseases(has_approved_drugs=True)
            assert response.total == 3

    def test_search_by_name(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = call_list_diseases(search="alzheimer")
            assert response.total == 1
            assert response.diseases[0].id == "alzheimers_disease"

    def test_search_by_synonym(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = call_list_diseases(search="CF")
            assert response.total == 1
            assert response.diseases[0].id == "cystic_fibrosis"

    def test_pagination(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = call_list_diseases(limit=2, offset=0)
            assert response.total == 3
            assert len(response.diseases) == 2

    def test_get_disease_by_id(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = run_async(get_disease("glioma"))
            assert response.id == "glioma"
            assert response.canonical_name == "Glioma"

    def test_get_disease_not_found(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            with pytest.raises(HTTPException) as exc_info:
                run_async(get_disease("nonexistent"))
            assert exc_info.value.status_code == 404

    def test_get_diseases_by_region(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = run_async(get_diseases_by_region("brain_cns"))
            assert response.total == 2

    def test_get_diseases_by_region_paginates(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = run_async(get_diseases_by_region("brain_cns", limit=1, offset=1))
            assert response.total == 2
            assert len(response.diseases) == 1

    def test_get_orphan_diseases(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = call_get_orphan_diseases()
            assert response.total == 1
            assert response.diseases[0].orphan_flag is True

    def test_search_endpoint(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = run_async(search_diseases("brain"))
            assert response.total == 1

    def test_search_endpoint_paginates(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            response = run_async(search_diseases("i", limit=1, offset=1))
            assert response.total == 3
            assert len(response.diseases) == 1

    def test_stats_endpoint(self, sample_diseases):
        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=sample_diseases
        ):
            with patch(
                "src.backend.routers.diseases.load_body_ontology", return_value={}
            ):
                response = run_async(get_disease_stats())
                assert response.total_diseases == 3
                assert response.orphan_diseases == 1
                assert response.total_targets == 27
                assert response.total_approved_drugs == 22

    def test_get_drugs_for_disease_uses_explicit_edges(self):
        diseases = [
            Disease(
                id="alzheimers_disease",
                canonical_name="Alzheimer's Disease",
                body_region="brain_cns",
                evidence_level=EvidenceLevel.APPROVED,
            )
        ]
        edges = [
            DrugDiseaseEdge(
                disease_id="alzheimers_disease",
                drug_id="donepezil-hydrochloride",
                indication_type="primary",
                evidence_source="seed",
                evidence_level="approved",
            ),
            DrugDiseaseEdge(
                disease_id="alzheimers_disease",
                drug_id="memantine",
                indication_type="primary",
                evidence_source="seed",
                evidence_level="approved",
            ),
        ]
        drugs = [
            {
                "id": "donepezil-hydrochloride",
                "name": "Donepezil hydrochloride",
                "atc_code": "N06DA02",
                "atc_category": "N",
                "body_region": "brain_cns",
                "secondary_body_regions": [],
                "targets": [],
                "synonyms": [],
                "clinical_trials": [],
            },
            {
                "id": "memantine",
                "name": "Memantine",
                "atc_code": "N06DX01",
                "atc_category": "N",
                "body_region": "brain_cns",
                "secondary_body_regions": [],
                "targets": [],
                "synonyms": [],
                "clinical_trials": [],
            },
            {
                "id": "unrelated",
                "name": "Unrelated drug",
                "atc_code": "C01AA01",
                "atc_category": "C",
                "body_region": "heart_vascular",
                "secondary_body_regions": [],
                "targets": [],
                "synonyms": [],
                "clinical_trials": [],
            },
        ]

        with patch(
            "src.backend.routers.diseases.load_diseases", return_value=diseases
        ), patch(
            "src.backend.routers.diseases.load_disease_drug_edges", return_value=edges
        ), patch("src.backend.routers.diseases.load_drugs", return_value=drugs):
            response = run_async(get_drugs_for_disease("alzheimers_disease"))

            assert response.total == 2
            assert {drug.id for drug in response.drugs} == {
                "donepezil-hydrochloride",
                "memantine",
            }

            paginated = run_async(
                get_drugs_for_disease("alzheimers_disease", limit=1, offset=1)
            )

            assert paginated.total == 2
            assert [drug.id for drug in paginated.drugs] == ["memantine"]

    def test_list_disease_drug_edges_uses_canonical_edge_loader(self):
        edges = [
            DrugDiseaseEdge(
                disease_id="alzheimers_disease",
                drug_id="donepezil-hydrochloride",
                indication_type="primary",
                evidence_source="seed",
                evidence_level="approved",
            ),
            DrugDiseaseEdge(
                disease_id="alzheimers_disease",
                drug_id="memantine",
                indication_type="primary",
                evidence_source="seed",
                evidence_level="approved",
            ),
            DrugDiseaseEdge(
                disease_id="glioma",
                drug_id="temozolomide",
                indication_type="primary",
                evidence_source="seed",
                evidence_level="approved",
            ),
        ]

        with patch(
            "src.backend.routers.diseases.load_disease_drug_edges", return_value=edges
        ):
            response = call_list_disease_drug_edges(disease_id="alzheimers_disease")

        assert response.total == 2
        assert all(edge.disease_id == "alzheimers_disease" for edge in response.edges)


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
