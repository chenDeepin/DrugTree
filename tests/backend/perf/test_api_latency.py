import pytest

from .helpers import load_benchmark_fixtures, measure_client_get, record_backend_metric


@pytest.mark.asyncio
async def test_drugs_list_latency_records_p95(api_client):
    fixtures = load_benchmark_fixtures()
    scenario = fixtures["backend"]["drugs_endpoint"]

    measurement = await measure_client_get(
        api_client,
        scenario["path"],
        iterations=15,
        warmups=3,
    )

    assert measurement["sample_count"] == 15
    assert all(
        status == scenario["expected_status"] for status in measurement["status_codes"]
    )
    assert measurement["max_payload_bytes"] > 0

    record_backend_metric(
        "drugs_list",
        {
            **measurement,
            "budget_ms": 120,
            "measurement_kind": "p95",
            "within_budget": measurement["p95_ms"] <= 120,
        },
    )

    assert measurement["p95_ms"] <= 120
