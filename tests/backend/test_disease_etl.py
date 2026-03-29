import json
from pathlib import Path

from src.backend.etl.disease_etl import (
    build_outputs,
    fetch_live_chembl_indication_map,
    parse_mondo_obographs,
    parse_orphanet_alignments,
)


def test_parse_orphanet_alignments_extracts_core_fields():
    payload = {
        "JDBOR": [
            {
                "DisorderList": [
                    {
                        "Disorder": [
                            {
                                "OrphaCode": "58",
                                "Name": [{"lang": "en", "label": "Alexander disease"}],
                                "SynonymList": [
                                    {
                                        "Synonym": [
                                            {"lang": "en", "label": "AxD"},
                                            {
                                                "lang": "en",
                                                "label": "Alexander leukodystrophy",
                                            },
                                        ]
                                    }
                                ],
                                "ExternalReferenceList": [
                                    {
                                        "ExternalReference": [
                                            {"Source": "MONDO", "Reference": "0008752"},
                                            {"Source": "MeSH", "Reference": "D038261"},
                                            {"Source": "ICD-10", "Reference": "G93.8"},
                                        ]
                                    }
                                ],
                                "SummaryInformationList": [
                                    {
                                        "SummaryInformation": [
                                            {
                                                "TextSectionList": [
                                                    {
                                                        "TextSection": [
                                                            {
                                                                "TextSectionType": [
                                                                    {
                                                                        "Name": [
                                                                            {
                                                                                "lang": "en",
                                                                                "label": "Definition",
                                                                            }
                                                                        ]
                                                                    }
                                                                ],
                                                                "Contents": "Rare astrocyte disorder.",
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }

    records = parse_orphanet_alignments(payload)

    assert len(records) == 1
    record = records[0]
    assert record["canonical_name"] == "Alexander disease"
    assert record["orphanet_id"] == "ORPHA:58"
    assert record["mondo_id"] == "MONDO:0008752"
    assert record["mesh_id"] == "MESH:D038261"
    assert record["icd10_code"] == "G93.8"
    assert "AxD" in record["synonyms"]
    assert record["orphan_flag"] is True


def test_parse_mondo_obographs_extracts_synonyms_and_xrefs():
    payload = {
        "graphs": [
            {
                "nodes": [
                    {
                        "id": "http://purl.obolibrary.org/obo/MONDO_0008752",
                        "lbl": "Alexander disease",
                        "meta": {
                            "definition": {
                                "val": "A neurodegenerative leukodystrophy.",
                            },
                            "synonyms": [
                                {"val": "AxD"},
                                {"val": "Alexander leukodystrophy"},
                            ],
                            "xrefs": [
                                {"val": "Orphanet:58"},
                                {"val": "DOID:0060868"},
                                {"val": "MESH:D038261"},
                            ],
                        },
                    }
                ]
            }
        ]
    }

    records = parse_mondo_obographs(payload)

    assert len(records) == 1
    record = records[0]
    assert record["mondo_id"] == "MONDO:0008752"
    assert record["canonical_name"] == "Alexander disease"
    assert record["orphanet_id"] == "ORPHA:58"
    assert record["doid_id"] == "DOID:0060868"
    assert record["mesh_id"] == "MESH:D038261"
    assert "AxD" in record["synonyms"]


def test_build_outputs_merges_external_sources_and_adds_chembl_edges():
    seed_diseases = [
        {
            "id": "alexander_disease",
            "canonical_name": "Alexander disease",
            "synonyms": ["AxD"],
            "body_region": "brain_cns",
            "anatomy_nodes": ["brain"],
            "categories": ["neurological"],
            "orphan_flag": True,
            "prevalence_tier": "unknown",
            "prevalence_count": None,
            "evidence_level": "seed",
            "target_count": 0,
            "approved_drug_count": 0,
            "clinical_drug_count": 0,
            "drugs": [],
        }
    ]
    drugs = [
        {
            "id": "riluzole",
            "name": "Riluzole",
            "chembl_id": "CHEMBL744",
            "phase": "IV",
            "synonyms": [],
        }
    ]
    orphanet_records = [
        {
            "canonical_name": "Alexander disease",
            "synonyms": ["Alexander leukodystrophy"],
            "orphanet_id": "ORPHA:58",
            "mondo_id": "MONDO:0008752",
            "mesh_id": "MESH:D038261",
            "icd10_code": "G93.8",
            "definition": "Rare astrocyte disorder.",
            "orphan_flag": True,
            "source": "orphanet",
        }
    ]
    mondo_records = [
        {
            "canonical_name": "Alexander disease",
            "synonyms": ["AxD"],
            "orphanet_id": "ORPHA:58",
            "mondo_id": "MONDO:0008752",
            "doid_id": "DOID:0060868",
            "mesh_id": "MESH:D038261",
            "definition": "A neurodegenerative leukodystrophy.",
            "source": "mondo",
        }
    ]
    chembl_indication_map = {
        "CHEMBL744": [
            {
                "disease_id": "MESH:D038261",
                "disease_name": "Alexander disease",
                "indication_type": "primary",
                "phase": "4.0",
            }
        ]
    }

    diseases_payload, edges_payload = build_outputs(
        seed_diseases=seed_diseases,
        drugs=drugs,
        orphanet_records=orphanet_records,
        mondo_records=mondo_records,
        chembl_indication_map=chembl_indication_map,
    )

    disease = diseases_payload["diseases"][0]
    assert disease["orphan_flag"] is True
    assert disease["orphanet_id"] == "ORPHA:58"
    assert disease["mondo_id"] == "MONDO:0008752"
    assert disease["doid_id"] == "DOID:0060868"
    assert disease["mesh_id"] == "MESH:D038261"
    assert disease["approved_drug_count"] == 1
    assert "orphan" in disease["categories"]

    edge = edges_payload["edges"][0]
    assert edge["disease_id"] == "alexander_disease"
    assert edge["drug_id"] == "riluzole"
    assert edge["evidence_source"] == "chembl"
    assert edge["evidence_level"] == "approved"


def test_build_outputs_can_create_new_external_disease_records():
    drugs = [
        {
            "id": "example-drug",
            "name": "Example Drug",
            "chembl_id": "CHEMBL1",
            "phase": "III",
            "synonyms": [],
        }
    ]
    orphanet_records = [
        {
            "canonical_name": "Example syndrome",
            "synonyms": ["Example rare syndrome"],
            "orphanet_id": "ORPHA:999999",
            "mondo_id": "MONDO:0999999",
            "mesh_id": None,
            "icd10_code": None,
            "definition": None,
            "orphan_flag": True,
            "source": "orphanet",
        }
    ]
    chembl_indication_map = {
        "CHEMBL1": [
            {
                "disease_id": "MONDO:0999999",
                "disease_name": "Example syndrome",
                "indication_type": "primary",
                "phase": 3,
            }
        ]
    }

    diseases_payload, edges_payload = build_outputs(
        seed_diseases=[],
        drugs=drugs,
        orphanet_records=orphanet_records,
        mondo_records=[],
        chembl_indication_map=chembl_indication_map,
    )

    assert len(diseases_payload["diseases"]) == 1
    disease = diseases_payload["diseases"][0]
    assert disease["canonical_name"] == "Example syndrome"
    assert disease["orphan_flag"] is True
    assert disease["body_region"] == "systemic_multiorgan"
    assert edges_payload["edges"][0]["disease_id"] == disease["id"]


def test_build_outputs_preserves_non_orphan_seed_diseases_when_external_match_is_orphan():
    seed_diseases = [
        {
            "id": "type_2_diabetes",
            "canonical_name": "Type 2 Diabetes",
            "synonyms": ["Type 2 diabetes mellitus", "T2D"],
            "body_region": "endocrine_metabolic",
            "anatomy_nodes": ["pancreas"],
            "categories": ["metabolic"],
            "orphan_flag": False,
            "prevalence_tier": "common",
            "prevalence_count": 462000000,
            "evidence_level": "approved",
            "target_count": 0,
            "approved_drug_count": 0,
            "clinical_drug_count": 0,
            "drugs": [],
        }
    ]
    orphanet_records = [
        {
            "canonical_name": "Type 2 diabetes mellitus",
            "synonyms": ["Type 2 Diabetes", "T2D"],
            "orphanet_id": "ORPHA:999",
            "mondo_id": "MONDO:0005148",
            "mesh_id": "MESH:D003924",
            "icd10_code": "E11.9",
            "definition": "Common metabolic disease.",
            "orphan_flag": True,
            "source": "orphanet",
        }
    ]

    diseases_payload, _ = build_outputs(
        seed_diseases=seed_diseases,
        drugs=[],
        orphanet_records=orphanet_records,
        mondo_records=[],
        chembl_indication_map={},
    )

    disease = diseases_payload["diseases"][0]
    assert disease["orphan_flag"] is False
    assert "orphan" not in disease["categories"]
    assert disease["prevalence_tier"] == "common"
    assert disease["prevalence_count"] == 462000000
    assert disease["orphanet_id"] == "ORPHA:999"


def test_fetch_live_chembl_indication_map_uses_drug_chembl_ids(monkeypatch):
    class FakeChEMBLClient:
        def __init__(self, rate_limit_per_sec=1.0):
            self.rate_limit_per_sec = rate_limit_per_sec

        async def get_drug_indications(self, chembl_id):
            if chembl_id == "CHEMBL1":
                return [
                    {
                        "disease_id": "MESH:D001",
                        "disease_name": "Test Disease",
                        "indication_type": "primary",
                        "phase": 4,
                    }
                ]
            return []

        async def close(self):
            return None

    monkeypatch.setattr(
        "src.backend.etl.disease_etl.ChEMBLClient",
        FakeChEMBLClient,
    )

    result = __import__("asyncio").run(
        fetch_live_chembl_indication_map(
            drugs=[
                {"id": "drug-a", "chembl_id": "CHEMBL1"},
                {"id": "drug-b", "chembl_id": "CHEMBL2"},
            ],
            limit=1,
            rate_limit_per_sec=5.0,
        )
    )

    assert list(result.keys()) == ["CHEMBL1"]
    assert result["CHEMBL1"][0]["disease_name"] == "Test Disease"
