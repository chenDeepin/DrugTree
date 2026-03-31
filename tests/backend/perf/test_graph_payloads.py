import pytest

from .helpers import load_benchmark_fixtures, measure_client_get, record_backend_metric


@pytest.mark.asyncio
async def test_graph_neighborhood_records_latency_and_payload_budget(api_client):
    fixtures = load_benchmark_fixtures()
    scenario = fixtures["backend"]["graph_neighborhood"]

    measurement = await measure_client_get(
        api_client,
        scenario["path"],
        iterations=12,
        warmups=2,
    )

    assert measurement["sample_count"] == 12
    assert all(
        status == scenario["expected_status"] for status in measurement["status_codes"]
    )
    assert measurement["max_payload_bytes"] > 0

    record_backend_metric(
        "graph_neighborhood",
        {
            **measurement,
            "budget_ms": 180,
            "payload_budget_bytes": 300 * 1024,
            "measurement_kind": "p95",
            "within_budget": measurement["p95_ms"] <= 180,
            "within_payload_budget": measurement["max_payload_bytes"] <= 300 * 1024,
        },
    )

    assert measurement["p95_ms"] <= 180
    assert measurement["max_payload_bytes"] <= 300 * 1024


@pytest.mark.asyncio
async def test_graph_evidence_records_latency_and_payload_budget(api_client):
    fixtures = load_benchmark_fixtures()
    scenario = fixtures["backend"]["graph_evidence"]

    measurement = await measure_client_get(
        api_client,
        scenario["path"],
        iterations=12,
        warmups=2,
    )

    assert measurement["sample_count"] == 12
    assert all(
        status == scenario["expected_status"] for status in measurement["status_codes"]
    )
    assert measurement["max_payload_bytes"] > 0

    record_backend_metric(
        "graph_evidence",
        {
            **measurement,
            "budget_ms": 80,
            "payload_budget_bytes": 20 * 1024,
            "measurement_kind": "p95",
            "within_budget": measurement["p95_ms"] <= 80,
            "within_payload_budget": measurement["max_payload_bytes"] <= 20 * 1024,
        },
    )

    assert measurement["p95_ms"] <= 80
    assert measurement["max_payload_bytes"] <= 20 * 1024
