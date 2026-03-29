from src.backend.etl.drug_etl import normalize_fda_metadata


def test_normalize_fda_metadata_extracts_year_and_company():
    metadata = normalize_fda_metadata(
        [
            {
                "application_number": "NDA021436",
                "product_name": "VERZENIO",
                "approval_date": "20170928",
                "sponsor": "Eli Lilly and Company",
                "status": "Approved",
            }
        ]
    )

    assert metadata == {"year_approved": 2017, "company": "Eli Lilly and Company"}


def test_normalize_fda_metadata_handles_missing_hits_gracefully():
    metadata = normalize_fda_metadata([])

    assert metadata == {"year_approved": None, "company": None}
