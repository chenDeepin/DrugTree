"""
DrugTree - Change Detector Unit Tests

Tests for hash-based change detection, rollback support, and change tracking.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from src.backend.models.change import (
    ChangeDetector,
    ChangeType,
    ChangePriority,
    FieldChange,
    DrugChange,
    ChangeSet,
    ChangeSetSummary,
    ROLLBACK_DAYS,
    HASH_EXCLUDE_FIELDS,
)
from src.backend.services.change_detector import (
    ChangeDetectorService,
    get_change_detector,
)


# Fixtures
@pytest.fixture
def sample_drug():
    """Sample drug dictionary for testing."""
    return {
        "id": "test_drug_001",
        "name": "Test Drug",
        "smiles": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        "atc_code": "C10AA05",
        "atc_category": "C",
        "molecular_weight": 348.48,
        "indication": "Hypercholesterolemia",
        "targets": ["HMG-CoA reductase"],
        "company": "Test Pharma",
        "phase": "IV",
        "year_approved": 1996,
        "generation": 2,
    }


@pytest.fixture
def sample_drug_updated(sample_drug):
    """Updated version of sample drug."""
    return {
        **sample_drug,
        "molecular_weight": 350.00,  # Changed
        "indication": "Hypercholesterolemia and cardiovascular disease",  # Changed
    }


@pytest.fixture
def change_detector_service():
    """Create change detector service instance for tests."""
    return ChangeDetectorService()


# Tests for ChangeDetector class
class TestChangeDetector:
    """Tests for ChangeDetector static methods."""

    def test_compute_hash_consistent(self, sample_drug):
        """Hash should be consistent for same input."""
        hash1 = ChangeDetector.compute_hash(sample_drug)
        hash2 = ChangeDetector.compute_hash(sample_drug)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest length

    def test_compute_hash_excludes_timestamps(self, sample_drug):
        """Hash should exclude timestamp fields."""
        drug_with_timestamp = {**sample_drug, "updated_at": "2024-01-01"}
        drug_different_timestamp = {**sample_drug, "updated_at": "2024-12-31"}

        hash1 = ChangeDetector.compute_hash(drug_with_timestamp)
        hash2 = ChangeDetector.compute_hash(drug_different_timestamp)

        assert hash1 == hash2

    def test_compute_hash_detects_changes(self, sample_drug):
        """Hash should change when significant fields change."""
        hash1 = ChangeDetector.compute_hash(sample_drug)

        modified_drug = {**sample_drug, "molecular_weight": 999.99}
        hash2 = ChangeDetector.compute_hash(modified_drug)

        assert hash1 != hash2

    def test_detect_change_new_drug(self, sample_drug):
        """Detect a new drug (no previous state)."""
        change = ChangeDetector.detect_change(None, sample_drug, "test_new")

        assert change is not None
        assert change.change_type == ChangeType.NEW
        assert change.drug_id == "test_drug_001"
        assert change.source == "test_new"

    def test_detect_change_no_change(self, sample_drug):
        """No change detected when drugs are identical."""
        change = ChangeDetector.detect_change(
            sample_drug, sample_drug, "test_no_change"
        )

        assert change is None

    def test_detect_change_field_update(self, sample_drug, sample_drug_updated):
        """Detect field-level changes."""
        change = ChangeDetector.detect_change(
            sample_drug, sample_drug_updated, "test_update"
        )

        assert change is not None
        assert change.change_type == ChangeType.UPDATED
        assert len(change.field_changes) == 2  # molecular_weight and indication

        # Check specific field changes
        field_names = [fc.field_name for fc in change.field_changes]
        assert "molecular_weight" in field_names
        assert "indication" in field_names

    def test_detect_change_prioritizes_critical_fields(self, sample_drug):
        """SMILES changes should be HIGH priority."""
        modified = {**sample_drug, "smiles": "CCO"}  # Different SMILES

        change = ChangeDetector.detect_change(sample_drug, modified, "test_priority")

        assert change is not None
        assert change.priority == ChangePriority.HIGH

    def test_detect_deprecation(self, sample_drug):
        """Detect drug deprecation."""
        change = ChangeDetector.detect_deprecation(
            sample_drug, "test_deprecate", reason="Removed from source data"
        )

        assert change is not None
        assert change.change_type == ChangeType.DEPRECATED
        assert change.drug_id == "test_drug_001"

    def test_create_rollback_change(self, sample_drug, sample_drug_updated):
        """Create rollback change from original."""
        original_change = ChangeDetector.detect_change(
            sample_drug, sample_drug_updated, "test_original"
        )
        # Set applied_at so make it eligible for rollback
        original_change.applied_at = datetime.now(timezone.utc)

        rollback = ChangeDetector.create_rollback_change(
            original_change, "test_rollback"
        )

        assert rollback is not None
        assert rollback.drug_id == original_change.drug_id
        assert rollback.old_snapshot == original_change.new_snapshot
        assert rollback.new_snapshot == original_change.old_snapshot


# Tests for DrugChange model
class TestDrugChange:
    """Tests for DrugChange Pydantic model."""

    def test_rollback_deadline(self, sample_drug):
        """Rollback deadline should be ROLLBACK_DAYS from applied_at."""
        applied_at = datetime.now(timezone.utc)
        change = DrugChange(
            drug_id="test",
            change_type=ChangeType.NEW,
            new_snapshot=sample_drug,
            source="test",
            applied_at=applied_at,
        )

        expected_deadline = applied_at + timedelta(days=ROLLBACK_DAYS)
        # Allow 1 minute tolerance for test execution time
        assert abs((change.rollback_deadline - expected_deadline).total_seconds()) < 60

    def test_can_rollback_true(self, sample_drug):
        """New change should be rollback eligible."""
        change = DrugChange(
            drug_id="test",
            change_type=ChangeType.UPDATED,
            new_snapshot=sample_drug,
            source="test",
            applied_at=datetime.now(timezone.utc),
        )

        assert change.can_rollback is True

    def test_can_rollback_false_if_rolled_back(self, sample_drug):
        """Already rolled back change should not be eligible."""
        change = DrugChange(
            drug_id="test",
            change_type=ChangeType.UPDATED,
            new_snapshot=sample_drug,
            source="test",
            rolled_back=True,
        )

        assert change.can_rollback is False

    def test_field_changes_list(self, sample_drug):
        """Field changes should be a list."""
        change = DrugChange(
            drug_id="test",
            change_type=ChangeType.UPDATED,
            field_changes=[
                FieldChange(
                    field_name="name",
                    old_value="Old Name",
                    new_value="New Name",
                    priority=ChangePriority.LOW,
                )
            ],
            new_snapshot=sample_drug,
            source="test",
        )

        assert len(change.field_changes) == 1
        assert change.field_changes[0].field_name == "name"


# Tests for ChangeSet model
class TestChangeSet:
    """Tests for ChangeSet model."""

    def test_changeset_statistics(self, sample_drug, sample_drug_updated):
        """ChangeSet should calculate statistics correctly."""
        changes = [
            DrugChange(
                drug_id="new_drug",
                change_type=ChangeType.NEW,
                new_snapshot=sample_drug,
                source="test",
            ),
            DrugChange(
                drug_id="updated_drug",
                change_type=ChangeType.UPDATED,
                old_snapshot=sample_drug,
                new_snapshot=sample_drug_updated,
                source="test",
            ),
            DrugChange(
                drug_id="deprecated_drug",
                change_type=ChangeType.DEPRECATED,
                old_snapshot=sample_drug,
                source="test",
            ),
        ]

        changeset = ChangeSet(changes=changes, source="test_set")

        assert changeset.new_drugs == 1
        assert changeset.updated_drugs == 1
        assert changeset.deprecated_drugs == 1
        assert changeset.total_changes == 3

    def test_critical_count(self, sample_drug):
        """Critical count should match CRITICAL priority changes."""
        changes = [
            DrugChange(
                drug_id="critical_drug",
                change_type=ChangeType.NEW,
                new_snapshot=sample_drug,
                source="test",
                field_changes=[
                    FieldChange(
                        field_name="atc_code",
                        old_value=None,
                        new_value="C10AA05",
                        priority=ChangePriority.CRITICAL,
                    )
                ],
            ),
            DrugChange(
                drug_id="normal_drug",
                change_type=ChangeType.UPDATED,
                new_snapshot=sample_drug,
                source="test",
                field_changes=[
                    FieldChange(
                        field_name="name",
                        old_value="Old Name",
                        new_value="New Name",
                        priority=ChangePriority.LOW,
                    )
                ],
            ),
        ]

        changeset = ChangeSet(changes=changes, source="test_set")

        assert changeset.critical_count == 1


# Tests for ChangeDetectorService
class TestChangeDetectorService:
    """Tests for ChangeDetectorService async methods."""

    @pytest.mark.asyncio
    async def test_detect_all_changes(self, change_detector_service, sample_drug):
        """Detect changes between two drug datasets."""
        old_drugs = [sample_drug]
        new_drugs = [
            {**sample_drug, "molecular_weight": 350.00},  # Updated
            {
                "id": "new_drug",
                "name": "New Drug",
                **{k: v for k, v in sample_drug.items() if k not in ["id", "name"]},
            },  # New
        ]

        changeset = await change_detector_service.detect_all_changes(
            old_drugs, new_drugs, "test_sync"
        )

        assert changeset is not None
        assert changeset.total_changes >= 1  # At least the new drug

    @pytest.mark.asyncio
    async def test_apply_change(self, change_detector_service, sample_drug):
        """Apply a change and verify it's tracked."""
        change = DrugChange(
            drug_id="test_drug",
            change_type=ChangeType.NEW,
            new_snapshot=sample_drug,
            source="test_apply",
        )

        result = await change_detector_service.apply_change(change, "test_user")

        assert result is True
        assert change.applied_at is not None
        assert change.applied_by == "test_user"

    @pytest.mark.asyncio
    async def test_apply_change_idempotent(self, change_detector_service, sample_drug):
        """Applying same change twice should return False."""
        change = DrugChange(
            drug_id="test_drug",
            change_type=ChangeType.NEW,
            new_snapshot=sample_drug,
            source="test_apply",
        )

        await change_detector_service.apply_change(change)
        result = await change_detector_service.apply_change(change)

        assert result is False

    @pytest.mark.asyncio
    async def test_apply_changeset(self, change_detector_service, sample_drug):
        """Apply all changes in a changeset."""
        changes = [
            DrugChange(
                drug_id=f"drug_{i}",
                change_type=ChangeType.NEW,
                new_snapshot=sample_drug,
                source="test_changeset",
            )
            for i in range(3)
        ]

        changeset = ChangeSet(changes=changes, source="test_set")
        success, failure = await change_detector_service.apply_changeset(changeset)

        assert success == 3
        assert failure == 0

    @pytest.mark.asyncio
    async def test_apply_changeset_filter_critical(
        self, change_detector_service, sample_drug
    ):
        """Apply only critical changes when filter enabled."""
        changes = [
            DrugChange(
                drug_id="critical",
                change_type=ChangeType.NEW,
                new_snapshot=sample_drug,
                source="test",
                priority=ChangePriority.CRITICAL,
            ),
            DrugChange(
                drug_id="normal",
                change_type=ChangeType.NEW,
                new_snapshot=sample_drug,
                source="test",
                priority=ChangePriority.LOW,
            ),
        ]

        changeset = ChangeSet(changes=changes, source="test_set")
        success, failure = await change_detector_service.apply_changeset(
            changeset, filter_critical_only=True
        )

        assert success == 1  # Only critical applied

    @pytest.mark.asyncio
    async def test_rollback_change(
        self, change_detector_service, sample_drug, sample_drug_updated
    ):
        """Rollback a previously applied change."""
        # First, apply a change
        original = DrugChange(
            drug_id="test_drug",
            change_type=ChangeType.UPDATED,
            old_snapshot=sample_drug,
            new_snapshot=sample_drug_updated,
            source="test_rollback",
        )
        await change_detector_service.apply_change(original)

        # Then, rollback
        rollback = await change_detector_service.rollback_change(
            original.change_id, "test_user"
        )

        assert rollback is not None
        assert original.rolled_back is True
        assert original.rollback_change_id == rollback.change_id

    @pytest.mark.asyncio
    async def test_rollback_expired_change(self, change_detector_service, sample_drug):
        """Cannot rollback changes past deadline."""
        # Create change with expired deadline
        change = DrugChange(
            drug_id="test_drug",
            change_type=ChangeType.UPDATED,
            new_snapshot=sample_drug,
            source="test",
            applied_at=datetime.now(timezone.utc) - timedelta(days=ROLLBACK_DAYS + 1),
        )

        # Manually add to applied changes
        change_detector_service._applied_changes[change.change_id] = change

        # Attempt rollback should raise ValueError
        with pytest.raises(ValueError, match="cannot be rolled back"):
            await change_detector_service.rollback_change(change.change_id)

    @pytest.mark.asyncio
    async def test_get_drug_history(self, change_detector_service, sample_drug):
        """Get change history for a specific drug."""
        # Apply multiple changes
        for i in range(3):
            change = DrugChange(
                drug_id="test_drug",
                change_type=ChangeType.UPDATED,
                new_snapshot={**sample_drug, "molecular_weight": 300 + i},
                source=f"test_{i}",
            )
            await change_detector_service.apply_change(change)

        history = await change_detector_service.get_drug_history("test_drug")

        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_get_rollback_eligible(self, change_detector_service, sample_drug):
        """Get all rollback-eligible changes."""
        # Apply a change
        change = DrugChange(
            drug_id="test_drug",
            change_type=ChangeType.NEW,
            new_snapshot=sample_drug,
            source="test",
        )
        await change_detector_service.apply_change(change)

        eligible = await change_detector_service.get_rollback_eligible()

        assert len(eligible) >= 1
        assert all(c.can_rollback for c in eligible)

    @pytest.mark.asyncio
    async def test_cleanup_expired_changes(self, change_detector_service, sample_drug):
        """Clean up changes past retention period."""
        # Create an expired change
        expired_change = DrugChange(
            drug_id="expired",
            change_type=ChangeType.NEW,
            new_snapshot=sample_drug,
            source="test",
            applied_at=datetime.now(timezone.utc) - timedelta(days=ROLLBACK_DAYS + 5),
        )
        change_detector_service._applied_changes[expired_change.change_id] = (
            expired_change
        )

        # Create a recent change
        recent_change = DrugChange(
            drug_id="recent",
            change_type=ChangeType.NEW,
            new_snapshot=sample_drug,
            source="test",
            applied_at=datetime.now(timezone.utc),
        )
        change_detector_service._applied_changes[recent_change.change_id] = (
            recent_change
        )

        cleaned = await change_detector_service.cleanup_expired_changes()

        assert cleaned >= 1
        assert expired_change.change_id not in change_detector_service._applied_changes
        assert recent_change.change_id in change_detector_service._applied_changes

    def test_get_changeset_summary(self, change_detector_service, sample_drug):
        """Generate changeset summary."""
        changes = [
            DrugChange(
                drug_id="test",
                change_type=ChangeType.NEW,
                new_snapshot=sample_drug,
                source="test",
            )
        ]
        changeset = ChangeSet(changes=changes, source="test")

        summary = change_detector_service.get_changeset_summary(changeset)

        assert summary.total_changes == 1
        assert summary.source == "test"
        assert len(summary.changes) == 1


# Tests for singleton
class TestSingleton:
    """Tests for service singleton pattern."""

    def test_get_change_detector_singleton(self):
        """get_change_detector should return same instance."""
        service1 = get_change_detector()
        service2 = get_change_detector()

        assert service1 is service2
