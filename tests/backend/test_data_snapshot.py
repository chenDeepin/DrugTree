import json
from pathlib import Path

from src.backend.services.data_snapshot import DataSnapshotService


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def build_temp_dataset(root: Path) -> None:
    write_json(root / "drugs.json", {"drugs": [{"id": "drug-a", "name": "Drug A"}]})
    write_json(
        root / "diseases.json",
        {"diseases": [{"id": "disease-a", "canonical_name": "Disease A"}]},
    )
    write_json(
        root / "disease_drug_edges.json",
        {"edges": [{"disease_id": "disease-a", "drug_id": "drug-a"}]},
    )
    write_json(
        root / "ontology" / "body-ontology.json",
        {"visible_regions": [{"id": "heart_vascular", "display_name": "Heart"}]},
    )


def test_snapshot_service_reuses_snapshot_until_source_changes(tmp_path):
    build_temp_dataset(tmp_path)
    service = DataSnapshotService(data_dir=tmp_path)

    first = service.get_snapshot()
    second = service.get_snapshot()

    assert first is second
    assert first.drugs[0]["id"] == "drug-a"


def test_snapshot_service_refreshes_after_data_change(tmp_path):
    build_temp_dataset(tmp_path)
    service = DataSnapshotService(data_dir=tmp_path)

    original = service.get_snapshot()
    write_json(tmp_path / "drugs.json", {"drugs": [{"id": "drug-b", "name": "Drug B"}]})

    refreshed = service.refresh()

    assert refreshed is not original
    assert refreshed.drugs[0]["id"] == "drug-b"
    assert refreshed.source_hash != original.source_hash
