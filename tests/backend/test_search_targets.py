import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from src.backend.routers.drugs import list_drugs, search_drugs_query


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
