from __future__ import annotations

import importlib.util
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.backend.etl.family_builder import FamilyBuilder
from src.backend.etl.lineage_builder import LineageBuilder


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "perf" / "benchmark-fixtures.json"
)
DEFAULT_EVIDENCE_PATH = (
    REPO_ROOT / ".sisyphus" / "evidence" / "final-performance-summary.json"
)
BACKEND_EVIDENCE_DIR = REPO_ROOT / ".sisyphus" / "evidence" / "backend-perf"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fixture_path() -> Path:
    override = Path(
        os.environ.get("DRUGTREE_PERF_FIXTURES_PATH", str(DEFAULT_FIXTURE_PATH))
    )
    return override if override.is_absolute() else (REPO_ROOT / override)


def evidence_path() -> Path:
    override = Path(
        os.environ.get("DRUGTREE_PERF_EVIDENCE_PATH", str(DEFAULT_EVIDENCE_PATH))
    )
    return override if override.is_absolute() else (REPO_ROOT / override)


def load_benchmark_fixtures() -> dict[str, Any]:
    path = fixture_path()
    if not path.exists():
        raise AssertionError(
            f"Benchmark fixture file missing: {path}. Run `python3 scripts/perf/generate_fixtures.py --output tests/fixtures/perf` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = max(
        0, min(len(sorted_values) - 1, int((len(sorted_values) * ratio) + 0.999999) - 1)
    )
    return float(sorted_values[index])


def summarize_samples(samples: list[float]) -> dict[str, Any]:
    rounded = [round(sample, 3) for sample in samples]
    return {
        "samples_ms": rounded,
        "sample_count": len(rounded),
        "min_ms": round(min(rounded), 3) if rounded else 0.0,
        "max_ms": round(max(rounded), 3) if rounded else 0.0,
        "median_ms": round(percentile(rounded, 0.5), 3),
        "p95_ms": round(percentile(rounded, 0.95), 3),
    }


async def measure_client_get(
    client: Any,
    path: str,
    *,
    iterations: int = 15,
    warmups: int = 3,
) -> dict[str, Any]:
    for _ in range(warmups):
        await client.get(path)

    samples: list[float] = []
    payload_sizes: list[int] = []
    statuses: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter()
        response = await client.get(path)
        elapsed_ms = (time.perf_counter() - started) * 1000
        samples.append(elapsed_ms)
        payload_sizes.append(len(response.content))
        statuses.append(response.status_code)

    summary = summarize_samples(samples)
    summary.update(
        {
            "path": path,
            "status_codes": statuses,
            "payload_bytes": payload_sizes,
            "max_payload_bytes": max(payload_sizes) if payload_sizes else 0,
            "median_payload_bytes": percentile(
                [float(size) for size in payload_sizes], 0.5
            )
            if payload_sizes
            else 0.0,
            "network_free": True,
            "same_host_backend": True,
        }
    )
    return summary


def _load_embed_module() -> Any:
    script_path = REPO_ROOT / "scripts" / "build_frontend_embeds.py"
    spec = importlib.util.spec_from_file_location(
        "perf_build_frontend_embeds", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load embed builder module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_etl_phase_benchmark(output_root: Path) -> dict[str, Any]:
    canonical_drugs = REPO_ROOT / "data" / "drugs.json"
    family_output = output_root / "processed" / "drug_families.json"
    lineage_output = output_root / "processed" / "lineage_edges.json"

    output_root.mkdir(parents=True, exist_ok=True)
    family_output.parent.mkdir(parents=True, exist_ok=True)

    total_started = time.perf_counter()

    load_started = time.perf_counter()
    drugs = FamilyBuilder.load_drugs_from_json(str(canonical_drugs))
    load_ms = (time.perf_counter() - load_started) * 1000

    family_builder = FamilyBuilder()
    family_started = time.perf_counter()
    families = family_builder.build_families(drugs)
    family_builder.save_families(str(family_output))
    family_ms = (time.perf_counter() - family_started) * 1000

    lineage_builder = LineageBuilder()
    lineage_started = time.perf_counter()
    edges = lineage_builder.build_edges(drugs, families)
    lineage_builder.save_edges(str(lineage_output), edges)
    lineage_ms = (time.perf_counter() - lineage_started) * 1000

    embed_module = _load_embed_module()
    embed_frontend_root = output_root / "frontend"
    embed_assets_dir = embed_frontend_root / "assets"
    embed_assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPO_ROOT / "src" / "frontend" / "assets" / "human-body.svg",
        embed_assets_dir / "human-body.svg",
    )
    embed_module.FRONTEND_ROOT = embed_frontend_root
    embed_module.FRONTEND_DATA_DIR = embed_frontend_root / "data"
    embed_started = time.perf_counter()
    embed_module.main()
    embed_ms = (time.perf_counter() - embed_started) * 1000

    total_ms = (time.perf_counter() - total_started) * 1000
    generated_files = sorted(
        str(path.relative_to(output_root)) for path in output_root.rglob("*.json")
    )
    generated_js_files = sorted(
        str(path.relative_to(output_root)) for path in output_root.rglob("*.js")
    )

    return {
        "network_free": True,
        "phase_name": "family_build_plus_lineage_build_plus_embed_generation",
        "load_drugs_ms": round(load_ms, 3),
        "family_build_ms": round(family_ms, 3),
        "lineage_build_ms": round(lineage_ms, 3),
        "embed_generation_ms": round(embed_ms, 3),
        "total_ms": round(total_ms, 3),
        "family_count": len(families),
        "lineage_edge_count": len(edges),
        "generated_json_files": generated_files,
        "generated_js_files": generated_js_files,
    }


def _load_evidence() -> dict[str, Any]:
    path = evidence_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"benchmark_contract_version": 1}


def record_backend_metric(metric_name: str, payload: dict[str, Any]) -> None:
    aggregate_path = evidence_path()
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    BACKEND_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    evidence = _load_evidence()
    evidence["generated_at"] = utcnow_iso()
    backend = evidence.setdefault(
        "backend",
        {"suite": "pytest-network-free-benchmark", "metrics": {}},
    )
    backend.setdefault("metrics", {})[metric_name] = payload
    if metric_name == "etl_phase":
        evidence["etl"] = payload

    aggregate_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (BACKEND_EVIDENCE_DIR / f"{metric_name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
