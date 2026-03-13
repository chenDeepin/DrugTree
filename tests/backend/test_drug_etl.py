import pandas as pd

from src.backend.etl.drug_etl import (
    ensure_unique_drug_ids,
    extract_drug_names,
    load_local_name_lookups,
    transform_drug,
)


def test_extract_drug_names_uses_local_kegg_lookup_when_trialbench_name_is_missing(tmp_path):
    drug_lookup = tmp_path / "kegg_drug_inchikeys.tsv"
    compound_lookup = tmp_path / "kegg_compound_inchikeys.tsv"

    drug_lookup.write_text(
        "inchikey\tcanonical_smiles\tsource\tkegg_id\tname\tmolecular_weight\toriginal_smiles\n"
        "AAAA\tCC\tkegg_drug\tD12345\tDemozine\t30.0\tCC\n",
        encoding="utf-8",
    )
    compound_lookup.write_text(
        "inchikey\tcanonical_smiles\tsource\tkegg_id\tname\tmolecular_weight\toriginal_smiles\n",
        encoding="utf-8",
    )

    lookups = load_local_name_lookups(drug_lookup, compound_lookup)
    row = pd.Series(
        {
            "trialbench_drug_names": "",
            "kegg_drug_id": "D12345",
            "kegg_compound_id": "",
            "inchikey": "AAAA",
        }
    )

    name, synonyms = extract_drug_names(row, local_name_lookups=lookups)

    assert name == "Demozine"
    assert synonyms == []


def test_transform_drug_adds_ontology_body_regions_from_tissues(tmp_path):
    drug_lookup = tmp_path / "kegg_drug_inchikeys.tsv"
    compound_lookup = tmp_path / "kegg_compound_inchikeys.tsv"

    drug_lookup.write_text(
        "inchikey\tcanonical_smiles\tsource\tkegg_id\tname\tmolecular_weight\toriginal_smiles\n"
        "BBBB\tCCO\tkegg_drug\tD99999\tCardiovex\t46.0\tCCO\n",
        encoding="utf-8",
    )
    compound_lookup.write_text(
        "inchikey\tcanonical_smiles\tsource\tkegg_id\tname\tmolecular_weight\toriginal_smiles\n",
        encoding="utf-8",
    )

    lookups = load_local_name_lookups(drug_lookup, compound_lookup)
    row = pd.Series(
        {
            "trialbench_drug_names": "",
            "kegg_drug_id": "D99999",
            "kegg_compound_id": "",
            "canonical_smiles": "CCO",
            "inchikey": "BBBB",
            "molecular_weight": 46.0,
            "trialbench_phases": "Phase III",
            "trialbench_outcomes": "approved",
            "tissues_union": "Heart,Blood,Kidney",
        }
    )

    drug = transform_drug(row, kegg_client=None, local_name_lookups=lookups)

    assert drug is not None
    assert drug["name"] == "Cardiovex"
    assert drug["body_region"] == "heart_vascular"
    assert "blood_immune" in drug["secondary_body_regions"]
    assert "kidney_urinary" in drug["secondary_body_regions"]


def test_extract_drug_names_prefers_local_kegg_name_when_trial_name_is_comparator(tmp_path):
    drug_lookup = tmp_path / "kegg_drug_inchikeys.tsv"
    compound_lookup = tmp_path / "kegg_compound_inchikeys.tsv"

    drug_lookup.write_text(
        "inchikey\tcanonical_smiles\tsource\tkegg_id\tname\tmolecular_weight\toriginal_smiles\n"
        "CCCC\tCCN\tkegg_drug\tD54321\tRealdrug\t45.0\tCCN\n",
        encoding="utf-8",
    )
    compound_lookup.write_text(
        "inchikey\tcanonical_smiles\tsource\tkegg_id\tname\tmolecular_weight\toriginal_smiles\n",
        encoding="utf-8",
    )

    lookups = load_local_name_lookups(drug_lookup, compound_lookup)
    row = pd.Series(
        {
            "trialbench_drug_names": "Comparator: something",
            "kegg_drug_id": "D54321",
            "kegg_compound_id": "",
            "inchikey": "CCCC",
        }
    )

    name, synonyms = extract_drug_names(row, local_name_lookups=lookups)

    assert name == "Realdrug"
    assert synonyms == []


def test_extract_drug_names_preserves_commas_inside_chemical_names():
    row = pd.Series(
        {
            "trialbench_drug_names": "1,4-Dimethyl-7-isopropylazulene",
            "kegg_drug_id": "",
            "kegg_compound_id": "",
            "inchikey": "",
        }
    )

    name, synonyms = extract_drug_names(row, local_name_lookups=None)

    assert name == "1,4-Dimethyl-7-isopropylazulene"
    assert synonyms == []


def test_extract_drug_names_keeps_compound_codes_when_placebo_is_prefixed():
    row = pd.Series(
        {
            "trialbench_drug_names": "Placebo/CP-690,550",
            "kegg_drug_id": "",
            "kegg_compound_id": "",
            "inchikey": "",
        }
    )

    name, synonyms = extract_drug_names(row, local_name_lookups=None)

    assert name == "CP-690,550"
    assert synonyms == []


def test_extract_drug_names_still_splits_multi_entry_lists_followed_by_dosage_numbers():
    row = pd.Series(
        {
            "trialbench_drug_names": "10 mg Rupatadine on demand,10 mg Rupatadine",
            "kegg_drug_id": "",
            "kegg_compound_id": "",
            "inchikey": "",
        }
    )

    name, synonyms = extract_drug_names(row, local_name_lookups=None)

    assert name == "10 mg Rupatadine on demand"
    assert synonyms == ["10 mg Rupatadine"]


def test_ensure_unique_drug_ids_resolves_same_slug_and_same_inchikey_prefix():
    drugs = [
        {"id": "dup", "inchikey": "ABCDEFGH1234", "kegg_id": None},
        {"id": "dup", "inchikey": "ABCDEFGH5678", "kegg_id": None},
        {"id": "dup", "inchikey": "ABCDEFGH9999", "kegg_id": None},
    ]

    ensure_unique_drug_ids(drugs)

    ids = [drug["id"] for drug in drugs]
    assert len(ids) == len(set(ids))
