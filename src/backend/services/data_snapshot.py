from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional, Union


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_MAX_STALE = timedelta(hours=24)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _record_count(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("drugs", "diseases", "edges", "families", "visible_regions"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    if isinstance(payload, list):
        return len(payload)
    return 0


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    sha256: str
    mtime_ns: int
    size: int
    record_count: int


@dataclass(frozen=True)
class CanonicalDataSnapshot:
    created_at: datetime
    source_hash: str
    sources: dict[str, SourceSnapshot]
    drugs_payload: Union[dict[str, Any], list[Any]]
    diseases_payload: Union[dict[str, Any], list[Any]]
    disease_drug_edges_payload: Union[dict[str, Any], list[Any]]
    body_ontology_payload: Union[dict[str, Any], list[Any]]
    drugs: list[dict[str, Any]]
    diseases: list[dict[str, Any]]
    disease_drug_edges: list[dict[str, Any]]
    body_ontology: dict[str, Any]


class DataSnapshotService:
    def __init__(
        self, data_dir: Optional[Path] = None, max_stale: timedelta = DEFAULT_MAX_STALE
    ):
        self.data_dir = data_dir or DATA_DIR
        self.max_stale = max_stale
        self._snapshot: Optional[CanonicalDataSnapshot] = None
        self._lock = Lock()
        self._cache_hits = 0
        self._cache_misses = 0
        self._refresh_count = 0

    def _source_paths(self) -> dict[str, Path]:
        return {
            "drugs": self.data_dir / "drugs.json",
            "diseases": self.data_dir / "diseases.json",
            "disease_drug_edges": self.data_dir / "disease_drug_edges.json",
            "body_ontology": self.data_dir / "ontology" / "body-ontology.json",
        }

    def _read_json(self, path: Path) -> tuple[bytes, Any]:
        raw = path.read_bytes()
        return raw, json.loads(raw.decode("utf-8"))

    def _collect_sources(self) -> tuple[dict[str, SourceSnapshot], dict[str, Any]]:
        sources: dict[str, SourceSnapshot] = {}
        payloads: dict[str, Any] = {}
        for name, path in self._source_paths().items():
            raw, payload = self._read_json(path)
            stat = path.stat()
            sources[name] = SourceSnapshot(
                path=path,
                sha256=hashlib.sha256(raw).hexdigest(),
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                record_count=_record_count(payload),
            )
            payloads[name] = payload
        return sources, payloads

    def _compute_source_hash(self, sources: dict[str, SourceSnapshot]) -> str:
        joined = "|".join(
            f"{name}:{snapshot.sha256}:{snapshot.mtime_ns}:{snapshot.size}"
            for name, snapshot in sorted(sources.items())
        )
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def _build_snapshot(self) -> CanonicalDataSnapshot:
        sources, payloads = self._collect_sources()
        drugs_payload = payloads["drugs"]
        diseases_payload = payloads["diseases"]
        disease_edges_payload = payloads["disease_drug_edges"]
        body_ontology_payload = payloads["body_ontology"]

        drugs = (
            drugs_payload.get("drugs", [])
            if isinstance(drugs_payload, dict)
            else drugs_payload
        )
        diseases = (
            diseases_payload.get("diseases", [])
            if isinstance(diseases_payload, dict)
            else diseases_payload
        )
        disease_drug_edges = (
            disease_edges_payload.get("edges", [])
            if isinstance(disease_edges_payload, dict)
            else disease_edges_payload
        )
        body_ontology = (
            body_ontology_payload if isinstance(body_ontology_payload, dict) else {}
        )

        return CanonicalDataSnapshot(
            created_at=_utcnow(),
            source_hash=self._compute_source_hash(sources),
            sources=sources,
            drugs_payload=drugs_payload,
            diseases_payload=diseases_payload,
            disease_drug_edges_payload=disease_edges_payload,
            body_ontology_payload=body_ontology_payload,
            drugs=list(drugs),
            diseases=list(diseases),
            disease_drug_edges=list(disease_drug_edges),
            body_ontology=body_ontology,
        )

    def _is_stale(self, snapshot: CanonicalDataSnapshot) -> bool:
        if _utcnow() - snapshot.created_at > self.max_stale:
            return True

        for name, path in self._source_paths().items():
            stat = path.stat()
            existing = snapshot.sources[name]
            if stat.st_mtime_ns != existing.mtime_ns or stat.st_size != existing.size:
                return True
        return False

    def get_snapshot(self, force_refresh: bool = False) -> CanonicalDataSnapshot:
        with self._lock:
            if (
                force_refresh
                or self._snapshot is None
                or self._is_stale(self._snapshot)
            ):
                self._cache_misses += 1
                self._refresh_count += 1
                self._snapshot = self._build_snapshot()
            else:
                self._cache_hits += 1
            return self._snapshot

    def refresh(self) -> CanonicalDataSnapshot:
        return self.get_snapshot(force_refresh=True)

    def cache_stats(self) -> dict[str, object]:
        snapshot_hash = (
            self._snapshot.source_hash if self._snapshot is not None else None
        )
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "refresh_count": self._refresh_count,
            "current_source_hash": snapshot_hash,
            "max_stale_hours": self.max_stale.total_seconds() / 3600,
        }


_snapshot_service: Optional[DataSnapshotService] = None


def get_data_snapshot_service() -> DataSnapshotService:
    global _snapshot_service
    if _snapshot_service is None:
        _snapshot_service = DataSnapshotService()
    return _snapshot_service
