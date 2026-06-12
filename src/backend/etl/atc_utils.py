"""Shared ATC enrichment utilities."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ATC_CODE_PATTERN = re.compile(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
PLACEHOLDER_ATC_PATTERN = re.compile(r"^[A-Z]99XX99$")


def is_placeholder_atc_code(code: Optional[str]) -> bool:
    if not code:
        return True

    normalized = str(code).strip().upper()
    return not normalized or bool(PLACEHOLDER_ATC_PATTERN.match(normalized))


def is_specific_atc_code(code: Optional[str]) -> bool:
    if not code:
        return False

    normalized = str(code).strip().upper()
    return bool(ATC_CODE_PATTERN.match(normalized)) and not is_placeholder_atc_code(
        normalized
    )


def load_drug_payload(path: Path) -> Tuple[Any, List[Dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    drugs = payload if isinstance(payload, list) else payload.get("drugs", [])
    if not isinstance(drugs, list):
        raise ValueError(f"Unexpected drug payload format in {path}")
    return payload, drugs


def write_drug_payload(path: Path, payload: Any, drugs: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_payload = drugs if isinstance(payload, list) else {**payload, "drugs": drugs}
    path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")


def merge_external_ids(
    drug: Dict[str, Any], external_ids: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not external_ids:
        return drug, {}

    merged = deepcopy(drug)
    applied: Dict[str, Any] = {}

    for field_name, value in external_ids.items():
        if value in (None, "", []):
            continue

        normalized_value: Any = value
        if field_name == "pubchem_cid":
            try:
                normalized_value = int(str(value).strip())
            except (TypeError, ValueError):
                continue

        existing_value = merged.get(field_name)
        if existing_value in (None, "", []):
            merged[field_name] = normalized_value
            applied[field_name] = normalized_value

    return merged, applied
