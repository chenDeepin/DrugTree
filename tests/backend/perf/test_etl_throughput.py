from .helpers import record_backend_metric, run_etl_phase_benchmark


def test_etl_phase_records_family_lineage_and_embed_timings(tmp_path):
    measurement = run_etl_phase_benchmark(tmp_path / "etl-benchmark")

    assert measurement["family_count"] >= 1
    assert measurement["total_ms"] > 0
    assert measurement["generated_json_files"]
    assert measurement["generated_js_files"]

    record_backend_metric(
        "etl_phase",
        {
            **measurement,
            "budget_ms": 90_000,
            "requires_percent_improvement_from_task_1_baseline": 25,
            "within_budget": measurement["total_ms"] <= 90_000,
            "baseline_capture_only": True,
        },
    )

    assert measurement["total_ms"] <= 90_000
