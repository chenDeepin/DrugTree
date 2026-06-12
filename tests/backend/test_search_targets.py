import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.backend.routers.drugs import (
    get_disease_tree,
    get_drugs_by_category,
    list_drugs,
    search_drugs,
    search_drugs_query,
)


def run_async(coro):
    return asyncio.run(coro)


def test_metadata_search_matches_targets_company_class_and_synonyms():
    drugs = [
        {
            "id": "alvocidib",
            "name": "Alvocidib",
            "smiles": "CC",
            "inchikey": "AAAA",
            "atc_code": "L01XX99",
            "atc_category": "L",
            "phase": "II",
            "targets": ["CDK1", "CDK2", "CDK4"],
            "company": "Sanofi",
            "synonyms": ["Flavopiridol"],
            "class": "CDK inhibitor",
        }
    ]

    with patch("src.backend.routers.drugs.load_drugs", return_value=drugs):
        assert run_async(list_drugs(search="cdk")).drugs[0].id == "alvocidib"
        assert run_async(list_drugs(search="sanofi")).drugs[0].id == "alvocidib"
        assert run_async(list_drugs(search="flavopiridol")).drugs[0].id == "alvocidib"
        assert run_async(list_drugs(search="inhibitor")).drugs[0].id == "alvocidib"


def test_query_param_search_endpoint_supports_cdk_contract():
    drugs = [
        {
            "id": "alvocidib",
            "name": "Alvocidib",
            "smiles": "CC",
            "inchikey": "AAAA",
            "atc_code": "L01XX99",
            "atc_category": "L",
            "phase": "II",
            "targets": ["CDK1", "CDK2", "CDK4"],
            "company": "Sanofi",
            "synonyms": ["Flavopiridol"],
            "class": "CDK inhibitor",
        }
    ]

    with patch("src.backend.routers.drugs.load_drugs", return_value=drugs):
        response = run_async(search_drugs_query(q="CDK"))
        assert response.total == 1
        assert response.drugs[0].id == "alvocidib"


def test_search_endpoint_paginates_results():
    drugs = [
        {
            "id": "statin-a",
            "name": "Statin A",
            "smiles": "CC",
            "inchikey": "AAAA",
            "atc_code": "C10AA01",
            "atc_category": "C",
            "phase": "IV",
            "targets": [],
            "company": "A",
            "synonyms": [],
            "class": "Statin",
        },
        {
            "id": "statin-b",
            "name": "Statin B",
            "smiles": "CC",
            "inchikey": "BBBB",
            "atc_code": "C10AA02",
            "atc_category": "C",
            "phase": "IV",
            "targets": [],
            "company": "B",
            "synonyms": [],
            "class": "Statin",
        },
    ]

    with patch("src.backend.routers.drugs.load_drugs", return_value=drugs):
        response = run_async(search_drugs(q="statin", limit=1, offset=1))

    assert response.total == 2
    assert [drug.id for drug in response.drugs] == ["statin-b"]


def test_category_endpoint_paginates_results():
    drugs = [
        {
            "id": "cardio-a",
            "name": "Cardio A",
            "smiles": "CC",
            "inchikey": "AAAA",
            "atc_code": "C01AA01",
            "atc_category": "C",
            "phase": "IV",
            "targets": [],
            "company": "A",
            "synonyms": [],
            "class": "Cardiac glycoside",
        },
        {
            "id": "cardio-b",
            "name": "Cardio B",
            "smiles": "CC",
            "inchikey": "BBBB",
            "atc_code": "C01AA02",
            "atc_category": "C",
            "phase": "IV",
            "targets": [],
            "company": "B",
            "synonyms": [],
            "class": "Cardiac glycoside",
        },
    ]

    with patch("src.backend.routers.drugs.load_drugs", return_value=drugs):
        response = run_async(get_drugs_by_category("C", limit=1, offset=1))

    assert response.total == 2
    assert [drug.id for drug in response.drugs] == ["cardio-b"]


@pytest.mark.asyncio
async def test_list_drugs_rejects_limit_above_cap(api_client):
    response = await api_client.get("/api/v1/drugs?limit=1001")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_drugs_rejects_negative_offset(api_client):
    response = await api_client.get("/api/v1/drugs?offset=-1")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_target_drug_endpoint_paginates_results(api_client, monkeypatch):
    drugs = [
        {
            "id": "target-a",
            "name": "Target A",
            "smiles": "CC",
            "inchikey": "AAAA",
            "atc_code": "C01AA01",
            "atc_category": "C",
            "phase": "IV",
            "targets": ["CDK2"],
            "company": "A",
            "synonyms": [],
            "class": "Kinase inhibitor",
        },
        {
            "id": "target-b",
            "name": "Target B",
            "smiles": "CC",
            "inchikey": "BBBB",
            "atc_code": "C01AA02",
            "atc_category": "C",
            "phase": "IV",
            "targets": ["CDK2"],
            "company": "B",
            "synonyms": [],
            "class": "Kinase inhibitor",
        },
    ]
    monkeypatch.setattr("src.backend.routers.diseases.load_drugs", lambda: drugs)

    response = await api_client.get("/api/v1/targets/CDK2/drugs?limit=1&offset=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [drug["id"] for drug in payload["drugs"]] == ["target-b"]


def test_disease_tree_endpoint_uses_limit_and_offset_instead_of_silent_slice():
    ontology = {
        "disease_to_anatomy": {"hypertension": {"region": "heart_vascular", "nodes": []}},
        "visible_regions": [
            {
                "id": "heart_vascular",
                "display_name": "Heart / Vascular",
                "icon": "heart",
                "description": "Cardiovascular system",
                "internal_nodes": [],
            }
        ],
        "internal_ontology": {},
    }
    drugs = [
        {
            "id": f"drug-{index}",
            "name": f"Drug {index}",
            "indication": "hypertension",
            "targets": [],
        }
        for index in range(3)
    ]

    with patch("src.backend.routers.drugs.load_body_ontology", return_value=ontology), patch(
        "src.backend.routers.drugs.load_drugs_full",
        return_value=drugs,
    ):
        response = run_async(get_disease_tree("hypertension", limit=1, offset=1))

    assert len(response.drugs) == 1
    assert response.drugs[0]["id"] == "drug-1"
    assert response.total == 3
    assert response.limit == 1
    assert response.offset == 1


@pytest.mark.asyncio
async def test_family_and_lineage_list_limits_are_capped(api_client):
    family_response = await api_client.get("/api/v1/families", params={"limit": 1001})
    lineage_response = await api_client.get("/api/v1/lineages", params={"limit": 1001})

    assert family_response.status_code == 422
    assert lineage_response.status_code == 422


def test_canonical_dataset_contains_cdk_searchable_metadata():
    data_path = Path(__file__).resolve().parents[2] / "data" / "drugs.json"
    payload = json.loads(data_path.read_text())
    drugs = payload.get("drugs", payload) if isinstance(payload, dict) else payload

    matches = [
        drug["id"]
        for drug in drugs
        if "cdk" in (drug.get("class") or "").lower()
        or any("cdk" in str(target).lower() for target in (drug.get("targets") or []))
    ]

    assert "alvocidib" in matches
