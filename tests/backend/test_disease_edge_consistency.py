import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_json(relative_path):
    return json.loads((ROOT / relative_path).read_text())


def test_disease_counts_match_explicit_edge_counts():
    diseases_payload = load_json("data/diseases.json")
    edges_payload = load_json("data/disease_drug_edges.json")
    diseases = diseases_payload.get("diseases", diseases_payload)
    edges = edges_payload.get("edges", edges_payload)

    edge_counts = {}
    for edge in edges:
        edge_counts[edge["disease_id"]] = edge_counts.get(edge["disease_id"], 0) + 1

    mismatches = [
        (
            disease["id"],
            disease.get("approved_drug_count", 0),
            edge_counts.get(disease["id"], 0),
        )
        for disease in diseases
        if disease.get("approved_drug_count", 0) != edge_counts.get(disease["id"], 0)
    ]

    assert mismatches == []


def test_selectable_diseases_have_edges():
    diseases_payload = load_json("data/diseases.json")
    edges_payload = load_json("data/disease_drug_edges.json")
    diseases = diseases_payload.get("diseases", diseases_payload)
    edges = edges_payload.get("edges", edges_payload)

    edge_disease_ids = {edge["disease_id"] for edge in edges}
    orphaned = [
        disease["id"] for disease in diseases if disease["id"] not in edge_disease_ids
    ]

    assert orphaned == []


def test_disease_edges_reference_known_drug_ids():
    drugs_payload = load_json("data/drugs.json")
    edges_payload = load_json("data/disease_drug_edges.json")
    drugs = drugs_payload.get("drugs", drugs_payload)
    edges = edges_payload.get("edges", edges_payload)

    known_drug_ids = {drug["id"] for drug in drugs}
    missing = [
        edge["drug_id"] for edge in edges if edge["drug_id"] not in known_drug_ids
    ]

    assert missing == []
