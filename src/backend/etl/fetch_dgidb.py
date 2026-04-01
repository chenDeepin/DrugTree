#!/usr/bin/env python3
"""Fetch DGIdb drug-gene interactions into raw JSONL with graceful degradation."""

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
RAW_DIR = DATA_DIR / "raw" / "dgidb"
CHECKPOINT_FILE = DATA_DIR / "checkpoints" / "fetch_dgidb_checkpoint.json"
DRUGS_FILE = DATA_DIR / "drugs.json"

GRAPHQL_URL = "https://www.dgidb.org/api/graphql"
GRAPHQL_FALLBACK_URL = "https://dgidb.org/api/graphql"
INTERACTIONS_URL = "https://www.dgidb.org/api/v2/interactions.json"

DRUG_INTERACTIONS_QUERY = """
query DrugInteractions($names: [String!]!) {
  drugs(names: $names) {
    matchedTerms {
      searchTerm
      drugName
      interactions {
        interactionId
        interactionTypes {
          type
          name
        }
        interactionAttributes {
          name
        }
        sources {
          sourceDbName
          sourceDbVersion
        }
        gene {
          id
          name
          symbol
          conceptId
          entrezId
        }
      }
      matchedDrug {
        name
        interactions {
          interactionId
          interactionTypes {
            type
            name
          }
          interactionAttributes {
            name
          }
          sources {
            sourceDbName
            sourceDbVersion
          }
          gene {
            id
            name
            symbol
            conceptId
            entrezId
          }
        }
      }
    }
    unmatchedTerms
    ambiguousTerms {
      searchTerm
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


def normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        output: List[str] = []
        for item in value:
            text = normalize_text(item)
            if text and text not in output:
                output.append(text)
        return output
    text = normalize_text(value)
    return [text] if text else []


def normalize_object_list(value: Any, field_names: Iterable[str]) -> List[str]:
    if value is None:
        return []

    items = value if isinstance(value, list) else [value]
    output: List[str] = []
    for item in items:
        if isinstance(item, dict):
            text = ""
            for field_name in field_names:
                text = normalize_text(item.get(field_name))
                if text:
                    break
        else:
            text = normalize_text(item)
        if text and text not in output:
            output.append(text)
    return output


def collect_candidate_sections(payload: Any) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    queue: List[Any] = [payload]

    while queue:
        current = queue.pop(0)
        if not isinstance(current, dict):
            continue

        for section in [current.get("matchedTerms"), current.get("matched_terms")]:
            if isinstance(section, list):
                sections.extend(item for item in section if isinstance(item, dict))

        for nested_key in ("data", "drugs", "genes"):
            nested = current.get(nested_key)
            if isinstance(nested, dict):
                queue.append(nested)

    return sections


def payload_looks_usable(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False

    if collect_candidate_sections(payload):
        return True

    queue: List[Any] = [payload]
    while queue:
        current = queue.pop(0)
        if not isinstance(current, dict):
            continue
        if any(
            key in current
            for key in (
                "matchedTerms",
                "matched_terms",
                "unmatchedTerms",
                "unmatched_terms",
                "ambiguousTerms",
                "ambiguous_terms",
            )
        ):
            return True
        for nested_key in ("data", "drugs", "genes"):
            nested = current.get(nested_key)
            if isinstance(nested, dict):
                queue.append(nested)

    return False


def load_local_drugs(limit: Optional[int] = None) -> List[Dict[str, str]]:
    if not DRUGS_FILE.exists():
        LOGGER.warning("Canonical drugs file missing: %s", DRUGS_FILE)
        return []

    payload = json.loads(DRUGS_FILE.read_text(encoding="utf-8"))
    drugs = payload.get("drugs", []) if isinstance(payload, dict) else payload
    items: List[Dict[str, str]] = []
    for drug in drugs:
        if not isinstance(drug, dict):
            continue
        name = normalize_text(drug.get("name"))
        drug_id = normalize_text(drug.get("id"))
        if name:
            items.append({"drug_id": drug_id, "drug_name": name})

    if limit is not None and limit > 0:
        return items[:limit]
    return items


def write_json(path: Path, data: Dict[str, Any]) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    snapshot = path.with_name(f"{path.stem}_{timestamp_tag()}{path.suffix}")
    snapshot.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return snapshot


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


async def safe_get_json(
    client: httpx.AsyncClient,
    url: str,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        LOGGER.warning("DGIdb request failed for %s: %s", url, exc)
        return None

    content_type = normalize_text(response.headers.get("content-type")).lower()
    if "json" not in content_type:
        LOGGER.warning("DGIdb returned non-JSON payload for %s", url)
        return None

    try:
        return response.json()
    except ValueError as exc:
        LOGGER.warning("DGIdb JSON parse failed for %s: %s", url, exc)
        return None


async def safe_graphql_query(
    client: httpx.AsyncClient,
    query: str,
    variables: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    for url in (GRAPHQL_URL, GRAPHQL_FALLBACK_URL):
        try:
            response = await client.post(
                url, json={"query": query, "variables": variables}
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.warning("DGIdb GraphQL request failed for %s: %s", url, exc)
            continue

        if not isinstance(payload, dict):
            LOGGER.warning("DGIdb GraphQL returned unexpected payload type for %s", url)
            continue

        if payload.get("errors"):
            LOGGER.warning("DGIdb GraphQL error for %s: %s", url, payload["errors"][:1])
            continue

        data = payload.get("data")
        if isinstance(data, dict):
            return data

    return None


def parse_interaction_payload(
    payload: Any, drug: Dict[str, str]
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, Tuple[str, ...]]] = set()

    candidates = collect_candidate_sections(payload)

    for candidate in candidates:
        interactions: List[Dict[str, Any]] = []
        interaction_groups: List[Any] = [
            candidate.get("interactions"),
            candidate.get("matchedInteractions"),
        ]

        nested_nodes: List[Any] = []
        for nested_key in ("matchedDrug", "drug", "matchedGene", "gene"):
            nested = candidate.get(nested_key)
            if isinstance(nested, dict):
                nested_nodes.append(nested)
        if isinstance(candidate.get("drugs"), list):
            nested_nodes.extend(
                item for item in candidate.get("drugs", []) if isinstance(item, dict)
            )

        for nested in nested_nodes:
            interaction_groups.extend(
                [nested.get("interactions"), nested.get("matchedInteractions")]
            )

        for group in interaction_groups:
            if isinstance(group, list):
                interactions.extend(item for item in group if isinstance(item, dict))

        for interaction in interactions:
            gene_payload = interaction.get("gene")
            gene: Dict[str, Any] = (
                gene_payload if isinstance(gene_payload, dict) else {}
            )
            gene_name = (
                normalize_text(interaction.get("geneName"))
                or normalize_text(interaction.get("gene_name"))
                or normalize_text(interaction.get("geneClaimName"))
                or normalize_text(interaction.get("gene_claim_name"))
                or normalize_text(gene.get("name"))
                or normalize_text(gene.get("symbol"))
            )
            gene_symbol = (
                normalize_text(interaction.get("geneSymbol"))
                or normalize_text(interaction.get("gene_symbol"))
                or normalize_text(gene.get("symbol"))
                or gene_name
            ).upper()
            interaction_types = normalize_object_list(
                interaction.get("interactionTypes")
                or interaction.get("interaction_types"),
                ("type", "name", "interactionType"),
            )
            key = (drug["drug_id"], gene_symbol, tuple(sorted(interaction_types)))
            if key in seen:
                continue
            seen.add(key)
            interaction_attributes = normalize_object_list(
                interaction.get("interactionAttributes")
                or interaction.get("interaction_attributes"),
                ("name", "attribute", "value"),
            )
            sources = normalize_object_list(
                interaction.get("sources") or interaction.get("source_trust_levels"),
                ("sourceDbName", "source_db_name", "name"),
            )
            if not sources:
                claim_sources = [
                    claim.get("interactionClaimSource")
                    for claim in interaction.get("interactionClaims", []) or []
                    if isinstance(claim, dict)
                    and isinstance(claim.get("interactionClaimSource"), dict)
                ]
                sources = normalize_object_list(
                    claim_sources,
                    ("sourceDbName", "source_db_name", "name"),
                )
            records.append(
                {
                    "drug_name": drug["drug_name"],
                    "drug_id_local": drug["drug_id"],
                    "gene_name": gene_name or gene_symbol,
                    "gene_symbol": gene_symbol,
                    "interaction_types": interaction_types,
                    "interaction_attributes": interaction_attributes,
                    "sources": sources,
                    "dgidb_gene_id": normalize_text(
                        interaction.get("geneId")
                        or interaction.get("gene_id")
                        or gene.get("conceptId")
                        or gene.get("id")
                        or gene.get("entrezId")
                    ),
                    "source_name": "dgidb",
                    "source_record_id": normalize_text(
                        interaction.get("interactionId")
                        or interaction.get("interaction_id")
                        or interaction.get("id")
                    )
                    or f"{drug['drug_id']}:{gene_symbol}",
                    "retrieved_at": utcnow_iso(),
                }
            )
    return records


async def fetch_interaction_payload(
    client: httpx.AsyncClient,
    drug: Dict[str, str],
) -> Dict[str, Any]:
    payload = await safe_graphql_query(
        client,
        DRUG_INTERACTIONS_QUERY,
        {"names": [drug["drug_name"]]},
    )
    if payload_looks_usable(payload):
        return {"method": "graphql", "payload": payload, "errors": []}

    errors: List[str] = []
    if payload is None:
        errors.append("graphql_failed")
    else:
        errors.append("graphql_unusable")

    rest_payload = await safe_get_json(
        client, INTERACTIONS_URL, {"drugs": drug["drug_name"]}
    )
    if rest_payload is not None:
        return {"method": "rest", "payload": rest_payload, "errors": errors}

    errors.append("rest_failed")
    return {"method": None, "payload": None, "errors": errors}


async def run(limit: Optional[int], concurrency: int) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)

    drugs = load_local_drugs(limit=limit)
    responses: Dict[str, Any] = {}
    records: List[Dict[str, Any]] = []
    usable_payload_count = 0
    semaphore = asyncio.Semaphore(max(1, concurrency))
    responses_path = RAW_DIR / "api_responses.json"
    output_path = RAW_DIR / "drug_gene_interactions.jsonl"

    async with httpx.AsyncClient(
        timeout=45.0,
        headers={"Accept": "application/json"},
        follow_redirects=True,
    ) as client:

        async def worker(drug: Dict[str, str]) -> None:
            nonlocal usable_payload_count
            async with semaphore:
                try:
                    result = await fetch_interaction_payload(client, drug)
                    responses[drug["drug_name"]] = result
                    payload = result.get("payload")
                    if payload_looks_usable(payload):
                        usable_payload_count += 1
                        records.extend(parse_interaction_payload(payload, drug))
                except Exception as exc:
                    LOGGER.warning(
                        "DGIdb worker failed for %s: %s", drug["drug_name"], exc
                    )
                    responses[drug["drug_name"]] = {
                        "method": None,
                        "payload": None,
                        "errors": [f"worker_exception:{type(exc).__name__}"],
                    }

        await asyncio.gather(*(worker(drug) for drug in drugs))

    if usable_payload_count == 0:
        status = "preserved_previous_outputs"
    elif usable_payload_count == len(drugs):
        status = "success"
    else:
        status = "partial"

    checkpoint: Dict[str, Any] = {
        "source_name": "dgidb",
        "retrieved_at": utcnow_iso(),
        "status": status,
        "input_drug_count": len(drugs),
        "usable_payload_count": usable_payload_count,
        "record_count": len(records),
    }

    if status == "preserved_previous_outputs":
        if responses_path.exists():
            checkpoint["response_dump_path"] = str(responses_path)
        if output_path.exists():
            checkpoint["output_path"] = str(output_path)
        write_checkpoint(checkpoint)
        return checkpoint

    responses_snapshot = write_json(
        responses_path,
        {"source_name": "dgidb", "retrieved_at": utcnow_iso(), "responses": responses},
    )
    output_snapshot, record_count = write_jsonl_with_snapshot(output_path, records)

    checkpoint.update(
        {
            "record_count": record_count,
            "response_dump_path": str(responses_path),
            "response_snapshot_path": str(responses_snapshot),
            "output_path": str(output_path),
            "snapshot_path": str(output_snapshot),
        }
    )
    write_checkpoint(checkpoint)
    return checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch DGIdb drug-gene interactions")
    parser.add_argument("--limit", type=int, default=None, help="Limit local drugs")
    parser.add_argument(
        "--concurrency", type=int, default=6, help="Concurrent DGIdb requests"
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    summary = asyncio.run(run(limit=args.limit, concurrency=args.concurrency))
    LOGGER.info("DGIdb extraction complete: %s records", summary["record_count"])


if __name__ == "__main__":
    main()
