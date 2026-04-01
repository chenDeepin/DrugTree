import json

import httpx
import pytest

from src.backend.etl import fetch_dgidb as mod


def test_parse_interaction_payload_supports_graphql_style_records():
    payload = {
        "drugs": {
            "matchedTerms": [
                {
                    "searchTerm": "Gefitinib",
                    "matchedDrug": {
                        "name": "Gefitinib",
                        "interactions": [
                            {
                                "interactionId": "int-1",
                                "gene": {
                                    "name": "Epidermal growth factor receptor",
                                    "symbol": "EGFR",
                                    "conceptId": "123",
                                },
                                "interactionTypes": [{"type": "inhibitor"}],
                                "interactionAttributes": [{"name": "FDA approved"}],
                                "sources": [{"sourceDbName": "DrugBank"}],
                            }
                        ],
                    },
                }
            ]
        }
    }

    records = mod.parse_interaction_payload(
        payload, {"drug_id": "gefitinib", "drug_name": "Gefitinib"}
    )

    assert records == [
        {
            "drug_name": "Gefitinib",
            "drug_id_local": "gefitinib",
            "gene_name": "Epidermal growth factor receptor",
            "gene_symbol": "EGFR",
            "interaction_types": ["inhibitor"],
            "interaction_attributes": ["FDA approved"],
            "sources": ["DrugBank"],
            "dgidb_gene_id": "123",
            "source_name": "dgidb",
            "source_record_id": "int-1",
            "retrieved_at": records[0]["retrieved_at"],
        }
    ]


@pytest.mark.asyncio
async def test_fetch_interaction_payload_falls_back_to_rest(monkeypatch):
    rest_payload = {"matchedTerms": [{"interactions": []}]}

    async def fake_graphql_query(client, query, variables):
        return None

    async def fake_get_json(client, url, params=None):
        assert url == mod.INTERACTIONS_URL
        assert params == {"drugs": "Gefitinib"}
        return rest_payload

    monkeypatch.setattr(mod, "safe_graphql_query", fake_graphql_query)
    monkeypatch.setattr(mod, "safe_get_json", fake_get_json)

    async with httpx.AsyncClient() as client:
        result = await mod.fetch_interaction_payload(
            client, {"drug_id": "gefitinib", "drug_name": "Gefitinib"}
        )

    assert result["method"] == "rest"
    assert result["payload"] == rest_payload
    assert result["errors"]


@pytest.mark.asyncio
async def test_run_preserves_checkpoint_outputs_on_partial_failures(
    monkeypatch, tmp_path
):
    raw_dir = tmp_path / "raw" / "dgidb"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_dgidb_checkpoint.json"

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)
    monkeypatch.setattr(
        mod,
        "load_local_drugs",
        lambda limit=None: [
            {"drug_id": "gefitinib", "drug_name": "Gefitinib"},
            {"drug_id": "erlotinib", "drug_name": "Erlotinib"},
        ],
    )

    async def fake_fetch_interaction_payload(client, drug):
        if drug["drug_name"] == "Gefitinib":
            return {
                "method": "graphql",
                "payload": {
                    "drugs": {
                        "matchedTerms": [
                            {
                                "matchedDrug": {
                                    "interactions": [
                                        {
                                            "interactionId": "int-1",
                                            "gene": {
                                                "name": "Epidermal growth factor receptor",
                                                "symbol": "EGFR",
                                                "conceptId": "123",
                                            },
                                            "interactionTypes": [{"type": "inhibitor"}],
                                            "interactionAttributes": [
                                                {"name": "FDA approved"}
                                            ],
                                            "sources": [{"sourceDbName": "DrugBank"}],
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                },
                "errors": [],
            }
        return {
            "method": None,
            "payload": None,
            "errors": ["graphql_failed", "rest_failed"],
        }

    monkeypatch.setattr(
        mod, "fetch_interaction_payload", fake_fetch_interaction_payload
    )

    summary = await mod.run(limit=None, concurrency=2)

    assert summary["status"] == "partial"
    assert summary["input_drug_count"] == 2
    assert summary["usable_payload_count"] == 1
    assert summary["record_count"] == 1
    assert summary["response_dump_path"].endswith("api_responses.json")
    assert summary["output_path"].endswith("drug_gene_interactions.jsonl")
    assert checkpoint_file.exists()

    response_dump = json.loads((raw_dir / "api_responses.json").read_text())
    assert response_dump["responses"]["Gefitinib"]["method"] == "graphql"
    assert response_dump["responses"]["Erlotinib"]["errors"] == [
        "graphql_failed",
        "rest_failed",
    ]

    output_lines = (raw_dir / "drug_gene_interactions.jsonl").read_text().splitlines()
    assert len(output_lines) == 1
    assert json.loads(output_lines[0])["gene_symbol"] == "EGFR"


@pytest.mark.asyncio
async def test_run_preserve_existing_outputs_when_all_payloads_unusable(
    monkeypatch, tmp_path
):
    raw_dir = tmp_path / "raw" / "dgidb"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_dgidb_checkpoint.json"
    raw_dir.mkdir(parents=True, exist_ok=True)

    responses_path = raw_dir / "api_responses.json"
    output_path = raw_dir / "drug_gene_interactions.jsonl"
    responses_path.write_text('{"preserved": true}\n', encoding="utf-8")
    output_path.write_text('{"gene_symbol": "EGFR"}\n', encoding="utf-8")

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)
    monkeypatch.setattr(
        mod,
        "load_local_drugs",
        lambda limit=None: [
            {"drug_id": "gefitinib", "drug_name": "Gefitinib"},
            {"drug_id": "erlotinib", "drug_name": "Erlotinib"},
        ],
    )

    async def fake_fetch_interaction_payload(client, drug):
        return {
            "method": "rest",
            "payload": {"message": f"unusable-{drug['drug_id']}"},
            "errors": ["graphql_unusable", "rest_unusable"],
        }

    monkeypatch.setattr(
        mod, "fetch_interaction_payload", fake_fetch_interaction_payload
    )

    summary = await mod.run(limit=None, concurrency=2)

    assert summary["status"] == "preserved_previous_outputs"
    assert summary["usable_payload_count"] == 0
    assert summary["record_count"] == 0
    assert summary["response_dump_path"] == str(responses_path)
    assert summary["output_path"] == str(output_path)
    assert "response_snapshot_path" not in summary
    assert "snapshot_path" not in summary
    assert responses_path.read_text(encoding="utf-8") == '{"preserved": true}\n'
    assert output_path.read_text(encoding="utf-8") == '{"gene_symbol": "EGFR"}\n'


@pytest.mark.asyncio
async def test_run_preserve_existing_outputs_when_all_payloads_unusable_on_initial_run(
    monkeypatch, tmp_path
):
    raw_dir = tmp_path / "raw" / "dgidb"
    checkpoint_file = tmp_path / "checkpoints" / "fetch_dgidb_checkpoint.json"

    monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mod, "CHECKPOINT_FILE", checkpoint_file)
    monkeypatch.setattr(
        mod,
        "load_local_drugs",
        lambda limit=None: [{"drug_id": "gefitinib", "drug_name": "Gefitinib"}],
    )

    async def fake_fetch_interaction_payload(client, drug):
        return {
            "method": None,
            "payload": None,
            "errors": ["graphql_failed", "rest_failed"],
        }

    monkeypatch.setattr(
        mod, "fetch_interaction_payload", fake_fetch_interaction_payload
    )

    summary = await mod.run(limit=None, concurrency=1)

    assert summary["status"] == "preserved_previous_outputs"
    assert summary["usable_payload_count"] == 0
    assert summary["record_count"] == 0
    assert "response_dump_path" not in summary
    assert "output_path" not in summary
    assert not (raw_dir / "api_responses.json").exists()
    assert not (raw_dir / "drug_gene_interactions.jsonl").exists()
