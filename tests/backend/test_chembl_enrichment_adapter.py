from src.backend.etl.drug_etl import normalize_chembl_metadata


def test_normalize_chembl_metadata_maps_targets_synonyms_and_indications():
    metadata = normalize_chembl_metadata(
        molecule_payload={
            "pref_name": "Abemaciclib",
            "molecule_synonyms": [
                {"molecule_synonym": "Verzenio"},
                {"molecule_synonym": "LY2835219"},
            ],
        },
        mechanisms_payload=[
            {
                "mechanism_of_action": "Cyclin-dependent kinase inhibitor",
                "target_chembl_id": "CHEMBL331",
                "target_pref_name": "Cyclin-dependent kinase 4",
            },
            {
                "mechanism_of_action": "Cyclin-dependent kinase inhibitor",
                "target_chembl_id": "CHEMBL332",
                "target_pref_name": "Cyclin-dependent kinase 6",
            },
        ],
        indications_payload=[
            {"mesh_id": "D000067836", "mesh_heading": "Breast Neoplasms"},
        ],
    )

    assert metadata["synonyms"] == ["Verzenio", "LY2835219"]
    assert metadata["targets"] == [
        "Cyclin-dependent kinase 4",
        "Cyclin-dependent kinase 6",
    ]
    assert metadata["class_name"] == "Cyclin-dependent kinase inhibitor"
    assert metadata["disease_ids"] == ["D000067836"]


def test_normalize_chembl_metadata_does_not_overwrite_with_empty_values():
    metadata = normalize_chembl_metadata(
        molecule_payload={"pref_name": "Abemaciclib", "molecule_synonyms": []},
        mechanisms_payload=[],
        indications_payload=[],
    )

    assert metadata == {
        "targets": [],
        "synonyms": [],
        "class_name": None,
        "disease_ids": [],
    }
