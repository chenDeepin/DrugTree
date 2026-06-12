from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ETL_PATH = REPO_ROOT / "src/backend/run_etl.sh"
SOURCE_REGISTRY_PATH = REPO_ROOT / "data/source_registry.yaml"
WORKFLOW_DOC_PATH = REPO_ROOT / "docs/operations/data-update-workflow.md"


def parse_phase2_extract_scripts(script_text: str) -> list[str]:
    match = re.search(r"EXTRACT_SCRIPTS=\((.*?)\)", script_text, re.DOTALL)
    assert match is not None, "run_etl.sh must declare EXTRACT_SCRIPTS"
    return re.findall(r'"([^"]+)"', match.group(1))


def parse_registry_source_names(registry_text: str) -> set[str]:
    return set(parse_registry_sources(registry_text))


def parse_registry_sources(registry_text: str) -> dict[str, str]:
    data = yaml.safe_load(registry_text)
    assert isinstance(data, dict), "source registry must parse as a mapping"

    raw_sources = data.get("sources")
    assert isinstance(raw_sources, list), "source registry must contain a sources list"

    sources: dict[str, str] = {}
    for source in raw_sources:
        assert isinstance(source, dict), "source registry entries must be mappings"
        name = source.get("name")
        assert isinstance(name, str) and name, (
            "source registry entries must contain non-empty names"
        )
        status = source.get("status")
        assert isinstance(status, str) and status, (
            "source registry entries must contain non-empty statuses"
        )
        sources[name] = status

    return sources


def validate_phase2_source_contract(
    extract_scripts: list[str], registry_names: set[str]
) -> None:
    duplicates = sorted(
        {script for script in extract_scripts if extract_scripts.count(script) > 1}
    )
    assert not duplicates, f"duplicate Phase 2 scripts found: {duplicates}"

    missing_registry_entries = sorted(
        {
            Path(script).stem.removeprefix("fetch_")
            for script in extract_scripts
            if Path(script).stem.removeprefix("fetch_") not in registry_names
        }
    )
    assert not missing_registry_entries, (
        f"Phase 2 scripts missing registry entries: {missing_registry_entries}"
    )


def validate_source_status_matrix(sources: dict[str, str]) -> None:
    valid_statuses = {"active", "extraction_only", "planned"}
    invalid = {
        name: status for name, status in sources.items() if status not in valid_statuses
    }
    assert not invalid, f"invalid source statuses: {invalid}"

    expected_active = {
        "chembl",
        "kegg",
        "pubchem",
        "fda",
        "drugcentral",
        "rxnorm",
        "opentargets",
        "dgidb",
        "ttd",
        "clinicaltrials",
        "mondo",
        "ctd",
    }
    for source_name in expected_active:
        assert sources.get(source_name) == "active", (
            f"{source_name} must be marked active"
        )

    assert sources.get("drugmechdb") == "extraction_only", (
        "drugmechdb must remain extraction_only"
    )
    assert sources.get("uniprot") == "planned", "uniprot must remain planned"
    assert sources.get("who_atc") == "planned", "who_atc must remain planned"


def test_phase2_extract_scripts_have_matching_registry_entries() -> None:
    extract_scripts = parse_phase2_extract_scripts(RUN_ETL_PATH.read_text())
    registry_names = parse_registry_source_names(SOURCE_REGISTRY_PATH.read_text())

    validate_phase2_source_contract(extract_scripts, registry_names)


def test_phase2_declares_ctd_once() -> None:
    extract_scripts = parse_phase2_extract_scripts(RUN_ETL_PATH.read_text())

    assert extract_scripts.count("fetch_ctd.py") == 1


def test_phase2_contract_rejects_missing_registry_entry() -> None:
    extract_scripts = parse_phase2_extract_scripts(RUN_ETL_PATH.read_text())
    registry_names = parse_registry_source_names(SOURCE_REGISTRY_PATH.read_text())
    missing_source = Path(extract_scripts[0]).stem.removeprefix("fetch_")

    registry_names.remove(missing_source)

    with pytest.raises(
        AssertionError,
        match=r"Phase 2 scripts missing registry entries",
    ):
        validate_phase2_source_contract(extract_scripts, registry_names)


def test_phase2_contract_rejects_duplicate_script_entry() -> None:
    extract_scripts = parse_phase2_extract_scripts(RUN_ETL_PATH.read_text())
    registry_names = parse_registry_source_names(SOURCE_REGISTRY_PATH.read_text())
    duplicated_scripts = [*extract_scripts, extract_scripts[0]]

    with pytest.raises(AssertionError, match=r"duplicate Phase 2 scripts found"):
        validate_phase2_source_contract(duplicated_scripts, registry_names)


def test_parse_registry_sources_includes_non_empty_statuses() -> None:
    sources = parse_registry_sources(SOURCE_REGISTRY_PATH.read_text())

    assert sources["ctd"]
    assert all(status for status in sources.values())


def test_source_registry_status_matrix_matches_wave3_expectations() -> None:
    sources = parse_registry_sources(SOURCE_REGISTRY_PATH.read_text())

    validate_source_status_matrix(sources)


def test_source_registry_rejects_invalid_extraction_only_assignment() -> None:
    sources = parse_registry_sources(SOURCE_REGISTRY_PATH.read_text())
    sources["drugmechdb"] = "active"

    with pytest.raises(AssertionError, match=r"drugmechdb must remain extraction_only"):
        validate_source_status_matrix(sources)


def test_workflow_docs_name_run_etl_as_canonical_execution_path() -> None:
    workflow_doc = WORKFLOW_DOC_PATH.read_text()

    assert "run_etl.sh" in workflow_doc
    assert "canonical execution path" in workflow_doc.lower()
    assert "optional/planned service infrastructure" in workflow_doc.lower()
    assert "/api/v1/admin/trigger-sync" in workflow_doc
    assert "/api/v1/admin/health/data-quality" in workflow_doc
    assert "/api/admin/trigger-sync" not in workflow_doc
    assert "/api/health/data-quality" not in workflow_doc
    assert "await start_scheduler()" not in workflow_doc
    assert "trigger_manual_sync(triggered_by=" not in workflow_doc
    assert (
        "python -m src.backend.services.update_scheduler --trigger" not in workflow_doc
    )
    assert "get_job_status" not in workflow_doc


def test_run_etl_wraps_required_and_optional_steps_with_timeouts() -> None:
    script_text = RUN_ETL_PATH.read_text()

    assert "ETL_CORE_TIMEOUT_SECONDS" in script_text
    assert "ETL_STEP_TIMEOUT_SECONDS" in script_text
    assert "run_required_step \"drug ETL\"" in script_text
    assert "run_required_step \"disease graph artifacts\"" in script_text
    assert "run_optional_step \"$script\"" in script_text
    assert "timeout \"${ETL_CORE_TIMEOUT_SECONDS}s\"" in script_text
    assert "timeout \"${ETL_STEP_TIMEOUT_SECONDS}s\"" in script_text
