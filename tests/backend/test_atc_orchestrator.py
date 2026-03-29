import json
from pathlib import Path

from src.backend.etl.atc_orchestrator import (
    ATCEnrichmentPipeline,
    ATCResolution,
    is_placeholder_atc_code,
    is_specific_atc_code,
)
from src.backend.validation.validators import validate_atc_code


class StubPipeline(ATCEnrichmentPipeline):
    def __init__(self, **responses):
        enable_network = responses.pop("enable_network", False)
        enable_kegg_brite = responses.pop("enable_kegg_brite", False)
        enable_fallback = responses.pop("enable_fallback", True)
        enable_who = responses.pop("enable_who", True)
        super().__init__(
            drugs_file=Path("unused.json"),
            reports_dir=Path("unused-reports"),
            enable_network=enable_network,
            enable_kegg_brite=enable_kegg_brite,
            enable_fallback=enable_fallback,
            enable_who=enable_who,
        )
        self.responses = responses

    def _recover_external_ids_from_kegg_dblinks(self, drug):
        return self.responses.get("dblinks", {})

    def _resolve_from_kegg_direct(self, drug):
        return self.responses.get("kegg")

    def _resolve_from_pubchem(self, drug):
        return self.responses.get("pubchem")

    def _resolve_from_chembl(self, drug):
        return self.responses.get("chembl")

    def _resolve_from_who_lookup(self, drug):
        if not self.enable_network or not self.enable_who:
            return None
        return self.responses.get("who")

    def _resolve_from_kegg_brite(self, drug):
        return self.responses.get("brite")


def test_validate_atc_code_accepts_real_codes_and_rejects_placeholders():
    assert validate_atc_code("C10AA05") == (True, "")
    assert validate_atc_code("C10AA") == (True, "")
    assert validate_atc_code("N07XX07") == (True, "")

    is_valid, error = validate_atc_code("C99XX99")
    assert not is_valid
    assert "Placeholder" in error


def test_placeholder_and_specific_atc_helpers():
    assert is_specific_atc_code("C10AA05")
    assert is_specific_atc_code("N07XX07")
    assert not is_specific_atc_code("C99XX99")
    assert not is_placeholder_atc_code("N07XX07")
    assert is_placeholder_atc_code("V99XX99")
    assert is_placeholder_atc_code("C99XX99")


def test_pipeline_preserves_existing_valid_atc():
    pipeline = StubPipeline()
    drug = {
        "id": "atorvastatin",
        "name": "Atorvastatin",
        "atc_code": "C10AA05",
        "atc_category": "C",
    }

    updated, outcome = pipeline.enrich_drug(drug)

    assert updated["atc_source"] == "existing"
    assert updated["atc_confidence"] == 1.0
    assert updated["atc_resolution_method"] == "preserved_existing"
    assert outcome.status == "preserved"
    assert outcome.atc_code == "C10AA05"


def test_pipeline_uses_kegg_resolution_and_recovers_external_ids():
    pipeline = StubPipeline(
        dblinks={"pubchem_cid": "12345", "drugbank_id": "DB00001"},
        kegg=ATCResolution(
            atc_code="C01AA01",
            atc_category="C",
            source="kegg",
            confidence=1.0,
            method="kegg_direct",
        ),
    )
    drug = {
        "id": "example-drug",
        "name": "Example Drug",
        "atc_code": "V99XX99",
        "atc_category": "V",
        "kegg_id": "D00001",
    }

    updated, outcome = pipeline.enrich_drug(drug)

    assert updated["atc_code"] == "C01AA01"
    assert updated["atc_category"] == "C"
    assert updated["atc_source"] == "kegg"
    assert updated["atc_resolution_method"] == "kegg_direct"
    assert updated["pubchem_cid"] == 12345
    assert updated["drugbank_id"] == "DB00001"
    assert outcome.status == "resolved"
    assert outcome.external_ids_recovered == {
        "pubchem_cid": 12345,
        "drugbank_id": "DB00001",
    }


def test_pipeline_falls_back_to_placeholder_metadata_when_no_specific_match():
    pipeline = StubPipeline()
    drug = {
        "id": "mystery-drug",
        "name": "Mystery Drug",
        "atc_code": "V99XX99",
        "atc_category": "V",
        "indication": "Treatment of hypertension",
        "body_region": "heart_vascular",
    }

    updated, outcome = pipeline.enrich_drug(drug)

    assert updated["atc_code"] == "C99XX99"
    assert updated["atc_category"] == "C"
    assert updated["atc_source"] == "fallback"
    assert updated["atc_resolution_method"] == "fallback_indication"
    assert updated["atc_confidence"] == 0.35
    assert outcome.status == "placeholder"


def test_pipeline_can_disable_who_lookup():
    pipeline = StubPipeline(
        enable_network=True,
        enable_fallback=False,
        enable_who=False,
        who=ATCResolution(
            atc_code="C01AA01",
            atc_category="C",
            source="who",
            confidence=1.0,
            method="who_name_lookup",
        ),
    )
    drug = {
        "id": "mystery-drug",
        "name": "Mystery Drug",
        "atc_code": "V99XX99",
        "atc_category": "V",
    }

    updated, outcome = pipeline.enrich_drug(drug)

    assert updated["atc_code"] == "V99XX99"
    assert updated["atc_source"] == "unresolved"
    assert outcome.status == "placeholder"


def test_pipeline_run_writes_summary_and_unresolved_reports(tmp_path):
    drugs_path = tmp_path / "drugs.json"
    reports_dir = tmp_path / "reports"
    drugs_path.write_text(
        """
{
  "drugs": [
    {
      "id": "resolved-drug",
      "name": "Resolved Drug",
      "atc_code": "V99XX99",
      "atc_category": "V"
    },
    {
      "id": "valid-drug",
      "name": "Valid Drug",
      "atc_code": "N06AB10",
      "atc_category": "N"
    }
  ]
}
""".strip()
    )

    class ReportPipeline(StubPipeline):
        def __init__(self):
            super().__init__(
                kegg=ATCResolution(
                    atc_code="A01AA01",
                    atc_category="A",
                    source="kegg",
                    confidence=1.0,
                    method="kegg_direct",
                )
            )
            self.drugs_file = drugs_path
            self.reports_dir = reports_dir

    pipeline = ReportPipeline()
    report = pipeline.run()

    assert report["resolved_specific_atc_count"] == 1
    assert (reports_dir / "atc_enrichment_summary.json").exists()
    assert (reports_dir / "atc_unresolved_drugs.json").exists()


def test_pipeline_run_can_target_placeholder_entries_only(tmp_path):
    drugs_path = tmp_path / "drugs.json"
    reports_dir = tmp_path / "reports"
    drugs_path.write_text(
        """
{
  "drugs": [
    {
      "id": "valid-drug",
      "name": "Valid Drug",
      "atc_code": "N06AB10",
      "atc_category": "N"
    },
    {
      "id": "placeholder-one",
      "name": "Placeholder One",
      "atc_code": "V99XX99",
      "atc_category": "V"
    },
    {
      "id": "placeholder-two",
      "name": "Placeholder Two",
      "atc_code": "V99XX99",
      "atc_category": "V"
    }
  ]
}
""".strip()
    )

    class PlaceholderOnlyPipeline(StubPipeline):
        def __init__(self):
            super().__init__(
                kegg=ATCResolution(
                    atc_code="A01AA01",
                    atc_category="A",
                    source="kegg",
                    confidence=1.0,
                    method="kegg_direct",
                )
            )
            self.drugs_file = drugs_path
            self.reports_dir = reports_dir

    pipeline = PlaceholderOnlyPipeline()
    report = pipeline.run(limit=1, placeholder_only=True)

    payload = json.loads(drugs_path.read_text())
    drugs = payload["drugs"]

    assert report["processed_count"] == 1
    assert report["processed_input_placeholder_count"] == 1
    assert report["total_input_placeholder_count"] == 2
    assert report["selection_mode"] == "placeholder_only"
    assert drugs[0]["atc_code"] == "N06AB10"
    assert drugs[1]["atc_code"] == "A01AA01"
    assert drugs[2]["atc_code"] == "V99XX99"
