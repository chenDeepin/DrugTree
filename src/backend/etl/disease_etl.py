#!/usr/bin/env python3
"""
Build canonical disease and disease->drug edge files for DrugTree.

The ETL now has a dedicated curated seed file and optional structured-source
enrichment from:
- Orphadata / Orphanet rare-disease alignments
- MONDO obographs JSON
- ChEMBL drug indication data (snapshot or live)

The canonical outputs remain:
- data/diseases.json
- data/disease_drug_edges.json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import io
import json
import re
import sys
import tarfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "src" / "backend"
for _path in (PROJECT_ROOT, BACKEND_ROOT):
    path_str = str(_path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

try:
    from .chembl_client import ChEMBLClient
except ImportError:  # pragma: no cover - direct script fallback
    from chembl_client import ChEMBLClient


DEFAULT_SEED_DISEASES_FILE = PROJECT_ROOT / "data" / "seeds" / "diseases.seed.json"
LEGACY_FRONTEND_SEED_FILE = PROJECT_ROOT / "src" / "frontend" / "data" / "diseases.json"
DRUGS_FILE = PROJECT_ROOT / "data" / "drugs.json"
OUTPUT_DISEASES_FILE = PROJECT_ROOT / "data" / "diseases.json"
OUTPUT_EDGES_FILE = PROJECT_ROOT / "data" / "disease_drug_edges.json"
REPORTS_FILE = PROJECT_ROOT / "data" / "reports" / "disease_etl_report.json"

COMMON_SUFFIXES = (
    " hydrochloride",
    " hydrobromide",
    " sodium",
    " potassium",
    " succinate",
    " mesylate",
    " maleate",
    " acetate",
    " bromide",
    " hydrate",
    " phosphate",
    " sulfate",
    " sulphate",
    " tartrate",
)

ALIASES = {
    "imatinib": "imatinib-mesylate",
    "losartan": "losartan-potassium",
    "metformin": "metformin-hydrochloride",
    "methotrexate": "methotrexate-sodium",
    "metoprolol": "metoprolol-succinate",
    "montelukast": "montelukast-sodium",
    "tamsulosin": "tamsulosin-hydrochloride",
    "tiotropium": "tiotropium-bromide-hydrate",
}

BODY_REGION_KEYWORDS = {
    "brain_cns": [
        "brain",
        "neuro",
        "gli",
        "alzheimer",
        "parkinson",
        "epilep",
        "dementia",
        "cns",
        "leukodystrophy",
        "astrocy",
    ],
    "eye_ear": ["glaucoma", "retin", "ocular", "uveal", "eye", "ear"],
    "lung_respiratory": ["lung", "respir", "asthma", "copd", "bronch", "pulmonary"],
    "heart_vascular": ["heart", "cardio", "vascular", "hypertension", "cholesterol"],
    "blood_immune": ["leukemia", "lymphoma", "myelo", "blood", "immune", "hemat"],
    "stomach_upper_gi": ["reflux", "esoph", "stomach", "ulcer", "gastric", "duoden"],
    "intestine_colorectal": ["crohn", "colitis", "intestinal", "colon", "bowel", "rect"],
    "liver_biliary_pancreas": ["liver", "hepatic", "biliary", "pancrea"],
    "endocrine_metabolic": ["diabetes", "thyroid", "metabolic", "endocrine", "obesity"],
    "kidney_urinary": ["renal", "kidney", "urinary", "bladder"],
    "reproductive_breast": ["ovary", "uter", "breast", "prostate", "reproductive", "cervix"],
    "bone_joint_muscle": ["bone", "joint", "muscle", "skeletal", "arthritis"],
    "skin": ["skin", "derm", "psoriasis", "eczema", "cutaneous", "melanoma"],
}

EVIDENCE_LEVEL_BY_PHASE = {
    4: "approved",
    3: "phase_iii",
    2: "phase_ii",
    1: "phase_i",
    0: "unknown",
}



try:
    from .disease_etl_helpers import *
    from .disease_source_loaders import *
    from .disease_source_loaders import fetch_live_chembl_indication_map as _fetch_live_chembl_indication_map
except ImportError:  # pragma: no cover - direct script fallback
    from src.backend.etl.disease_etl_helpers import *
    from src.backend.etl.disease_source_loaders import *
    from src.backend.etl.disease_source_loaders import fetch_live_chembl_indication_map as _fetch_live_chembl_indication_map


async def fetch_live_chembl_indication_map(
    drugs: list[dict[str, Any]],
    limit: Optional[int] = None,
    rate_limit_per_sec: float = 1.0,
) -> dict[str, list[dict[str, Any]]]:
    return await _fetch_live_chembl_indication_map(
        drugs=drugs,
        limit=limit,
        rate_limit_per_sec=rate_limit_per_sec,
        client_factory=ChEMBLClient,
    )


def choose_seed_file(path_override: Optional[str]) -> Path:
    if path_override:
        return Path(path_override)

    if DEFAULT_SEED_DISEASES_FILE.exists():
        return DEFAULT_SEED_DISEASES_FILE

    if LEGACY_FRONTEND_SEED_FILE.exists():
        payload = json.loads(LEGACY_FRONTEND_SEED_FILE.read_text(encoding="utf-8"))
        diseases = payload.get("diseases", []) if isinstance(payload, dict) else payload
        if any("drugs" in disease for disease in diseases):
            return LEGACY_FRONTEND_SEED_FILE

    raise FileNotFoundError("No disease seed file with curated drug links is available")


def build_outputs(
    seed_diseases: list[dict[str, Any]],
    drugs: list[dict[str, Any]],
    orphanet_records: Optional[list[dict[str, Any]]] = None,
    mondo_records: Optional[list[dict[str, Any]]] = None,
    chembl_indication_map: Optional[dict[str, list[dict[str, Any]]]] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    orphanet_records = orphanet_records or []
    mondo_records = mondo_records or []
    chembl_indication_map = chembl_indication_map or {}

    lookup = build_drug_lookup(drugs)
    drugs_by_id = {drug["id"]: drug for drug in drugs if drug.get("id")}
    drugs_by_chembl = {
        str(drug.get("chembl_id")): drug["id"]
        for drug in drugs
        if drug.get("id") and drug.get("chembl_id")
    }

    canonical_diseases = [copy.deepcopy(disease) for disease in seed_diseases]
    for disease in canonical_diseases:
        disease.setdefault("orphanet_id", None)
        disease.setdefault("mondo_id", None)
        disease.setdefault("doid_id", None)
        disease.setdefault("icd10_code", None)
        disease.setdefault("mesh_id", None)
        disease.setdefault("efo_id", None)
        disease.setdefault("mechanism_summary", None)
        disease.setdefault("mechanism_citation", None)

    disease_index = build_disease_index(canonical_diseases)
    _, external_index = build_external_record_index(orphanet_records, mondo_records)

    source_matches = 0
    for disease in canonical_diseases:
        matched_records = []
        for key in external_record_keys(disease):
            matched_records.extend(external_index.get(key, []))
        deduped_records = []
        seen_names = set()
        for record in matched_records:
            name_key = normalize_name(record["canonical_name"])
            if name_key in seen_names:
                continue
            seen_names.add(name_key)
            deduped_records.append(record)
        for record in deduped_records:
            merge_disease_record(disease, record, allow_orphan_promotion=False)
            source_matches += 1
        disease_index = build_disease_index(canonical_diseases)

    edges: list[dict[str, Any]] = []
    matched_by_disease: dict[str, list[str]] = defaultdict(list)
    unmatched_seed_links: dict[str, list[str]] = defaultdict(list)
    unmatched_chembl_indications: list[dict[str, Any]] = []
    new_external_diseases = 0

    def add_edge(
        disease_id: str,
        drug_id: str,
        indication_type: str,
        evidence_source: str,
        evidence_level: str,
    ) -> None:
        if drug_id in matched_by_disease[disease_id]:
            return
        matched_by_disease[disease_id].append(drug_id)
        edges.append(
            {
                "disease_id": disease_id,
                "drug_id": drug_id,
                "indication_type": indication_type,
                "evidence_source": evidence_source,
                "evidence_level": evidence_level,
            }
        )

    for disease in canonical_diseases:
        disease_id = disease["id"]
        for seed_name in disease.get("drugs", []):
            resolved_id = resolve_drug_id(seed_name, lookup)
            if not resolved_id or resolved_id not in drugs_by_id:
                unmatched_seed_links[disease_id].append(seed_name)
                continue
            add_edge(
                disease_id=disease_id,
                drug_id=resolved_id,
                indication_type="primary",
                evidence_source="curated_seed",
                evidence_level=disease.get("evidence_level", "unknown"),
            )

    for chembl_id, indications in chembl_indication_map.items():
        drug_id = drugs_by_chembl.get(str(chembl_id))
        if not drug_id:
            continue

        for indication in indications:
            keys = set()
            disease_name = indication.get("disease_name") or ""
            disease_id_value = indication.get("disease_id")
            if disease_name:
                for variant in normalized_variants(disease_name):
                    keys.add(f"name:{variant}")
            if disease_id_value:
                keys.add(f"id:{str(disease_id_value).upper()}")

            canonical_disease_id = next(
                (disease_index[key] for key in keys if key in disease_index),
                None,
            )

            matched_external_record = next(
                (
                    record
                    for key in keys
                    for record in external_index.get(key, [])
                ),
                None,
            )

            if canonical_disease_id is None and matched_external_record:
                new_disease = create_external_disease(matched_external_record)
                if new_disease["id"] in {d["id"] for d in canonical_diseases}:
                    suffix = 2
                    while f"{new_disease['id']}_{suffix}" in {d['id'] for d in canonical_diseases}:
                        suffix += 1
                    new_disease["id"] = f"{new_disease['id']}_{suffix}"
                canonical_diseases.append(new_disease)
                canonical_disease_id = new_disease["id"]
                disease_index = build_disease_index(canonical_diseases)
                new_external_diseases += 1

            if canonical_disease_id is None:
                unmatched_chembl_indications.append(
                    {
                        "chembl_id": chembl_id,
                        "drug_id": drug_id,
                        "disease_id": disease_id_value,
                        "disease_name": disease_name,
                    }
                )
                continue

            add_edge(
                disease_id=canonical_disease_id,
                drug_id=drug_id,
                indication_type=indication.get("indication_type", "primary"),
                evidence_source="chembl",
                evidence_level=evidence_level_from_phase(indication.get("phase")),
            )

    for disease in canonical_diseases:
        linked_ids = matched_by_disease.get(disease["id"], [])
        linked_drugs = [drugs_by_id[drug_id] for drug_id in linked_ids if drug_id in drugs_by_id]
        approved_count = sum(1 for drug in linked_drugs if str(drug.get("phase", "")).upper() == "IV")
        clinical_count = sum(1 for drug in linked_drugs if str(drug.get("phase", "")).upper() not in {"", "IV"})
        disease["approved_drug_count"] = approved_count
        disease["clinical_drug_count"] = clinical_count
        disease["drugs"] = linked_ids
        if disease.get("orphan_flag") and "orphan" not in disease.get("categories", []):
            disease["categories"] = sorted({*disease.get("categories", []), "orphan"})

    generated_at = utcnow_iso()
    diseases_payload = {
        "diseases": [
            {key: value for key, value in disease.items() if key != "drugs"}
            for disease in canonical_diseases
        ],
        "metadata": {
            "generated_at": generated_at,
            "source_seed_file": str(DEFAULT_SEED_DISEASES_FILE.relative_to(PROJECT_ROOT))
            if DEFAULT_SEED_DISEASES_FILE.exists()
            else None,
            "seed_disease_count": len(seed_diseases),
            "canonical_disease_count": len(canonical_diseases),
            "orphanet_record_count": len(orphanet_records),
            "mondo_record_count": len(mondo_records),
            "chembl_indication_drug_count": len(chembl_indication_map),
            "resolved_edge_count": len(edges),
            "source_match_count": source_matches,
            "new_external_disease_count": new_external_diseases,
            "unmatched_seed_links": sum(len(values) for values in unmatched_seed_links.values()),
            "unmatched_seed_links_by_disease": unmatched_seed_links,
            "unmatched_chembl_indication_count": len(unmatched_chembl_indications),
        },
    }
    edges_payload = {
        "edges": edges,
        "metadata": {
            "generated_at": generated_at,
            "seed_edge_count": sum(
                1 for edge in edges if edge["evidence_source"] == "curated_seed"
            ),
            "chembl_edge_count": sum(
                1 for edge in edges if edge["evidence_source"] == "chembl"
            ),
        },
    }
    return diseases_payload, edges_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build canonical disease data files.")
    parser.add_argument(
        "--seed",
        default=None,
        help="Path to the curated disease seed JSON (defaults to data/seeds/diseases.seed.json)",
    )
    parser.add_argument(
        "--drugs",
        type=Path,
        default=DRUGS_FILE,
        help="Path to canonical drugs JSON",
    )
    parser.add_argument(
        "--orphanet-alignments",
        default=None,
        help="Path or URL to Orphadata/Orphanet alignments JSON or JSON tarball",
    )
    parser.add_argument(
        "--mondo-json",
        default=None,
        help="Path or URL to MONDO obographs JSON",
    )
    parser.add_argument(
        "--chembl-indications",
        default=None,
        help="Path to a cached ChEMBL indication snapshot",
    )
    parser.add_argument(
        "--chembl-live-limit",
        type=int,
        default=0,
        help="Fetch live ChEMBL indications for the first N atlas drugs with chembl_id",
    )
    parser.add_argument(
        "--chembl-rate-limit",
        type=float,
        default=1.0,
        help="Live ChEMBL request rate per second",
    )
    parser.add_argument(
        "--out-diseases",
        type=Path,
        default=OUTPUT_DISEASES_FILE,
        help="Output path for canonical diseases JSON",
    )
    parser.add_argument(
        "--out-edges",
        type=Path,
        default=OUTPUT_EDGES_FILE,
        help="Output path for disease-drug edges JSON",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPORTS_FILE,
        help="Output path for ETL report JSON",
    )
    args = parser.parse_args()

    seed_path = choose_seed_file(args.seed)
    seed_diseases = load_wrapped_json(seed_path, "diseases")
    drugs = load_wrapped_json(args.drugs, "drugs")
    orphanet_records = load_orphanet_records(args.orphanet_alignments)
    mondo_records = load_mondo_records(args.mondo_json)
    chembl_indication_map = load_chembl_indication_map(args.chembl_indications)

    if args.chembl_live_limit:
        chembl_indication_map.update(
            asyncio.run(
                fetch_live_chembl_indication_map(
                    drugs=drugs,
                    limit=args.chembl_live_limit,
                    rate_limit_per_sec=args.chembl_rate_limit,
                )
            )
        )

    diseases_payload, edges_payload = build_outputs(
        seed_diseases=seed_diseases,
        drugs=drugs,
        orphanet_records=orphanet_records,
        mondo_records=mondo_records,
        chembl_indication_map=chembl_indication_map,
    )

    args.out_diseases.parent.mkdir(parents=True, exist_ok=True)
    args.out_edges.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.out_diseases.write_text(
        json.dumps(diseases_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.out_edges.write_text(
        json.dumps(edges_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.report.write_text(
        json.dumps(
            {
                "generated_at": utcnow_iso(),
                "seed_file": str(seed_path),
                "orphanet_alignments": args.orphanet_alignments,
                "mondo_json": args.mondo_json,
                "chembl_indications": args.chembl_indications,
                "chembl_live_limit": args.chembl_live_limit,
                "disease_count": len(diseases_payload["diseases"]),
                "edge_count": len(edges_payload["edges"]),
                "diseases_metadata": diseases_payload["metadata"],
                "edges_metadata": edges_payload["metadata"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
