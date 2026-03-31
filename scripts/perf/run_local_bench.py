#!/usr/bin/env python3
"""Run the local DrugTree performance benchmark suites and write a JSON summary."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / ".sisyphus" / "evidence" / "final-performance-summary.json"
DEFAULT_FIXTURES_OUTPUT = REPO_ROOT / "tests" / "fixtures" / "perf"
TASK_1_BASELINE_PATH = (
    REPO_ROOT / ".sisyphus" / "evidence" / "task-1-benchmark-contract.json"
)
TASK_12_DECISION_PATH = (
    REPO_ROOT / ".sisyphus" / "evidence" / "task-12-sqlite-read-model.json"
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite", choices=("all", "frontend", "backend"), default="all"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fixtures-output", type=Path, default=DEFAULT_FIXTURES_OUTPUT)
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument(
        "--post-task-11",
        action="store_true",
        help="Evaluate the Task 12 trigger as if Tasks 1-11 were complete.",
    )
    return parser.parse_args(argv)


def run_command(
    command: list[str], *, env: dict[str, str], description: str
) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "description": description,
        "command": command,
        "exit_code": completed.returncode,
        "duration_ms": round(elapsed_ms, 3),
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_budget(
    measurement: dict[str, Any] | None, *, field: str, budget: float
) -> dict[str, Any]:
    if not measurement:
        return {"status": "missing", "field": field, "budget": budget}
    value = measurement.get(field)
    if value is None:
        return {"status": "missing", "field": field, "budget": budget}
    return {
        "status": "pass" if float(value) <= budget else "fail",
        "field": field,
        "budget": budget,
        "observed": value,
    }


def evaluate_payload_budget(
    measurement: dict[str, Any] | None, *, budget: int
) -> dict[str, Any]:
    if not measurement:
        return {"status": "missing", "field": "max_payload_bytes", "budget": budget}
    value = measurement.get("max_payload_bytes")
    if value is None:
        return {"status": "missing", "field": "max_payload_bytes", "budget": budget}
    return {
        "status": "pass" if int(value) <= budget else "fail",
        "field": "max_payload_bytes",
        "budget": budget,
        "observed": value,
    }


def evaluate_improvement(
    current: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
    *,
    field: str,
    required_improvement_pct: float,
) -> dict[str, Any]:
    if not current or not baseline:
        return {
            "status": "missing",
            "field": field,
            "required_improvement_pct": required_improvement_pct,
        }

    current_value = current.get(field)
    baseline_value = baseline.get(field)
    if current_value is None or baseline_value in (None, 0):
        return {
            "status": "missing",
            "field": field,
            "required_improvement_pct": required_improvement_pct,
        }

    improvement_pct = (
        (float(baseline_value) - float(current_value)) / float(baseline_value)
    ) * 100
    return {
        "status": "pass" if improvement_pct >= required_improvement_pct else "fail",
        "field": field,
        "required_improvement_pct": required_improvement_pct,
        "baseline": baseline_value,
        "observed": current_value,
        "improvement_pct": round(improvement_pct, 3),
    }


def build_summary(
    *,
    output_path: Path,
    fixtures_output: Path,
    suite: str,
    post_task_11: bool,
    command_results: list[dict[str, Any]],
    failed_exit_code: int | None,
) -> dict[str, Any]:
    evidence = load_json(output_path)
    task_1_baseline = load_json(TASK_1_BASELINE_PATH)
    manifest = load_json(fixtures_output / "manifest.json")
    frontend = evidence.get("frontend", {})
    backend = evidence.get("backend", {})
    baseline_frontend = task_1_baseline.get("frontend", {})
    baseline_backend = task_1_baseline.get("backend", {})
    backend_metrics = backend.get("metrics", {}) if isinstance(backend, dict) else {}
    baseline_backend_metrics = (
        baseline_backend.get("metrics", {})
        if isinstance(baseline_backend, dict)
        else {}
    )
    api = {
        "drugs_list": backend_metrics.get("drugs_list"),
        "graph_neighborhood": backend_metrics.get("graph_neighborhood"),
        "graph_evidence": backend_metrics.get("graph_evidence"),
    }
    etl = evidence.get("etl") or backend_metrics.get("etl_phase")
    baseline_etl = task_1_baseline.get("etl") or baseline_backend_metrics.get(
        "etl_phase"
    )

    frontend_metrics = frontend.get("metrics", {}) if isinstance(frontend, dict) else {}
    baseline_frontend_metrics = (
        baseline_frontend.get("metrics", {})
        if isinstance(baseline_frontend, dict)
        else {}
    )
    budget_evaluation = {
        "cold_boot": evaluate_budget(
            frontend_metrics.get("cold_boot"), field="median_ms", budget=1800
        ),
        "filter_interaction": evaluate_budget(
            frontend_metrics.get("filter_interaction"), field="median_ms", budget=120
        ),
        "route_to_detail": evaluate_budget(
            frontend_metrics.get("route_to_detail"), field="median_ms", budget=500
        ),
        "api_drugs": evaluate_budget(api.get("drugs_list"), field="p95_ms", budget=120),
        "graph_neighborhood_latency": evaluate_budget(
            api.get("graph_neighborhood"), field="p95_ms", budget=180
        ),
        "graph_neighborhood_payload": evaluate_payload_budget(
            api.get("graph_neighborhood"), budget=300 * 1024
        ),
        "graph_evidence_latency": evaluate_budget(
            api.get("graph_evidence"), field="p95_ms", budget=80
        ),
        "graph_evidence_payload": evaluate_payload_budget(
            api.get("graph_evidence"), budget=20 * 1024
        ),
        "deterministic_etl": evaluate_budget(
            etl if isinstance(etl, dict) else None, field="total_ms", budget=90_000
        ),
        "cold_boot_improvement_vs_task_1_baseline": {
            **evaluate_improvement(
                frontend_metrics.get("cold_boot"),
                baseline_frontend_metrics.get("cold_boot"),
                field="median_ms",
                required_improvement_pct=25,
            ),
        },
        "deterministic_etl_improvement_vs_task_1_baseline": {
            **evaluate_improvement(
                etl if isinstance(etl, dict) else None,
                baseline_etl if isinstance(baseline_etl, dict) else None,
                field="total_ms",
                required_improvement_pct=25,
            ),
        },
        "freshness_policy": {
            "status": "contract_recorded",
            "max_stale_hours": 24,
            "invalidate_on_canonical_hash_change": True,
        },
    }

    trigger_failures = [
        name
        for name in (
            "cold_boot",
            "filter_interaction",
            "route_to_detail",
            "graph_neighborhood_latency",
            "graph_neighborhood_payload",
            "deterministic_etl",
        )
        if budget_evaluation[name].get("status") == "fail"
    ]

    return {
        **evidence,
        "summary_version": 1,
        "generated_at": utcnow_iso(),
        "suite": suite,
        "contract_path": "docs/performance/benchmark-contract.md",
        "fixture_manifest": manifest,
        "api": api,
        "etl": etl,
        "budget_evaluation": budget_evaluation,
        "task_12_trigger": {
            "eligible_after_tasks_1_11": post_task_11,
            "activation_threshold_failed_budgets": 2,
            "tracked_failures": trigger_failures,
            "threshold_met": post_task_11 and len(trigger_failures) >= 2,
            "rule": {
                "cold_boot_ms": 1800,
                "filter_interaction_ms": 120,
                "route_to_detail_ms": 500,
                "graph_neighborhood_p95_ms": 180,
                "graph_neighborhood_payload_bytes": 300 * 1024,
                "deterministic_etl_ms": 90_000,
            },
        },
        "suite_status": "failed" if failed_exit_code else "passed",
        "failed_exit_code": failed_exit_code,
        "command_results": command_results,
    }


def write_task_12_decision(summary: dict[str, Any]) -> None:
    task_12 = summary.get("task_12_trigger", {})
    TASK_12_DECISION_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": summary.get("generated_at"),
        "plan": ".sisyphus/plans/drugtree-next-stage-performance-plan.md",
        "eligible_after_tasks_1_11": task_12.get("eligible_after_tasks_1_11", False),
        "threshold_met": task_12.get("threshold_met", False),
        "tracked_failures": task_12.get("tracked_failures", []),
        "decision": "implement_sqlite_read_model"
        if task_12.get("threshold_met")
        else "skip_sqlite_read_model",
        "reason": "threshold_not_met"
        if not task_12.get("threshold_met")
        else "threshold_met",
    }
    TASK_12_DECISION_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["DRUGTREE_PERF_EVIDENCE_PATH"] = str(args.output)
    env["DRUGTREE_PERF_FIXTURES_PATH"] = str(
        args.fixtures_output / "benchmark-fixtures.json"
    )
    env.setdefault("DRUGTREE_BENCHMARK_MODE", "1")

    command_results: list[dict[str, Any]] = []
    failed_exit_code: int | None = None

    if not args.skip_generate:
        command_results.append(
            run_command(
                [
                    sys.executable,
                    "scripts/perf/generate_fixtures.py",
                    "--output",
                    str(args.fixtures_output),
                ],
                env=env,
                description="Generate deterministic performance fixtures",
            )
        )
        if command_results[-1]["exit_code"] != 0:
            failed_exit_code = command_results[-1]["exit_code"]

    if failed_exit_code is None and args.suite in {"all", "frontend"}:
        command_results.append(
            run_command(
                [
                    "npx",
                    "playwright",
                    "test",
                    "tests/frontend/e2e/perf",
                    "--config",
                    "tests/frontend/playwright.config.ts",
                    "--project=chromium",
                ],
                env=env,
                description="Run frontend performance Playwright suite",
            )
        )
        if command_results[-1]["exit_code"] != 0:
            failed_exit_code = command_results[-1]["exit_code"]

    if failed_exit_code is None and args.suite in {"all", "backend"}:
        command_results.append(
            run_command(
                ["pytest", "tests/backend/perf", "-q"],
                env=env,
                description="Run backend performance pytest suite",
            )
        )
        if command_results[-1]["exit_code"] != 0:
            failed_exit_code = command_results[-1]["exit_code"]

    summary = build_summary(
        output_path=args.output,
        fixtures_output=args.fixtures_output,
        suite=args.suite,
        post_task_11=args.post_task_11,
        command_results=command_results,
        failed_exit_code=failed_exit_code,
    )
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.post_task_11:
        write_task_12_decision(summary)
    print(f"Wrote benchmark summary to {args.output}")
    return failed_exit_code or 0


if __name__ == "__main__":
    raise SystemExit(main())
