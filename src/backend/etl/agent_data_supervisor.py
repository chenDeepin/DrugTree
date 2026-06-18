#!/usr/bin/env python3
"""Agent data supervisor — a reusable, resumable audit-loop ETL stage.

This stage reads canonical ``data/drugs.json`` and, for each configured field,
fetches web evidence via *pluggable source adapters*, computes a confidence
score, and proposes values with a full provenance tag
(``{source, url, fetched_at, confidence}``).

Guardrails baked in (see ``docs/plans/2026-06-12-next-round-plan.md`` Track H):

* **No silent overwrite of existing high-confidence values.** If a field already
  has a value, a change is only *proposed* when the adapter's confidence is high,
  and it is always logged as a conflict in a human-review queue rather than
  written blindly.
* **Provenance on everything.** Every proposed value carries source, URL,
  fetch timestamp, and confidence. Nothing is fabricated: if an adapter cannot
  fetch evidence it returns ``None`` and the field is queued for review.
* **Graceful degradation.** Adapters wrap network work in try/except with
  per-call timeouts and capped retries (the underlying ``httpx`` clients already
  retry with backoff). An adapter that raises or is offline is recorded as an
  error for that record and the loop keeps going.
* **Resumable.** A checkpoint under ``data/checkpoints/`` records processed drug
  ids so a re-run continues rather than restarts.
* **Bounded.** ``batch_size`` / ``max_records`` cap how much a single run does;
  this stage is a supervised audit loop, not a bulk overwriter.

Outputs:

* ``data/reports/agent_supervisor_report_<ts>.json`` — per-run report + the
  human-review queue (conflicts, low-confidence proposals, unresolved fields).
* ``data/changes/<uuid>.json`` — one record per *accepted* change, in the
  existing :class:`~src.backend.models.change.DrugChange` format.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence

# ---------------------------------------------------------------------------
# Imports that work both as a package module and as a direct script.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - exercised via package import in tests
    from ..models.change import (
        ChangePriority,
        ChangeType,
        DrugChange,
        FieldChange,
    )
    from .atc_utils import is_placeholder_atc_code, is_specific_atc_code
except ImportError:  # pragma: no cover - direct-script fallback
    import sys

    _BACKEND_ROOT = Path(__file__).resolve().parents[1]
    _SRC_ROOT = _BACKEND_ROOT.parent
    _REPO_ROOT = _SRC_ROOT.parent
    for _p in (_REPO_ROOT, _SRC_ROOT, _BACKEND_ROOT):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
    from src.backend.models.change import (  # type: ignore
        ChangePriority,
        ChangeType,
        DrugChange,
        FieldChange,
    )
    from src.backend.etl.atc_utils import (  # type: ignore
        is_placeholder_atc_code,
        is_specific_atc_code,
    )

LOGGER = logging.getLogger(__name__)

# Ensure the backend root is importable so transitively-imported ETL clients
# (e.g. ``fda_client`` -> ``from cache.cache_manager import ...``) resolve when
# this module is launched as ``python -m src.backend.etl.agent_data_supervisor``.
import sys as _sys

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
for _path in (
    _BACKEND_ROOT.parent.parent,  # repo root
    _BACKEND_ROOT.parent,         # src/
    _BACKEND_ROOT,                # src/backend/
):
    if str(_path) not in _sys.path:
        _sys.path.insert(0, str(_path))

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DRUGS_FILE = PROJECT_ROOT / "data" / "drugs.json"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "reports"
DEFAULT_CHANGES_DIR = PROJECT_ROOT / "data" / "changes"
DEFAULT_CHECKPOINT_DIR = PROJECT_ROOT / "data" / "checkpoints"
DEFAULT_CHECKPOINT_FILE = DEFAULT_CHECKPOINT_DIR / "agent_supervisor_checkpoint.json"

# Confidence at/above which a *change to an existing value* is allowed to be
# proposed (still review-gated, never auto-written over an existing value).
HIGH_CONFIDENCE_THRESHOLD = 0.85
# Confidence at/above which filling an *empty* field is treated as accept-able.
ACCEPT_CONFIDENCE_THRESHOLD = 0.6


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Provenance + proposal data model
# ---------------------------------------------------------------------------
@dataclass
class Provenance:
    """A provenance tag attached to every proposed value.

    Mirrors the schema requested in the plan: ``{source, url, fetched_at,
    confidence}``.
    """

    source: str
    url: Optional[str]
    fetched_at: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FieldProposal:
    """A proposed value for a single field of a single drug."""

    drug_id: str
    field: str
    value: Any
    provenance: Provenance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drug_id": self.drug_id,
            "field": self.field,
            "value": self.value,
            "provenance": self.provenance.to_dict(),
        }


# Disposition of a proposal after gating.
DISP_ACCEPTED = "accepted"          # filled an empty field with sufficient confidence
DISP_CONFLICT = "conflict"          # existing value differs; queued for human review
DISP_LOW_CONFIDENCE = "low_confidence"  # below accept threshold; queued
DISP_NO_CHANGE = "no_change"        # proposal matches existing value
DISP_UNRESOLVED = "unresolved"      # adapter returned nothing
DISP_ERROR = "error"                # adapter raised


@dataclass
class FieldOutcome:
    drug_id: str
    field: str
    disposition: str
    proposed_value: Any = None
    existing_value: Any = None
    provenance: Optional[Dict[str, Any]] = None
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Adapter protocol
# ---------------------------------------------------------------------------
class FieldAdapter(Protocol):
    """A pluggable source adapter for one canonical field.

    Implementations MUST:
      * expose ``name`` and ``field`` attributes;
      * implement ``async propose(drug) -> Optional[FieldProposal]``;
      * never raise on ordinary network failure (return ``None`` instead);
      * attach a real :class:`Provenance` to any value they return.

    The supervisor catches exceptions defensively regardless, but a well-behaved
    adapter degrades to ``None``.
    """

    name: str
    field: str

    async def propose(self, drug: Dict[str, Any]) -> Optional[FieldProposal]:
        ...


def needs_enrichment(drug: Dict[str, Any], field: str) -> bool:
    """Whether a field is empty/placeholder and therefore a fill candidate."""
    value = drug.get(field)
    if field == "atc_code":
        # Placeholder ``*99XX99`` codes count as needing enrichment.
        return is_placeholder_atc_code(value) or not is_specific_atc_code(value)
    if value in (None, "", [], {}):
        return True
    return False


# ---------------------------------------------------------------------------
# Concrete adapters (reuse existing async clients + canonical normalizers)
# ---------------------------------------------------------------------------
class OpenFDAApprovalAdapter:
    """H1 (year_approved) + H4 (company) via openFDA drugsfda.

    Reuses :class:`FDAClient.get_drug_approvals` and the canonical
    :func:`normalize_fda_metadata` so this stays consistent with the main ETL.
    Crosswalks by drug name (and brand-name synonyms when available).
    """

    name = "openfda"
    field = "year_approved"  # primary field; also yields ``company``

    BASE_URL = "https://api.fda.gov/drug/drugsfda.json"

    def __init__(self, client: Any, *, also_company: bool = True) -> None:
        self._client = client
        self.also_company = also_company

    def _url(self, drug_name: str) -> str:
        query = (
            f'openfda.generic_name:"{drug_name}" '
            f'OR openfda.brand_name:"{drug_name}"'
        )
        return f"{self.BASE_URL}?search={query}&limit=20"

    async def _approvals(self, drug: Dict[str, Any]) -> List[Dict[str, Any]]:
        names: List[str] = []
        if drug.get("name"):
            names.append(str(drug["name"]))
        for syn in drug.get("synonyms") or []:
            cleaned = str(syn).split("(")[0].strip().rstrip(";").strip()
            if cleaned and cleaned not in names:
                names.append(cleaned)
            if len(names) >= 3:
                break
        for name in names:
            approvals = await self._client.get_drug_approvals(name)
            if approvals:
                return approvals
        return []

    async def propose(self, drug: Dict[str, Any]) -> Optional[FieldProposal]:
        from .drug_metadata import normalize_fda_metadata  # local import: heavy deps

        drug_name = drug.get("name")
        if not drug_name:
            return None
        approvals = await self._approvals(drug)
        if not approvals:
            return None
        meta = normalize_fda_metadata(approvals)
        year = meta.get("year_approved")
        if year is None:
            return None
        # Confidence: an exact application record with a parseable year is strong;
        # we are conservative because crosswalk is name-based.
        confidence = 0.8
        prov = Provenance(
            source="openFDA:drugsfda",
            url=self._url(str(drug_name)),
            fetched_at=utcnow_iso(),
            confidence=confidence,
        )
        return FieldProposal(
            drug_id=drug["id"],
            field="year_approved",
            value=int(year),
            provenance=prov,
        )


class OpenFDACompanyAdapter(OpenFDAApprovalAdapter):
    """H4 company sponsor via the same openFDA crosswalk."""

    name = "openfda_company"
    field = "company"

    async def propose(self, drug: Dict[str, Any]) -> Optional[FieldProposal]:
        from .drug_metadata import normalize_fda_metadata

        drug_name = drug.get("name")
        if not drug_name:
            return None
        approvals = await self._approvals(drug)
        if not approvals:
            return None
        meta = normalize_fda_metadata(approvals)
        company = meta.get("company")
        if not company:
            return None
        prov = Provenance(
            source="openFDA:drugsfda",
            url=self._url(str(drug_name)),
            fetched_at=utcnow_iso(),
            # Sponsor on the label can be a repackager, not the originator — so
            # company confidence is deliberately lower than year.
            confidence=0.65,
        )
        return FieldProposal(
            drug_id=drug["id"],
            field="company",
            value=company,
            provenance=prov,
        )


class ChemblAtcAdapter:
    """H2 ATC placeholder resolution via ChEMBL molecule ATC classifications.

    Uses a lightweight direct ``httpx`` call to the ChEMBL molecule endpoint
    (or a molecule id already on the record) to recover a *specific* ATC code,
    replacing ``*99XX99`` placeholders. Only proposes specific codes.
    """

    name = "chembl_atc"
    field = "atc_code"

    MOLECULE_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule"
    SEARCH_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json"

    def __init__(self, http_client: Any) -> None:
        # ``http_client`` is an httpx.AsyncClient-like object with ``.get``.
        self._http = http_client

    async def _molecule_payload(self, drug: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        chembl_id = drug.get("chembl_id")
        try:
            if chembl_id:
                resp = await self._http.get(
                    f"{self.MOLECULE_URL}/{chembl_id}.json"
                )
                if resp.status_code == 200:
                    return resp.json()
            name = drug.get("name")
            if name:
                clean = "".join(c for c in str(name).split("/")[0] if c.isalnum() or c in " -_").strip()
                resp = await self._http.get(self.SEARCH_URL, params={"q": clean})
                if resp.status_code == 200:
                    molecules = resp.json().get("molecules", [])
                    if molecules:
                        return molecules[0]
        except Exception as exc:  # graceful degradation
            LOGGER.debug("ChEMBL ATC fetch failed for %s: %s", drug.get("id"), exc)
        return None

    async def propose(self, drug: Dict[str, Any]) -> Optional[FieldProposal]:
        payload = await self._molecule_payload(drug)
        if not payload:
            return None
        classifications = payload.get("atc_classifications") or []
        chembl_id = payload.get("molecule_chembl_id") or drug.get("chembl_id")
        for code in classifications:
            code_str = code if isinstance(code, str) else (code or {}).get("level5")
            if code_str and is_specific_atc_code(code_str):
                url = (
                    f"{self.MOLECULE_URL}/{chembl_id}.json"
                    if chembl_id
                    else self.SEARCH_URL
                )
                prov = Provenance(
                    source="ChEMBL:molecule.atc_classifications",
                    url=url,
                    fetched_at=utcnow_iso(),
                    # A curated ATC classification on a matched molecule is high
                    # confidence — but we still review-gate any *change* below.
                    confidence=0.9,
                )
                return FieldProposal(
                    drug_id=drug["id"],
                    field="atc_code",
                    value=str(code_str).upper(),
                    provenance=prov,
                )
        return None


class ChemblMechanismAdapter:
    """H5 targets + class via ChEMBL mechanism of action.

    Reuses :class:`ChEMBLClient.get_clinical_candidates` is target-centric, so
    here we hit the mechanism endpoint filtered by molecule id and feed the raw
    payload through :func:`normalize_chembl_metadata`.
    """

    name = "chembl_mechanism"
    field = "targets"  # primary; also yields ``class``

    MECHANISM_URL = "https://www.ebi.ac.uk/chembl/api/data/mechanism.json"

    def __init__(self, http_client: Any, *, target_field: str = "targets") -> None:
        self._http = http_client
        self.field = target_field

    async def _mechanisms(self, chembl_id: str) -> List[Dict[str, Any]]:
        try:
            resp = await self._http.get(
                self.MECHANISM_URL,
                params={"molecule_chembl_id": chembl_id, "limit": 50},
            )
            if resp.status_code == 200:
                return resp.json().get("mechanisms", [])
        except Exception as exc:
            LOGGER.debug("ChEMBL mechanism fetch failed for %s: %s", chembl_id, exc)
        return []

    async def propose(self, drug: Dict[str, Any]) -> Optional[FieldProposal]:
        from .drug_metadata import normalize_chembl_metadata

        chembl_id = drug.get("chembl_id")
        if not chembl_id:
            return None
        mechanisms = await self._mechanisms(str(chembl_id))
        if not mechanisms:
            return None
        meta = normalize_chembl_metadata(
            molecule_payload=None,
            mechanisms_payload=mechanisms,
            indications_payload=None,
        )
        url = f"{self.MECHANISM_URL}?molecule_chembl_id={chembl_id}"
        if self.field == "class":
            class_name = meta.get("class_name")
            if not class_name:
                return None
            prov = Provenance(
                source="ChEMBL:mechanism.mechanism_of_action",
                url=url,
                fetched_at=utcnow_iso(),
                confidence=0.75,
            )
            return FieldProposal(
                drug_id=drug["id"],
                field="class",
                value=class_name,
                provenance=prov,
            )
        targets = meta.get("targets") or []
        if not targets:
            return None
        prov = Provenance(
            source="ChEMBL:mechanism.target_pref_name",
            url=url,
            fetched_at=utcnow_iso(),
            confidence=0.8,
        )
        return FieldProposal(
            drug_id=drug["id"],
            field="targets",
            value=targets,
            provenance=prov,
        )


# ---------------------------------------------------------------------------
# Checkpoint helpers (resume support)
# ---------------------------------------------------------------------------
def load_checkpoint(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            LOGGER.warning("Corrupt checkpoint at %s; starting fresh", path)
    return {"processed_ids": [], "field_outcomes": {}, "updated_at": None}


def save_checkpoint(path: Path, processed_ids: Iterable[str],
                    field_outcomes: Optional[Dict[str, Any]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "processed_ids": sorted(set(processed_ids)),
        "field_outcomes": field_outcomes or {},
        "updated_at": utcnow_iso(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# The supervisor
# ---------------------------------------------------------------------------
class AgentDataSupervisor:
    """Batch records, fetch field evidence, gate by confidence, queue + report."""

    def __init__(
        self,
        adapters: Sequence[FieldAdapter],
        *,
        drugs_file: Path = DEFAULT_DRUGS_FILE,
        reports_dir: Path = DEFAULT_REPORTS_DIR,
        changes_dir: Path = DEFAULT_CHANGES_DIR,
        checkpoint_file: Path = DEFAULT_CHECKPOINT_FILE,
        batch_size: int = 50,
        max_records: Optional[int] = None,
        accept_threshold: float = ACCEPT_CONFIDENCE_THRESHOLD,
        high_confidence_threshold: float = HIGH_CONFIDENCE_THRESHOLD,
        write_changes: bool = True,
        apply_to_canonical: bool = False,
        per_adapter_timeout: float = 30.0,
        verify_existing: bool = True,
    ) -> None:
        self.adapters = list(adapters)
        self.drugs_file = Path(drugs_file)
        self.reports_dir = Path(reports_dir)
        self.changes_dir = Path(changes_dir)
        self.checkpoint_file = Path(checkpoint_file)
        self.batch_size = max(1, batch_size)
        self.max_records = max_records
        self.accept_threshold = accept_threshold
        self.high_confidence_threshold = high_confidence_threshold
        self.write_changes = write_changes
        # Off by default: writing canonical data is a separate, deliberate act.
        self.apply_to_canonical = apply_to_canonical
        self.per_adapter_timeout = per_adapter_timeout
        # When True, adapters also run against already-populated fields so that
        # high-confidence *disagreements* surface as conflicts (the
        # no-silent-overwrite guarantee). When False, only empty/placeholder
        # fields are queried (cheaper; pure gap-fill).
        self.verify_existing = verify_existing

        self.outcomes: List[FieldOutcome] = []
        self.review_queue: List[Dict[str, Any]] = []
        self.accepted_changes: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []

    # -- loading -----------------------------------------------------------
    def _load_drugs(self) -> tuple[Any, List[Dict[str, Any]]]:
        payload = json.loads(self.drugs_file.read_text(encoding="utf-8"))
        drugs = payload if isinstance(payload, list) else payload.get("drugs", [])
        return payload, drugs

    # -- gating ------------------------------------------------------------
    def _gate(
        self, drug: Dict[str, Any], proposal: FieldProposal
    ) -> FieldOutcome:
        field = proposal.field
        existing = drug.get(field)
        existing_is_empty = needs_enrichment(drug, field)
        prov_dict = proposal.provenance.to_dict()

        # Proposal matches what we already have -> no-op (but still provenanced
        # in the report so we can show "verified").
        if not existing_is_empty and _values_equal(existing, proposal.value):
            return FieldOutcome(
                drug_id=drug["id"],
                field=field,
                disposition=DISP_NO_CHANGE,
                proposed_value=proposal.value,
                existing_value=existing,
                provenance=prov_dict,
                note="proposed value matches existing value",
            )

        # Existing non-empty value differs -> never silently overwrite. Only
        # surface as a conflict for human review, and only when confidence is
        # high enough to be worth a reviewer's time.
        if not existing_is_empty:
            note = (
                "existing value present; change requires human review"
                if proposal.provenance.confidence >= self.high_confidence_threshold
                else "existing value present and proposal below high-confidence bar"
            )
            return FieldOutcome(
                drug_id=drug["id"],
                field=field,
                disposition=DISP_CONFLICT,
                proposed_value=proposal.value,
                existing_value=existing,
                provenance=prov_dict,
                note=note,
            )

        # Empty field: accept if confident enough, else queue as low-confidence.
        if proposal.provenance.confidence >= self.accept_threshold:
            return FieldOutcome(
                drug_id=drug["id"],
                field=field,
                disposition=DISP_ACCEPTED,
                proposed_value=proposal.value,
                existing_value=existing,
                provenance=prov_dict,
                note="filled empty field with sourced value",
            )
        return FieldOutcome(
            drug_id=drug["id"],
            field=field,
            disposition=DISP_LOW_CONFIDENCE,
            proposed_value=proposal.value,
            existing_value=existing,
            provenance=prov_dict,
            note="below accept threshold; queued for review",
        )

    # -- per-record processing --------------------------------------------
    async def _process_drug(self, drug: Dict[str, Any]) -> List[FieldOutcome]:
        outcomes: List[FieldOutcome] = []
        for adapter in self.adapters:
            target_field = adapter.field
            # Skip adapters whose field is already populated/specific — unless
            # verify_existing is on, in which case we still query to detect
            # high-confidence disagreements (conflicts) for human review.
            if not needs_enrichment(drug, target_field) and not self.verify_existing:
                continue
            try:
                proposal = await asyncio.wait_for(
                    adapter.propose(drug), timeout=self.per_adapter_timeout
                )
            except asyncio.TimeoutError:
                outcomes.append(
                    FieldOutcome(
                        drug_id=drug["id"],
                        field=target_field,
                        disposition=DISP_ERROR,
                        note=f"adapter {adapter.name} timed out",
                    )
                )
                self.errors.append(
                    {"drug_id": drug["id"], "adapter": adapter.name,
                     "field": target_field, "error": "timeout"}
                )
                continue
            except Exception as exc:  # graceful degradation
                outcomes.append(
                    FieldOutcome(
                        drug_id=drug["id"],
                        field=target_field,
                        disposition=DISP_ERROR,
                        note=f"adapter {adapter.name} error: {exc}",
                    )
                )
                self.errors.append(
                    {"drug_id": drug["id"], "adapter": adapter.name,
                     "field": target_field, "error": str(exc)}
                )
                continue

            if proposal is None:
                outcomes.append(
                    FieldOutcome(
                        drug_id=drug["id"],
                        field=target_field,
                        disposition=DISP_UNRESOLVED,
                        existing_value=drug.get(target_field),
                        note=f"{adapter.name} found no evidence",
                    )
                )
                continue

            outcomes.append(self._gate(drug, proposal))
        return outcomes

    # -- main loop ---------------------------------------------------------
    async def run(self) -> Dict[str, Any]:
        payload, drugs = self._load_drugs()
        checkpoint = load_checkpoint(self.checkpoint_file)
        processed_ids = set(checkpoint.get("processed_ids", []))

        pending = [d for d in drugs if d.get("id") not in processed_ids]
        if self.max_records is not None:
            pending = pending[: self.max_records]

        LOGGER.info(
            "Supervisor run: %d drugs total, %d already processed, %d this run",
            len(drugs), len(processed_ids), len(pending),
        )

        drug_by_id = {d["id"]: d for d in drugs if d.get("id")}
        canonical_dirty = False

        for start in range(0, len(pending), self.batch_size):
            batch = pending[start : start + self.batch_size]
            batch_outcomes = await asyncio.gather(
                *(self._process_drug(drug) for drug in batch)
            )
            for drug, drug_outcomes in zip(batch, batch_outcomes):
                self.outcomes.extend(drug_outcomes)
                for outcome in drug_outcomes:
                    self._record_outcome(drug_by_id.get(drug["id"], drug), outcome)
                    if (
                        self.apply_to_canonical
                        and outcome.disposition == DISP_ACCEPTED
                    ):
                        drug_by_id[drug["id"]][outcome.field] = outcome.proposed_value
                        canonical_dirty = True
                processed_ids.add(drug["id"])
            # Checkpoint after each batch so re-runs resume mid-stream.
            save_checkpoint(self.checkpoint_file, processed_ids)

        if self.apply_to_canonical and canonical_dirty:
            self._write_canonical(payload, drugs)

        report = self._write_report(total_drugs=len(drugs),
                                    processed_this_run=len(pending),
                                    already_processed=len(processed_ids) - len(pending))
        return report

    # -- outcome recording -------------------------------------------------
    def _record_outcome(self, drug: Dict[str, Any], outcome: FieldOutcome) -> None:
        if outcome.disposition in (DISP_CONFLICT, DISP_LOW_CONFIDENCE):
            self.review_queue.append(outcome.to_dict())
        elif outcome.disposition == DISP_ACCEPTED:
            if self.write_changes:
                change = self._build_change_record(drug, outcome)
                self.accepted_changes.append(change)

    def _build_change_record(
        self, drug: Dict[str, Any], outcome: FieldOutcome
    ) -> Dict[str, Any]:
        priority = ChangeDetectorPriority(outcome.field)
        new_snapshot = dict(drug)
        new_snapshot[outcome.field] = outcome.proposed_value
        change = DrugChange(
            drug_id=drug["id"],
            change_type=ChangeType.UPDATED,
            field_changes=[
                FieldChange(
                    field_name=outcome.field,
                    old_value=outcome.existing_value,
                    new_value=outcome.proposed_value,
                    priority=priority,
                )
            ],
            priority=priority,
            old_snapshot=dict(drug),
            new_snapshot=new_snapshot,
            source=f"agent_data_supervisor:{(outcome.provenance or {}).get('source')}",
            applied_at=None,
            applied_by="agent_data_supervisor",
        )
        record = json.loads(change.model_dump_json())
        # Carry the full provenance tag alongside the change record.
        record["provenance"] = outcome.provenance
        return record

    # -- writers -----------------------------------------------------------
    def _write_canonical(self, payload: Any, drugs: List[Dict[str, Any]]) -> None:
        out = drugs if isinstance(payload, list) else {**payload, "drugs": drugs}
        self.drugs_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
        LOGGER.info("Wrote canonical updates to %s", self.drugs_file)

    def _write_changes_files(self) -> List[str]:
        if not self.write_changes or not self.accepted_changes:
            return []
        self.changes_dir.mkdir(parents=True, exist_ok=True)
        written: List[str] = []
        for record in self.accepted_changes:
            path = self.changes_dir / f"{record['change_id']}.json"
            path.write_text(json.dumps(record, indent=2), encoding="utf-8")
            written.append(str(path))
        return written

    def _summary(self) -> Dict[str, Any]:
        by_disposition: Dict[str, int] = {}
        by_field: Dict[str, Dict[str, int]] = {}
        for outcome in self.outcomes:
            by_disposition[outcome.disposition] = (
                by_disposition.get(outcome.disposition, 0) + 1
            )
            field_bucket = by_field.setdefault(outcome.field, {})
            field_bucket[outcome.disposition] = (
                field_bucket.get(outcome.disposition, 0) + 1
            )
        return {"by_disposition": by_disposition, "by_field": by_field}

    def _write_report(self, *, total_drugs: int, processed_this_run: int,
                      already_processed: int) -> Dict[str, Any]:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        change_files = self._write_changes_files()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report = {
            "generated_at": utcnow_iso(),
            "stage": "agent_data_supervisor",
            "drugs_file": str(self.drugs_file),
            "totals": {
                "total_drugs": total_drugs,
                "processed_this_run": processed_this_run,
                "already_processed": already_processed,
            },
            "config": {
                "adapters": [
                    {"name": a.name, "field": a.field} for a in self.adapters
                ],
                "batch_size": self.batch_size,
                "max_records": self.max_records,
                "accept_threshold": self.accept_threshold,
                "high_confidence_threshold": self.high_confidence_threshold,
                "apply_to_canonical": self.apply_to_canonical,
            },
            "summary": self._summary(),
            "review_queue": self.review_queue,
            "accepted_change_files": change_files,
            "accepted_changes_count": len(self.accepted_changes),
            "errors": self.errors,
        }
        report_path = self.reports_dir / f"agent_supervisor_report_{timestamp}.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        LOGGER.info(
            "Supervisor report written to %s (%d review items, %d accepted)",
            report_path, len(self.review_queue), len(self.accepted_changes),
        )
        return report


def ChangeDetectorPriority(field: str) -> ChangePriority:
    """Map a field name to a change priority (reuses the codebase mapping)."""
    mapping = {
        "atc_code": ChangePriority.CRITICAL,
        "atc_category": ChangePriority.CRITICAL,
        "targets": ChangePriority.HIGH,
        "indication": ChangePriority.HIGH,
        "year_approved": ChangePriority.MEDIUM,
        "class": ChangePriority.MEDIUM,
        "company": ChangePriority.LOW,
    }
    return mapping.get(field, ChangePriority.MEDIUM)


def _values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        return set(a or []) == set(b or [])
    return a == b


# ---------------------------------------------------------------------------
# H3 — disease-drug edge builder (separate from the per-field audit loop)
# ---------------------------------------------------------------------------
async def build_disease_drug_edges(
    *,
    indication_provider: Any,
    diseases_file: Path = PROJECT_ROOT / "data" / "diseases.json",
    drugs_file: Path = DEFAULT_DRUGS_FILE,
    edges_file: Path = PROJECT_ROOT / "data" / "disease_drug_edges.json",
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    max_diseases: Optional[int] = None,
    max_drugs_queried: Optional[int] = None,
    write: bool = True,
    sync_disease_counts: bool = True,
) -> Dict[str, Any]:
    """H3: extend ``disease_drug_edges.json`` from available indication data.

    ``indication_provider`` is any object exposing
    ``async indications_for_drug(chembl_id) -> List[{disease_id, disease_name}]``
    (``ChEMBLClient.get_drug_indications`` satisfies this). Diseases with no
    resolved drug are flagged explicitly with ``no_approved_drug`` so the UI can
    distinguish "sparse data" from "genuinely no approved therapy".

    Existing curated edges are preserved; only new, sourced edges are appended.
    """
    drugs_payload = json.loads(Path(drugs_file).read_text(encoding="utf-8"))
    drugs = (
        drugs_payload
        if isinstance(drugs_payload, list)
        else drugs_payload.get("drugs", [])
    )
    diseases_payload = json.loads(Path(diseases_file).read_text(encoding="utf-8"))
    diseases = (
        diseases_payload
        if isinstance(diseases_payload, list)
        else diseases_payload.get("diseases", [])
    )

    existing = {"edges": [], "metadata": {}}
    if Path(edges_file).exists():
        try:
            existing = json.loads(Path(edges_file).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    existing_edges = existing.get("edges", []) if isinstance(existing, dict) else []
    existing_keys = {
        (e.get("disease_id"), e.get("drug_id")) for e in existing_edges
    }

    # Map ChEMBL disease ids (MeSH/EFO) we get from indications back to our
    # canonical disease ids via synonym / id match.
    disease_index: Dict[str, str] = {}
    for disease in diseases:
        did = disease.get("id")
        if not did:
            continue
        disease_index[did.lower()] = did
        name = disease.get("canonical_name") or ""
        if name:
            disease_index[name.lower()] = did
        for syn in disease.get("synonyms") or []:
            disease_index[str(syn).lower()] = did

    drugs_with_chembl = [
        d for d in drugs if d.get("chembl_id") and d.get("id")
    ]
    # Bound how many drugs we actually query upstream (rate-limited) so a demo
    # run stays bounded even on the full dataset.
    if max_drugs_queried is not None:
        drugs_with_chembl = drugs_with_chembl[:max_drugs_queried]

    new_edges: List[Dict[str, Any]] = []
    diseases_seen: set = set()
    errors: List[Dict[str, Any]] = []

    for drug in drugs_with_chembl:
        try:
            indications = await indication_provider.indications_for_drug(
                drug["chembl_id"]
            )
        except Exception as exc:  # graceful degradation
            errors.append({"drug_id": drug["id"], "error": str(exc)})
            continue
        for ind in indications or []:
            name = (ind.get("disease_name") or "").lower()
            raw_id = (ind.get("disease_id") or "").lower()
            canonical = disease_index.get(name) or disease_index.get(raw_id)
            if not canonical:
                continue
            key = (canonical, drug["id"])
            if key in existing_keys:
                diseases_seen.add(canonical)
                continue
            new_edges.append(
                {
                    "disease_id": canonical,
                    "drug_id": drug["id"],
                    "indication_type": ind.get("indication_type", "primary"),
                    "evidence_source": "chembl_indication",
                    "evidence_level": "approved",
                    "provenance": {
                        "source": "ChEMBL:drug_indication",
                        "url": (
                            "https://www.ebi.ac.uk/chembl/api/data/drug_indication"
                            f"?molecule_chembl_id={drug['chembl_id']}"
                        ),
                        "fetched_at": utcnow_iso(),
                        "confidence": 0.7,
                    },
                }
            )
            existing_keys.add(key)
            diseases_seen.add(canonical)
        if max_diseases is not None and len(diseases_seen) >= max_diseases:
            break

    # Flag diseases with no approved drug edge at all (existing or new).
    covered = {e.get("disease_id") for e in existing_edges} | diseases_seen
    no_drug_flags = [
        {"disease_id": d.get("id"), "flag": "no_approved_drug"}
        for d in diseases
        if d.get("id") and d.get("id") not in covered
    ]

    merged_edges = existing_edges + new_edges
    metadata = {
        "generated_at": utcnow_iso(),
        "seed_edge_count": existing.get("metadata", {}).get("seed_edge_count")
        if isinstance(existing, dict)
        else None,
        "prior_edge_count": len(existing_edges),
        "new_edge_count": len(new_edges),
        "total_edge_count": len(merged_edges),
        "diseases_total": len(diseases),
        "diseases_covered": len(covered),
        "diseases_no_approved_drug": len(no_drug_flags),
        "errors": len(errors),
    }
    output = {"edges": merged_edges, "metadata": metadata, "no_drug_flags": no_drug_flags}

    if write:
        Path(edges_file).parent.mkdir(parents=True, exist_ok=True)
        Path(edges_file).write_text(json.dumps(output, indent=2), encoding="utf-8")
        # Keep diseases.json's approved_drug_count consistent with the edge file
        # (the test_disease_edge_consistency invariant). Without this, adding
        # edges would desync the counts the frontend/embeds rely on.
        if sync_disease_counts:
            edge_counts: Dict[str, int] = {}
            for edge in merged_edges:
                did = edge.get("disease_id")
                if did:
                    edge_counts[did] = edge_counts.get(did, 0) + 1
            changed = False
            for disease in diseases:
                did = disease.get("id")
                new_count = edge_counts.get(did, 0)
                if disease.get("approved_drug_count", 0) != new_count:
                    disease["approved_drug_count"] = new_count
                    changed = True
            if changed:
                out_diseases = (
                    diseases
                    if isinstance(diseases_payload, list)
                    else {**diseases_payload, "diseases": diseases}
                )
                Path(diseases_file).write_text(
                    json.dumps(out_diseases, indent=2), encoding="utf-8"
                )
        Path(reports_dir).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (Path(reports_dir) / f"disease_drug_edges_report_{ts}.json").write_text(
            json.dumps({**metadata, "errors_detail": errors}, indent=2),
            encoding="utf-8",
        )
    return output


# ---------------------------------------------------------------------------
# Default adapter wiring (live network) + CLI
# ---------------------------------------------------------------------------
def build_default_adapters(http_client: Any, *, fda_client: Any) -> List[FieldAdapter]:
    """Wire the live adapters around shared async clients."""
    return [
        OpenFDAApprovalAdapter(fda_client),
        OpenFDACompanyAdapter(fda_client),
        ChemblAtcAdapter(http_client),
        ChemblMechanismAdapter(http_client, target_field="targets"),
        ChemblMechanismAdapter(http_client, target_field="class"),
    ]


class _ChemblIndicationProvider:
    """Adapt :class:`ChEMBLClient.get_drug_indications` to the H3 builder API."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def indications_for_drug(self, chembl_id: str) -> List[Dict[str, Any]]:
        return await self._client.get_drug_indications(chembl_id)


async def _run_fields(args: argparse.Namespace) -> Dict[str, Any]:
    import httpx

    from .fda_client import FDAClient

    timeout = httpx.Timeout(args.timeout)
    async with httpx.AsyncClient(
        timeout=timeout, headers={"Accept": "application/json"}
    ) as http_client:
        fda_client = FDAClient()
        try:
            adapters = build_default_adapters(http_client, fda_client=fda_client)
            supervisor = AgentDataSupervisor(
                adapters,
                batch_size=args.batch_size,
                max_records=args.max_records,
                apply_to_canonical=args.apply,
                per_adapter_timeout=args.timeout,
            )
            return await supervisor.run()
        finally:
            await fda_client.close()


async def _run_edges(args: argparse.Namespace) -> Dict[str, Any]:
    """H3: build/extend disease-drug edges from ChEMBL indications (bounded)."""
    from .chembl_client import ChEMBLClient

    client = ChEMBLClient()
    try:
        provider = _ChemblIndicationProvider(client)
        out = await build_disease_drug_edges(
            indication_provider=provider,
            max_drugs_queried=args.max_records,
        )
        return {
            "summary": {"by_disposition": {}},
            "report_path": None,
            "review_queue": [],
            "accepted_changes_count": 0,
            "edges_metadata": out.get("metadata", {}),
        }
    finally:
        await client.close()


async def _run_live(args: argparse.Namespace) -> Dict[str, Any]:
    if getattr(args, "mode", "fields") == "edges":
        return await _run_edges(args)
    return await _run_fields(args)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Agent data supervisor (Track H)")
    parser.add_argument(
        "--mode",
        choices=["fields", "edges"],
        default="fields",
        help="'fields' = per-field audit loop (H1/H2/H4/H5); "
        "'edges' = disease-drug edge expansion (H3).",
    )
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument(
        "--max-records",
        type=int,
        default=200,
        help="Cap records this run (bounded demonstration default).",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Also write accepted fills to canonical drugs.json (off by default).",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    report = asyncio.run(_run_live(args))
    if args.mode == "edges":
        print(json.dumps({"edges_metadata": report.get("edges_metadata", {})},
                         indent=2))
        return 0
    summary = report.get("summary", {}).get("by_disposition", {})
    print(json.dumps({"report_path": report.get("report_path"),
                      "summary": summary,
                      "review_items": len(report.get("review_queue", [])),
                      "accepted": report.get("accepted_changes_count", 0)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
