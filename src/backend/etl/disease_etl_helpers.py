"""Parsing and source-loading helpers for disease ETL."""

from __future__ import annotations

import copy
import io
import json
import re
import tarfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

try:
    from .chembl_client import ChEMBLClient
except ImportError:  # pragma: no cover - direct script fallback
    from src.backend.etl.chembl_client import ChEMBLClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]

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
