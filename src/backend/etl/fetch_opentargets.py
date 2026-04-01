#!/usr/bin/env python3
"""Fetch Open Targets drug-target and target-disease edges into raw JSONL files."""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import httpx

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "opentargets"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "fetch_opentargets_checkpoint.json"
DRUGS_FILE = DATA_DIR / "drugs.json"
DISEASES_FILE = DATA_DIR / "diseases.json"

GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"

DRUG_MECHANISMS_QUERY = """
query DrugMechanisms($chemblId: String!) {
  drug(chemblId: $chemblId) {
    id
    name
    maximumClinicalStage
    mechanismsOfAction {
      rows {
        mechanismOfAction
        actionType
        targetName
        targets {
          id
          approvedSymbol
          approvedName
        }
      }
    }
  }
}
"""

TARGET_SEARCH_QUERY = """
query SearchTarget($query: String!, $page: Pagination) {
  search(queryString: $query, entityNames: [\"target\"], page: $page) {
    total
    hits {
      id
      name
      entity
      description
    }
  }
}
"""

TARGET_DISEASES_QUERY = """
query TargetDiseases($ensemblId: String!, $page: Pagination) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    associatedDiseases(page: $page) {
      count
      rows {
        score
        datasourceScores {
          id
          score
        }
        disease {
          id
          name
          dbXRefs
        }
      }
    }
  }
}
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: Any) -> str:
    return normalize_text(value).lower()


def load_local_drugs(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not DRUGS_FILE.exists():
        LOGGER.warning("Canonical drugs file missing: %s", DRUGS_FILE)
        return []

    payload = json.loads(DRUGS_FILE.read_text(encoding="utf-8"))
    drugs = payload.get("drugs", []) if isinstance(payload, dict) else payload

    items: List[Dict[str, Any]] = []
    for drug in drugs:
        if not isinstance(drug, dict):
            continue
        chembl_id = normalize_text(drug.get("chembl_id"))
        if not chembl_id:
            continue
        items.append(
            {
                "drug_id": normalize_text(drug.get("id")),
                "drug_name": normalize_text(drug.get("name")),
                "chembl_id": chembl_id,
                "targets": drug.get("targets", []) or [],
            }
        )

    if limit is not None and limit > 0:
        return items[:limit]
    return items


def load_local_disease_lookup() -> Dict[str, Dict[str, str]]:
    if not DISEASES_FILE.exists():
        LOGGER.warning("Canonical diseases file missing: %s", DISEASES_FILE)
        return {}

    payload = json.loads(DISEASES_FILE.read_text(encoding="utf-8"))
    diseases = payload.get("diseases", []) if isinstance(payload, dict) else payload
    lookup: Dict[str, Dict[str, str]] = {}

    for disease in diseases:
        if not isinstance(disease, dict):
            continue
        disease_id = normalize_text(disease.get("id"))
        if not disease_id:
            continue

        values = [
            disease.get("id"),
            disease.get("canonical_name"),
            disease.get("mondo_id"),
            disease.get("mesh_id"),
            disease.get("doid_id"),
            disease.get("efo_id"),
        ]
        values.extend(disease.get("synonyms", []) or [])

        entry = {
            "disease_id": disease_id,
            "disease_name": normalize_text(disease.get("canonical_name")) or disease_id,
            "mondo_id": normalize_text(disease.get("mondo_id")),
        }
        for value in values:
            key = normalize_key(value).replace("_", ":") if value else ""
            if key:
                lookup.setdefault(key, entry)
            plain_key = normalize_key(value)
            if plain_key:
                lookup.setdefault(plain_key, entry)

    return lookup


def stage_to_phase(value: Any) -> Optional[int]:
    stage = normalize_text(value).upper()
    mapping = {
        "PRECLINICAL": 0,
        "PHASE_1": 1,
        "PHASE_2": 2,
        "PHASE_3": 3,
        "APPROVAL": 4,
        "WITHDRAWN": 4,
    }
    return mapping.get(stage)


def write_jsonl_with_snapshot(
    path: Path, records: Iterable[Dict[str, Any]]
) -> Tuple[Path, int]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = path.with_name(f"{path.stem}_{timestamp_tag()}{path.suffix}")
    count = 0

    with (
        path.open("w", encoding="utf-8") as current,
        snapshot.open("w", encoding="utf-8") as stamped,
    ):
        for record in records:
            line = json.dumps(record, ensure_ascii=False)
            current.write(line + "\n")
            stamped.write(line + "\n")
            count += 1

    return snapshot, count


def write_checkpoint(payload: Dict[str, Any]) -> None:
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def graphql_query(
    client: httpx.AsyncClient, query: str, variables: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    try:
        response = await client.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.warning("Open Targets request failed: %s", exc)
        return None

    if payload.get("errors"):
        LOGGER.warning("Open Targets GraphQL error: %s", payload["errors"][:1])
        return None
    return payload.get("data")


def resolve_local_disease(
    disease: Dict[str, Any], disease_lookup: Dict[str, Dict[str, str]]
) -> Optional[Dict[str, str]]:
    candidates: List[str] = []
    disease_id = normalize_text(disease.get("id"))
    if disease_id:
        candidates.append(disease_id.replace("_", ":"))
        candidates.append(disease_id)
    for xref in disease.get("dbXRefs", []) or []:
        candidates.append(normalize_text(xref))
    candidates.append(normalize_text(disease.get("name")))

    for candidate in candidates:
        key = normalize_key(candidate)
        if key in disease_lookup:
            return disease_lookup[key]
        colon_key = key.replace("_", ":")
        if colon_key in disease_lookup:
            return disease_lookup[colon_key]
    return None


async def fetch_drug_target_edges(
    client: httpx.AsyncClient,
    drugs: List[Dict[str, Any]],
    concurrency: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    edges: List[Dict[str, Any]] = []
    target_symbol_to_id: Dict[str, str] = {}
    seen: Set[Tuple[str, str, str]] = set()
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def worker(drug: Dict[str, Any]) -> None:
        async with semaphore:
            data = await graphql_query(
                client,
                DRUG_MECHANISMS_QUERY,
                {"chemblId": drug["chembl_id"]},
            )
            node = (data or {}).get("drug") if data else None
            if not isinstance(node, dict):
                return

            for row in (node.get("mechanismsOfAction") or {}).get("rows") or []:
                for target in row.get("targets", []) or []:
                    target_id = normalize_text(target.get("id"))
                    target_symbol = normalize_text(target.get("approvedSymbol"))
                    if not target_id or not target_symbol:
                        continue
                    target_symbol_to_id[target_symbol.upper()] = target_id
                    key = (
                        normalize_text(drug.get("drug_id")),
                        target_id,
                        normalize_text(row.get("mechanismOfAction")),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(
                        {
                            "drug_id": normalize_text(drug.get("drug_id")),
                            "drug_name": normalize_text(node.get("name"))
                            or normalize_text(drug.get("drug_name")),
                            "target_id": target_id,
                            "target_symbol": target_symbol,
                            "target_ensembl_id": target_id,
                            "mechanism_of_action": normalize_text(
                                row.get("mechanismOfAction")
                            )
                            or normalize_text(row.get("actionType")),
                            "clinical_phase": stage_to_phase(
                                node.get("maximumClinicalStage")
                            ),
                            "association_score": 1.0,
                            "evidence_sources": ["mechanismsOfAction"],
                            "source_name": "opentargets",
                            "source_record_id": f"{drug['chembl_id']}:{target_id}",
                            "retrieved_at": utcnow_iso(),
                        }
                    )

    await asyncio.gather(*(worker(drug) for drug in drugs))
    return edges, target_symbol_to_id


async def resolve_target_ids(
    client: httpx.AsyncClient,
    symbols: Iterable[str],
    existing: Dict[str, str],
    concurrency: int,
) -> Dict[str, str]:
    resolved = dict(existing)
    missing = sorted(
        {
            symbol.upper()
            for symbol in symbols
            if symbol and symbol.upper() not in resolved
        }
    )
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def worker(symbol: str) -> None:
        async with semaphore:
            data = await graphql_query(
                client,
                TARGET_SEARCH_QUERY,
                {"query": symbol, "page": {"index": 0, "size": 5}},
            )
            search = (data or {}).get("search") if data else None
            hits = search.get("hits", []) if isinstance(search, dict) else []
            for hit in hits:
                if normalize_key(hit.get("entity")) != "target":
                    continue
                if normalize_text(hit.get("name")).upper() == symbol:
                    resolved[symbol] = normalize_text(hit.get("id"))
                    return
            if hits:
                resolved[symbol] = normalize_text(hits[0].get("id"))

    await asyncio.gather(*(worker(symbol) for symbol in missing))
    return resolved


async def fetch_target_disease_edges(
    client: httpx.AsyncClient,
    target_ids: Dict[str, str],
    disease_lookup: Dict[str, Dict[str, str]],
    page_size: int,
    concurrency: int,
) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str]] = set()
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def worker(target_symbol: str, target_id: str) -> None:
        async with semaphore:
            index = 0
            total = None
            fetched = 0

            while total is None or fetched < total:
                data = await graphql_query(
                    client,
                    TARGET_DISEASES_QUERY,
                    {
                        "ensemblId": target_id,
                        "page": {"index": index, "size": page_size},
                    },
                )
                node = (data or {}).get("target") if data else None
                associated = (
                    (node or {}).get("associatedDiseases")
                    if isinstance(node, dict)
                    else None
                )
                if not isinstance(associated, dict):
                    return

                rows = associated.get("rows", []) or []
                total = int(associated.get("count") or 0)
                if not rows:
                    return

                for row in rows:
                    disease = row.get("disease") or {}
                    resolved = resolve_local_disease(disease, disease_lookup)
                    if not resolved:
                        continue
                    datasource_scores = row.get("datasourceScores", []) or []
                    evidence_type = normalize_text(
                        datasource_scores[0].get("id")
                        if datasource_scores
                        else "association"
                    )
                    key = (target_id, resolved["disease_id"], evidence_type)
                    if key in seen:
                        continue
                    seen.add(key)

                    node_symbol = (
                        normalize_text(node.get("approvedSymbol"))
                        if isinstance(node, dict)
                        else ""
                    )

                    edges.append(
                        {
                            "target_id": target_id,
                            "target_symbol": node_symbol or target_symbol,
                            "disease_id": resolved["disease_id"],
                            "disease_name": resolved["disease_name"],
                            "mondo_id": resolved.get("mondo_id", ""),
                            "association_score": row.get("score"),
                            "evidence_type": evidence_type,
                            "source_name": "opentargets",
                            "source_record_id": f"{target_id}:{resolved['disease_id']}",
                            "retrieved_at": utcnow_iso(),
                        }
                    )

                fetched += len(rows)
                index += 1

    await asyncio.gather(
        *(worker(symbol, target_id) for symbol, target_id in sorted(target_ids.items()))
    )
    return edges


async def run(limit: Optional[int], concurrency: int, page_size: int) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    drugs = load_local_drugs(limit=limit)
    disease_lookup = load_local_disease_lookup()
    target_symbols: Set[str] = set()
    for drug in drugs:
        for symbol in drug.get("targets", []) or []:
            clean = normalize_text(symbol).upper()
            if clean:
                target_symbols.add(clean)

    async with httpx.AsyncClient(
        timeout=60.0, headers={"Accept": "application/json"}
    ) as client:
        drug_target_edges, target_ids = await fetch_drug_target_edges(
            client, drugs=drugs, concurrency=concurrency
        )
        target_ids = await resolve_target_ids(
            client,
            symbols=target_symbols,
            existing=target_ids,
            concurrency=concurrency,
        )
        target_disease_edges = await fetch_target_disease_edges(
            client,
            target_ids=target_ids,
            disease_lookup=disease_lookup,
            page_size=page_size,
            concurrency=concurrency,
        )

    drug_target_path = RAW_DIR / "drug_target_edges.jsonl"
    target_disease_path = RAW_DIR / "target_disease_edges.jsonl"
    drug_snapshot, drug_count = write_jsonl_with_snapshot(
        drug_target_path, drug_target_edges
    )
    disease_snapshot, disease_count = write_jsonl_with_snapshot(
        target_disease_path, target_disease_edges
    )

    checkpoint = {
        "source_name": "opentargets",
        "retrieved_at": utcnow_iso(),
        "input_drug_count": len(drugs),
        "resolved_target_count": len(target_ids),
        "drug_target_edges": {
            "count": drug_count,
            "output_path": str(drug_target_path),
            "snapshot_path": str(drug_snapshot),
        },
        "target_disease_edges": {
            "count": disease_count,
            "output_path": str(target_disease_path),
            "snapshot_path": str(disease_snapshot),
        },
    }
    write_checkpoint(checkpoint)
    return checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Open Targets raw edges")
    parser.add_argument("--limit", type=int, default=None, help="Limit local drugs")
    parser.add_argument(
        "--concurrency", type=int, default=4, help="Concurrent GraphQL requests"
    )
    parser.add_argument(
        "--page-size", type=int, default=200, help="Target-disease page size"
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    summary = asyncio.run(
        run(limit=args.limit, concurrency=args.concurrency, page_size=args.page_size)
    )
    LOGGER.info(
        "Open Targets extraction complete: %s drug-target, %s target-disease",
        summary["drug_target_edges"]["count"],
        summary["target_disease_edges"]["count"],
    )


if __name__ == "__main__":
    main()
