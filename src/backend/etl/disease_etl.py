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


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_wrapped_json(path: Path, key: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get(key, [])
    return payload


def normalize_name(value: str) -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"\([^)]*\)", " ", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?%?\b", " ", normalized)
    normalized = normalized.replace("/", " ")
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalized_variants(value: str) -> set[str]:
    base = normalize_name(value)
    variants = {base}
    for suffix in COMMON_SUFFIXES:
        if base.endswith(suffix):
            variants.add(base[: -len(suffix)].strip())
    return {variant for variant in variants if variant}


def slugify_disease_id(value: str) -> str:
    slug = normalize_name(value).replace(" ", "_")
    return slug or "unknown_disease"


def strip_html(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    stripped = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", stripped).strip()


def normalize_identifier(value: Optional[str], prefix_hint: Optional[str] = None) -> Optional[str]:
    if not value:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    upper = raw.upper()
    if upper.startswith("MONDO:"):
        digits = re.sub(r"\D", "", upper)
        return f"MONDO:{digits.zfill(7)}" if digits else None
    if upper.startswith("HTTP://PURL.OBO") or upper.startswith("HTTPS://PURL.OBO"):
        if "MONDO_" in upper:
            digits = re.sub(r"\D", "", upper.rsplit("MONDO_", 1)[-1])
            return f"MONDO:{digits.zfill(7)}" if digits else None
    if upper.startswith(("ORPHANET:", "ORPHA:")):
        digits = re.sub(r"\D", "", upper)
        return f"ORPHA:{digits}" if digits else None
    if upper.startswith("DOID:"):
        return upper
    if upper.startswith("MESH:"):
        return f"MESH:{upper.split(':', 1)[1]}"
    if upper.startswith("EFO:"):
        return upper

    hint = (prefix_hint or "").upper()
    digits = re.sub(r"\D", "", raw)
    if hint == "MONDO" and digits:
        return f"MONDO:{digits.zfill(7)}"
    if hint in {"ORPHANET", "ORPHA"} and digits:
        return f"ORPHA:{digits}"
    if hint == "DOID" and digits:
        return f"DOID:{digits}"
    if hint == "MESH":
        return f"MESH:{raw.upper()}"
    if hint == "EFO":
        return f"EFO:{raw.upper()}"

    return raw


def first_label(entries: Any) -> Optional[str]:
    if not isinstance(entries, list):
        return None
    english = next(
        (
            entry.get("label")
            for entry in entries
            if isinstance(entry, dict) and entry.get("lang") == "en" and entry.get("label")
        ),
        None,
    )
    if english:
        return english
    return next(
        (
            entry.get("label")
            for entry in entries
            if isinstance(entry, dict) and entry.get("label")
        ),
        None,
    )


def extract_synonym_labels(entries: Any) -> list[str]:
    if not isinstance(entries, list):
        return []
    labels: list[str] = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("label"):
            labels.append(entry["label"])
    return labels


def parse_orphanet_alignments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    disorders = []
    for root in payload.get("JDBOR", []):
        for disorder_list in root.get("DisorderList", []):
            disorders.extend(disorder_list.get("Disorder", []))

    for disorder in disorders:
        name = first_label(disorder.get("Name"))
        if not name:
            continue

        flag_labels = []
        for flag_list in disorder.get("DisorderFlagList", []):
            for flag in flag_list.get("DisorderFlag", []):
                label = flag.get("Label") or ""
                if label:
                    flag_labels.append(label.lower())
        if any("obsolete" in label or "inactive" in label for label in flag_labels):
            continue

        synonyms = []
        for synonym_list in disorder.get("SynonymList", []):
            synonyms.extend(extract_synonym_labels(synonym_list.get("Synonym", [])))

        external_refs: dict[str, str] = {}
        for ref_list in disorder.get("ExternalReferenceList", []):
            for ref in ref_list.get("ExternalReference", []):
                source = str(ref.get("Source") or "").upper()
                reference = ref.get("Reference")
                if not source or not reference:
                    continue
                external_refs[source] = str(reference)

        definition = None
        for summary_list in disorder.get("SummaryInformationList", []):
            for summary in summary_list.get("SummaryInformation", []):
                for text_list in summary.get("TextSectionList", []):
                    for text_section in text_list.get("TextSection", []):
                        definition_type = None
                        for type_info in text_section.get("TextSectionType", []):
                            definition_type = first_label(type_info.get("Name"))
                        if definition_type == "Definition":
                            definition = strip_html(text_section.get("Contents"))
                            break
                    if definition:
                        break
                if definition:
                    break
            if definition:
                break

        records.append(
            {
                "canonical_name": name,
                "synonyms": sorted({syn for syn in synonyms if syn}),
                "orphanet_id": normalize_identifier(disorder.get("OrphaCode"), "ORPHA"),
                "mondo_id": normalize_identifier(external_refs.get("MONDO"), "MONDO"),
                "doid_id": normalize_identifier(external_refs.get("DOID"), "DOID"),
                "mesh_id": normalize_identifier(external_refs.get("MESH"), "MESH"),
                "icd10_code": external_refs.get("ICD-10"),
                "definition": definition,
                "orphan_flag": True,
                "source": "orphanet",
            }
        )

    return records


def parse_mondo_obographs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for graph in payload.get("graphs", []):
        for node in graph.get("nodes", []):
            node_id = str(node.get("id") or "")
            if "MONDO_" not in node_id and not node_id.startswith("MONDO:"):
                continue

            meta = node.get("meta") or {}
            if meta.get("deprecated") or meta.get("obsolete"):
                continue

            mondo_id = normalize_identifier(node_id, "MONDO")
            canonical_name = node.get("lbl")
            if not canonical_name or not mondo_id:
                continue

            synonyms = sorted(
                {
                    str(item.get("val")).strip()
                    for item in meta.get("synonyms", [])
                    if isinstance(item, dict) and item.get("val")
                }
            )

            orphanet_id = None
            doid_id = None
            mesh_id = None
            efo_id = None
            for xref in meta.get("xrefs", []):
                value = xref.get("val") if isinstance(xref, dict) else xref
                value = str(value or "")
                upper = value.upper()
                if upper.startswith(("ORPHANET:", "ORPHA:")) and orphanet_id is None:
                    orphanet_id = normalize_identifier(value, "ORPHA")
                elif upper.startswith("DOID:") and doid_id is None:
                    doid_id = normalize_identifier(value, "DOID")
                elif upper.startswith("MESH:") and mesh_id is None:
                    mesh_id = normalize_identifier(value, "MESH")
                elif upper.startswith("EFO:") and efo_id is None:
                    efo_id = normalize_identifier(value, "EFO")

            definition = meta.get("definition")
            if isinstance(definition, dict):
                definition = definition.get("val")
            elif isinstance(definition, list) and definition:
                definition = definition[0].get("val")

            records.append(
                {
                    "canonical_name": canonical_name,
                    "synonyms": synonyms,
                    "orphanet_id": orphanet_id,
                    "mondo_id": mondo_id,
                    "doid_id": doid_id,
                    "mesh_id": mesh_id,
                    "efo_id": efo_id,
                    "icd10_code": None,
                    "definition": strip_html(definition),
                    "orphan_flag": bool(orphanet_id),
                    "source": "mondo",
                }
            )

    return records


def read_location_bytes(location: str) -> bytes:
    parsed = urlparse(location)
    if parsed.scheme in {"http", "https"}:
        with urlopen(location) as response:  # nosec - official public data sources only
            return response.read()
    return Path(location).read_bytes()


def load_json_like_location(location: Optional[str]) -> Any:
    if not location:
        return None

    raw = read_location_bytes(location)
    lower = location.lower()

    if lower.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            for member in archive.getmembers():
                if member.isfile() and member.name.endswith(".json"):
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        continue
                    return json.loads(extracted.read().decode("utf-8"))
            raise ValueError(f"No JSON payload found in tarball: {location}")

    if lower.endswith(".gz"):
        import gzip

        return json.loads(gzip.decompress(raw).decode("utf-8"))

    return json.loads(raw.decode("utf-8"))


def load_orphanet_records(location: Optional[str]) -> list[dict[str, Any]]:
    payload = load_json_like_location(location)
    if payload is None:
        return []
    return parse_orphanet_alignments(payload)


def load_mondo_records(location: Optional[str]) -> list[dict[str, Any]]:
    payload = load_json_like_location(location)
    if payload is None:
        return []
    return parse_mondo_obographs(payload)


def load_chembl_indication_map(location: Optional[str]) -> dict[str, list[dict[str, Any]]]:
    payload = load_json_like_location(location)
    if payload is None:
        return {}

    if isinstance(payload, dict) and all(isinstance(value, list) for value in payload.values()):
        return payload

    mapping: dict[str, list[dict[str, Any]]] = defaultdict(list)
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return {}

    for item in items:
        if not isinstance(item, dict):
            continue
        chembl_id = item.get("chembl_id") or item.get("molecule_chembl_id")
        indications = item.get("indications") or item.get("drug_indications") or []
        if chembl_id and isinstance(indications, list):
            mapping[str(chembl_id)] = indications

    return dict(mapping)


def build_drug_lookup(drugs: list[dict[str, Any]]) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = defaultdict(list)

    def add(key: str, drug_id: str) -> None:
        if key and drug_id not in lookup[key]:
            lookup[key].append(drug_id)

    for drug in drugs:
        drug_id = drug.get("id")
        if not drug_id:
            continue

        names = [drug_id, drug.get("name", "")]
        names.extend(drug.get("synonyms") or [])
        for name in names:
            for variant in normalized_variants(str(name)):
                add(variant, drug_id)

    return lookup


def resolve_drug_id(source_name: str, lookup: dict[str, list[str]]) -> str | None:
    source_variants = normalized_variants(source_name)

    for variant in list(source_variants):
        alias = ALIASES.get(variant)
        if alias:
            return alias

    for variant in source_variants:
        matches = lookup.get(variant, [])
        if len(matches) == 1:
            return matches[0]

    return None


def infer_body_region(name: str) -> str:
    normalized = normalize_name(name)
    for region, keywords in BODY_REGION_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return region
    return "systemic_multiorgan"


def evidence_level_from_phase(value: Any) -> str:
    try:
        phase = int(float(value or 0))
    except (TypeError, ValueError):
        return "unknown"
    return EVIDENCE_LEVEL_BY_PHASE.get(phase, "unknown")


def build_disease_index(diseases: list[dict[str, Any]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for disease in diseases:
        disease_id = disease["id"]
        for name in [disease.get("canonical_name", ""), *disease.get("synonyms", [])]:
            for variant in normalized_variants(str(name)):
                index.setdefault(f"name:{variant}", disease_id)
        for field in ("orphanet_id", "mondo_id", "doid_id", "icd10_code", "mesh_id", "efo_id"):
            value = disease.get(field)
            if value:
                index.setdefault(f"id:{str(value).upper()}", disease_id)
    return index


def external_record_keys(record: dict[str, Any]) -> set[str]:
    keys = set()
    for name in [record.get("canonical_name", ""), *(record.get("synonyms") or [])]:
        for variant in normalized_variants(str(name)):
            keys.add(f"name:{variant}")
    for field in ("orphanet_id", "mondo_id", "doid_id", "mesh_id", "efo_id", "icd10_code"):
        value = record.get(field)
        if value:
            keys.add(f"id:{str(value).upper()}")
    return keys


def merge_disease_record(
    disease: dict[str, Any],
    record: dict[str, Any],
    allow_orphan_promotion: bool = False,
) -> None:
    disease["synonyms"] = sorted(
        {
            *disease.get("synonyms", []),
            *(record.get("synonyms") or []),
        }
    )
    for field in ("orphanet_id", "mondo_id", "doid_id", "icd10_code", "mesh_id", "efo_id"):
        if record.get(field) and not disease.get(field):
            disease[field] = record[field]

    if record.get("orphan_flag") and allow_orphan_promotion:
        disease["orphan_flag"] = True
        categories = set(disease.get("categories", []))
        categories.add("orphan")
        disease["categories"] = sorted(categories)
        if disease.get("prevalence_tier") in (None, "", "unknown"):
            disease["prevalence_tier"] = "rare"

    if record.get("definition") and not disease.get("mechanism_summary"):
        disease["mechanism_summary"] = record["definition"]
        disease["mechanism_citation"] = record.get("source")


def create_external_disease(record: dict[str, Any]) -> dict[str, Any]:
    categories = ["orphan"] if record.get("orphan_flag") else []
    return {
        "id": slugify_disease_id(record["canonical_name"]),
        "canonical_name": record["canonical_name"],
        "synonyms": sorted(set(record.get("synonyms") or [])),
        "body_region": infer_body_region(record["canonical_name"]),
        "anatomy_nodes": [],
        "categories": categories,
        "orphan_flag": bool(record.get("orphan_flag")),
        "prevalence_tier": "rare" if record.get("orphan_flag") else "unknown",
        "prevalence_count": None,
        "evidence_level": "unknown",
        "mechanism_summary": record.get("definition"),
        "mechanism_citation": record.get("source"),
        "target_count": 0,
        "approved_drug_count": 0,
        "clinical_drug_count": 0,
        "orphanet_id": record.get("orphanet_id"),
        "mondo_id": record.get("mondo_id"),
        "doid_id": record.get("doid_id"),
        "icd10_code": record.get("icd10_code"),
        "mesh_id": record.get("mesh_id"),
        "efo_id": record.get("efo_id"),
    }


def build_external_record_index(
    orphanet_records: Iterable[dict[str, Any]],
    mondo_records: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    merged_records: list[dict[str, Any]] = []
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)

    by_name: dict[str, dict[str, Any]] = {}
    for source_record in [*orphanet_records, *mondo_records]:
        name_key = normalize_name(source_record.get("canonical_name", ""))
        if not name_key:
            continue
        target = by_name.get(name_key)
        if target is None:
            target = copy.deepcopy(source_record)
            target["synonyms"] = sorted(set(target.get("synonyms") or []))
            by_name[name_key] = target
            merged_records.append(target)
        else:
            target["synonyms"] = sorted(
                {
                    *target.get("synonyms", []),
                    *(source_record.get("synonyms") or []),
                }
            )
            for field in ("orphanet_id", "mondo_id", "doid_id", "mesh_id", "efo_id", "icd10_code", "definition"):
                if source_record.get(field) and not target.get(field):
                    target[field] = source_record[field]
            target["orphan_flag"] = bool(target.get("orphan_flag") or source_record.get("orphan_flag"))
            target["source"] = ",".join(sorted(set(str(target.get("source", "")).split(",")) | {source_record.get("source", "")}))

    for record in merged_records:
        for key in external_record_keys(record):
            index[key].append(record)

    return merged_records, index


async def fetch_live_chembl_indication_map(
    drugs: list[dict[str, Any]],
    limit: Optional[int] = None,
    rate_limit_per_sec: float = 1.0,
) -> dict[str, list[dict[str, Any]]]:
    chembl_ids = []
    for drug in drugs:
        chembl_id = drug.get("chembl_id")
        if chembl_id and chembl_id not in chembl_ids:
            chembl_ids.append(chembl_id)
    if limit is not None:
        chembl_ids = chembl_ids[:limit]

    client = ChEMBLClient(rate_limit_per_sec=rate_limit_per_sec)
    results: dict[str, list[dict[str, Any]]] = {}
    try:
        for chembl_id in chembl_ids:
            indications = await client.get_drug_indications(chembl_id)
            if indications:
                results[chembl_id] = indications
    finally:
        await client.close()

    return results


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
