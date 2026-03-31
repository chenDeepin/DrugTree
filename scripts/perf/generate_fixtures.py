#!/usr/bin/env python3
"""Generate deterministic DrugTree performance fixtures from canonical repo data."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "tests" / "fixtures" / "perf"
TOKEN_PATTERN = re.compile(r"[a-z0-9]{4,}")
SORT_KEYS = (
    "id",
    "edge_id",
    "family_id",
    "drug_id",
    "disease_id",
    "canonical_name",
    "name",
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def normalized_sort_key(item: Any) -> tuple[Any, ...]:
    if isinstance(item, dict):
        for key in SORT_KEYS:
            value = item.get(key)
            if value is not None:
                return (0, key, str(value))
        normalized = json.dumps(
            normalize_for_hash(item), ensure_ascii=False, separators=(",", ":")
        )
        return (1, sha256_bytes(normalized.encode("utf-8")))
    if isinstance(item, list):
        normalized = json.dumps(
            normalize_for_hash(item), ensure_ascii=False, separators=(",", ":")
        )
        return (2, sha256_bytes(normalized.encode("utf-8")))
    return (3, json.dumps(item, ensure_ascii=False, sort_keys=True))


def normalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_for_hash(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized_items = [normalize_for_hash(item) for item in value]
        return sorted(normalized_items, key=normalized_sort_key)
    return value


def load_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Required canonical input missing: {path}") from exc
    return json.loads(raw.decode("utf-8"))


def count_records(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in (
            "drugs",
            "diseases",
            "edges",
            "families",
            "regions",
            "visible_regions",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    if isinstance(payload, list):
        return len(payload)
    return 0


def require_drug(
    drugs_by_id: dict[str, dict[str, Any]], drug_id: str
) -> dict[str, Any]:
    drug = drugs_by_id.get(drug_id)
    if drug is None:
        raise ValueError(f"Required benchmark anchor drug missing: {drug_id}")
    return drug


def drug_matches_query(drug: dict[str, Any], query: str) -> bool:
    query_lower = query.lower()
    haystacks = [
        str(drug.get("name") or ""),
        str(drug.get("class") or drug.get("class_name") or ""),
        str(drug.get("company") or ""),
        str(drug.get("indication") or ""),
        *[str(value) for value in (drug.get("targets") or [])],
        *[str(value) for value in (drug.get("synonyms") or [])],
    ]
    return any(query_lower in haystack.lower() for haystack in haystacks)


def extract_tokens(drug: dict[str, Any]) -> set[str]:
    values = [
        str(drug.get("name") or ""),
        *[str(value) for value in (drug.get("synonyms") or [])],
        str(drug.get("class") or drug.get("class_name") or ""),
        str(drug.get("indication") or ""),
        *[str(value) for value in (drug.get("targets") or [])],
    ]
    joined = " ".join(values).lower()
    return set(TOKEN_PATTERN.findall(joined))


def choose_combined_filter_fixture(
    diseases: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    drugs_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    disease_to_drugs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in sorted(
        edges,
        key=lambda item: (
            str(item.get("disease_id") or ""),
            str(item.get("drug_id") or ""),
        ),
    ):
        disease_id = str(edge.get("disease_id") or "")
        drug_id = str(edge.get("drug_id") or "")
        drug = drugs_by_id.get(drug_id)
        if disease_id and drug is not None:
            disease_to_drugs[disease_id].append(drug)

    diseases_by_id = {
        str(disease.get("id")): disease for disease in diseases if disease.get("id")
    }

    fallback: dict[str, Any] | None = None
    for disease_id in sorted(disease_to_drugs):
        linked_drugs = disease_to_drugs[disease_id]
        if len(linked_drugs) < 2:
            continue

        by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for drug in linked_drugs:
            category = str(drug.get("atc_category") or "").upper()
            if category and category != "ALL":
                by_category[category].append(drug)

        for category in sorted(by_category):
            category_drugs = by_category[category]
            token_counts: Counter[str] = Counter()
            for drug in category_drugs:
                token_counts.update(extract_tokens(drug))

            for token, _count in sorted(
                token_counts.items(), key=lambda item: (-item[1], item[0])
            ):
                expected_ids = sorted(
                    drug["id"]
                    for drug in category_drugs
                    if drug_matches_query(drug, token)
                )
                if len(expected_ids) >= 2:
                    disease = diseases_by_id.get(disease_id, {})
                    return {
                        "disease_id": disease_id,
                        "disease_name": disease.get("canonical_name") or disease_id,
                        "category": category,
                        "search_query": token,
                        "expected_ids": expected_ids,
                        "expected_count": len(expected_ids),
                    }
                if fallback is None and expected_ids:
                    disease = diseases_by_id.get(disease_id, {})
                    fallback = {
                        "disease_id": disease_id,
                        "disease_name": disease.get("canonical_name") or disease_id,
                        "category": category,
                        "search_query": token,
                        "expected_ids": expected_ids,
                        "expected_count": len(expected_ids),
                    }

    if fallback is not None:
        return fallback
    raise ValueError(
        "Unable to derive a deterministic combined filter fixture from canonical disease edges"
    )


def choose_search_fixture(drugs: list[dict[str, Any]]) -> dict[str, Any]:
    preferred_query = "statin"
    expected_ids = sorted(
        drug["id"] for drug in drugs if drug_matches_query(drug, preferred_query)
    )
    if expected_ids:
        return {
            "query": preferred_query,
            "expected_ids": expected_ids,
            "expected_count": len(expected_ids),
        }

    token_counts: Counter[str] = Counter()
    for drug in drugs:
        token_counts.update(extract_tokens(drug))

    for token, _count in sorted(
        token_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        expected_ids = sorted(
            drug["id"] for drug in drugs if drug_matches_query(drug, token)
        )
        if len(expected_ids) >= 2:
            return {
                "query": token,
                "expected_ids": expected_ids,
                "expected_count": len(expected_ids),
            }

    raise ValueError(
        "Unable to derive a deterministic search fixture from canonical drugs"
    )


def build_fixtures(
    *,
    drugs_path: Path,
    diseases_path: Path,
    disease_drug_edges_path: Path,
    body_ontology_path: Path,
    drug_families_path: Path,
    lineage_edges_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_paths = {
        "drugs": drugs_path,
        "diseases": diseases_path,
        "disease_drug_edges": disease_drug_edges_path,
        "body_ontology": body_ontology_path,
        "drug_families": drug_families_path,
        "lineage_edges": lineage_edges_path,
    }

    source_payloads: dict[str, Any] = {}
    source_manifest: dict[str, Any] = {}
    for name, path in source_paths.items():
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        source_payloads[name] = payload
        source_manifest[name] = {
            "path": str(path.relative_to(REPO_ROOT)),
            "sha256": sha256_bytes(raw),
            "record_count": count_records(payload),
        }

    drugs = source_payloads["drugs"].get("drugs", [])
    diseases = source_payloads["diseases"].get("diseases", [])
    disease_drug_edges = source_payloads["disease_drug_edges"].get("edges", [])
    drug_families = source_payloads["drug_families"].get("families", [])
    lineage_edges = source_payloads["lineage_edges"].get("edges", [])
    body_regions = source_payloads["body_ontology"].get("visible_regions", [])

    drugs_by_id = {str(drug["id"]): drug for drug in drugs if drug.get("id")}
    atorvastatin = require_drug(drugs_by_id, "atorvastatin")

    lineage_edge_ids = {
        str(edge.get("edge_id")) for edge in lineage_edges if edge.get("edge_id")
    }
    if "simvastatin_to_atorvastatin" not in lineage_edge_ids:
        raise ValueError(
            "Required benchmark anchor edge missing: simvastatin_to_atorvastatin"
        )

    if not any(str(drug.get("atc_category") or "").upper() == "C" for drug in drugs):
        raise ValueError("Required benchmark anchor category missing: C")

    search_fixture = choose_search_fixture(drugs)
    combined_filter_fixture = choose_combined_filter_fixture(
        diseases, disease_drug_edges, drugs_by_id
    )
    category_c_ids = sorted(
        str(drug["id"])
        for drug in drugs
        if str(drug.get("atc_category") or "").upper() == "C"
    )

    benchmark_fixtures = {
        "fixture_version": 1,
        "generated_at": utcnow_iso(),
        "selection_rules": {
            "ordering": "sort by stable identifier when present, otherwise by normalized JSON sha256",
            "search_match": "same case-insensitive contains logic as backend search helpers for name, targets, class, synonyms, company, and indication",
            "combined_filter_fixture": "first deterministic disease/category/query tuple with at least one explicit disease-edge-backed match",
        },
        "sources": source_manifest,
        "frontend": {
            "cold_boot": {
                "render_selector": ".drug-card",
                "expected_minimum_cards": 1,
                "static_harness_base_url": "http://localhost:8766",
            },
            "category_filter": {
                "category": "C",
                "tag_selector": '.atc-tag[data-category="C"]',
                "expected_count": len(category_c_ids),
                "sample_expected_ids": category_c_ids[:10],
            },
            "search_filter": search_fixture,
            "route_detail": {
                "drug_id": "atorvastatin",
                "drug_name": atorvastatin.get("name") or "atorvastatin",
                "prefilter_query": "atorvastatin",
                "detail_selector": "#drug-detail-page",
            },
            "combined_filter": combined_filter_fixture,
        },
        "backend": {
            "drugs_endpoint": {
                "path": "/api/v1/drugs?limit=50",
                "limit": 50,
                "expected_status": 200,
            },
            "graph_neighborhood": {
                "path": "/api/v1/graph/neighborhood/drug:atorvastatin?max_hops=1",
                "node_id": "drug:atorvastatin",
                "max_hops": 1,
                "expected_status": 200,
            },
            "graph_evidence": {
                "path": "/api/v1/graph/evidence/simvastatin_to_atorvastatin",
                "edge_id": "simvastatin_to_atorvastatin",
                "expected_status": 200,
            },
        },
        "etl": {
            "phase_name": "family_build_plus_lineage_build_plus_embed_generation",
            "canonical_drug_count": len(drugs),
            "canonical_disease_count": len(diseases),
            "canonical_disease_edge_count": len(disease_drug_edges),
            "body_region_count": len(body_regions),
            "existing_family_count": len(drug_families),
            "existing_lineage_edge_count": len(lineage_edges),
            "frontend_embed_script": "scripts/build_frontend_embeds.py",
        },
    }

    manifest = {
        "manifest_version": 1,
        "generated_at": benchmark_fixtures["generated_at"],
        "source_hash_policy": "sha256(raw canonical file bytes)",
        "fixture_hash_policy": "sha256(pretty-printed generated fixture JSON bytes)",
        "sources": source_manifest,
    }
    return benchmark_fixtures, manifest


def write_output(
    output_dir: Path, benchmark_fixtures: dict[str, Any], manifest: dict[str, Any]
) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir.parent / f".{output_dir.name}.tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    try:
        temp_dir.mkdir(parents=True, exist_ok=False)

        fixtures_path = temp_dir / "benchmark-fixtures.json"
        fixtures_bytes = (
            json.dumps(benchmark_fixtures, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        fixtures_path.write_bytes(fixtures_bytes)

        manifest["fixtures"] = {
            "benchmark-fixtures.json": {
                "sha256": sha256_bytes(fixtures_bytes),
                "scenario_sections": sorted(
                    key
                    for key in benchmark_fixtures.keys()
                    if key in {"frontend", "backend", "etl"}
                ),
            },
            "manifest.json": {
                "sha256": "",
                "hash_input": "manifest JSON bytes with fixtures.manifest.json.sha256 blank",
            },
        }
        manifest_path = temp_dir / "manifest.json"
        manifest_projection = copy.deepcopy(manifest)
        manifest_projection["fixtures"]["manifest.json"]["sha256"] = ""
        manifest["fixtures"]["manifest.json"]["sha256"] = sha256_bytes(
            (
                json.dumps(manifest_projection, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        if output_dir.exists():
            shutil.rmtree(output_dir)
        temp_dir.replace(output_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--test-mode", choices=("normal", "validate-inputs"), default="normal"
    )
    parser.add_argument(
        "--drugs-path", type=Path, default=REPO_ROOT / "data" / "drugs.json"
    )
    parser.add_argument(
        "--diseases-path", type=Path, default=REPO_ROOT / "data" / "diseases.json"
    )
    parser.add_argument(
        "--disease-drug-edges-path",
        type=Path,
        default=REPO_ROOT / "data" / "disease_drug_edges.json",
    )
    parser.add_argument(
        "--body-ontology-path",
        type=Path,
        default=REPO_ROOT / "data" / "ontology" / "body-ontology.json",
    )
    parser.add_argument(
        "--drug-families-path",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "drug_families.json",
    )
    parser.add_argument(
        "--lineage-edges-path",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "lineage_edges.json",
    )
    return parser


def validate_paths(paths: list[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Required canonical input missing: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    required_paths = [
        args.drugs_path,
        args.diseases_path,
        args.disease_drug_edges_path,
        args.body_ontology_path,
        args.drug_families_path,
        args.lineage_edges_path,
    ]

    try:
        validate_paths(required_paths)
        if args.test_mode == "validate-inputs":
            return 0

        benchmark_fixtures, manifest = build_fixtures(
            drugs_path=args.drugs_path,
            diseases_path=args.diseases_path,
            disease_drug_edges_path=args.disease_drug_edges_path,
            body_ontology_path=args.body_ontology_path,
            drug_families_path=args.drug_families_path,
            lineage_edges_path=args.lineage_edges_path,
        )
        write_output(args.output, benchmark_fixtures, manifest)
        print(f"Wrote deterministic performance fixtures to {args.output}")
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
