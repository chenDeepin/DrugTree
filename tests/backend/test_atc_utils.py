import json

from src.backend.etl.atc_utils import (
    is_placeholder_atc_code,
    is_specific_atc_code,
    load_drug_payload,
    merge_external_ids,
    write_drug_payload,
)


def test_atc_code_helpers_classify_specific_and_placeholder_codes():
    assert is_specific_atc_code("C10AA05")
    assert not is_specific_atc_code("C99XX99")
    assert is_placeholder_atc_code("C99XX99")
    assert is_placeholder_atc_code(None)


def test_merge_external_ids_preserves_existing_values_and_normalizes_pubchem():
    drug = {"id": "d1", "pubchem_cid": None, "drugbank_id": "DB00001"}

    merged, applied = merge_external_ids(
        drug, {"pubchem_cid": "12345", "drugbank_id": "DB99999"}
    )

    assert merged["pubchem_cid"] == 12345
    assert merged["drugbank_id"] == "DB00001"
    assert applied == {"pubchem_cid": 12345}
    assert drug["pubchem_cid"] is None


def test_drug_payload_helpers_preserve_root_shape(tmp_path):
    payload_path = tmp_path / "drugs.json"
    payload_path.write_text(json.dumps({"drugs": [{"id": "d1"}], "meta": 1}))

    payload, drugs = load_drug_payload(payload_path)
    drugs.append({"id": "d2"})
    write_drug_payload(payload_path, payload, drugs)

    assert json.loads(payload_path.read_text()) == {
        "drugs": [{"id": "d1"}, {"id": "d2"}],
        "meta": 1,
    }
