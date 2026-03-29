from src.backend.etl.drug_etl import parse_kegg_metadata


KEGG_RAW_TEXT = """ENTRY       D02880                      Drug
NAME        Alvocidib hydrochloride (USAN)
PRODUCT     ALVOCIDIB (Aventis)
            ALVOCIDIB (Sanofi)
CLASS       Antineoplastic
             DG03138  CDK inhibitor
REMARK      Chemical structure group: DG02041
            ATC code: L01XX99
EFFICACY    Antineoplastic, Cyclin-dependent kinase (CDK) inhibitor
TARGET      CDK1 [HSA:983] [KO:K02087]
            CDK2 [HSA:1017] [KO:K02206]
            CDK4 [HSA:1019] [KO:K02089]
            CDK6 [HSA:1021] [KO:K02091]
  DISEASE   Mantle cell lymphoma [DS:H12345]
"""


def test_parse_kegg_metadata_extracts_targets_synonyms_disease_and_atc():
    metadata = parse_kegg_metadata(KEGG_RAW_TEXT)

    assert metadata["primary_name"] == "Alvocidib hydrochloride"
    assert metadata["synonyms"] == ["Alvocidib hydrochloride (USAN)"]
    assert metadata["targets"] == ["CDK1", "CDK2", "CDK4", "CDK6"]
    assert metadata["disease_ids"] == ["H12345"]
    assert metadata["atc_codes"] == ["L01XX99"]
    assert metadata["class_name"] == "CDK inhibitor"
    assert metadata["companies"] == ["Aventis", "Sanofi"]


def test_parse_kegg_metadata_leaves_unsupported_year_approval_empty():
    metadata = parse_kegg_metadata(KEGG_RAW_TEXT)

    assert metadata["year_approved"] is None
