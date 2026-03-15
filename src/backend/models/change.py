"""
DrugTree - Change Detection Models

Models for tracking drug data changes, supporting hash-based diffing,
change sets, and 30-day rollback capability.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


ROLLBACK_DAYS = 30

HASH_EXCLUDE_FIELDS = {
    "timestamp",
    "last_synced",
    "updated_at",
    "created_at",
}


class ChangeType(str, Enum):
    """Types of changes that can occur to to drug records"""

    NEW = "new"  # New drug added
    UPDATED = "updated"  # Existing drug modified
    DEPRECATED = "deprecated"  # Drug marked as deprecated
    RESTORED = "restored"  # Previously deprecated drug restored


class ChangePriority(str, Enum):
    """Priority levels for changes"""

    LOW = "low"  # Minor field updates (e.g., synonyms)
    MEDIUM = "medium"  # Standard updates (e.g., molecular_weight)
    HIGH = "high"  # Important updates (e.g., atc_code, targets)
    CRITICAL = "critical"  # Critical updates requiring immediate review


class FieldChange(BaseModel):
    """
    Represents a change to a single field.

    Supports:
    - Priority classification
    - Field-level tracking
    """

    field_name: str = Field(..., description="Name of the changed field")
    old_value: Optional[Any] = Field(default=None, description="Previous value")
    new_value: Optional[Any] = Field(default=None, description="New value")
    priority: ChangePriority = Field(
        default=ChangePriority.MEDIUM, description="Change priority"
    )


class DrugChange(BaseModel):
    """
    Represents a change to a drug record.

    Supports:
    - Tracking old/new values for each changed field
    - Rollback within 30 days
    - Priority classification
    - Provenance of the change
    """

    change_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique change identifier",
    )
    drug_id: str = Field(..., description="ID of the affected drug")
    change_type: ChangeType = Field(..., description="Type of change")
    field_changes: list[FieldChange] = Field(
        default_factory=list, description="List of field-level changes"
    )
    priority: ChangePriority = Field(
        default=ChangePriority.MEDIUM,
        description="Change priority level",
    )

    # Snapshot for rollback
    old_snapshot: Optional[dict[str, Any]] = Field(
        default=None, description="Complete drug state before change (for rollback)"
    )
    new_snapshot: Optional[dict[str, Any]] = Field(
        default=None, description="Complete drug state after change"
    )

    # Metadata
    source: str = Field(
        ..., description="Source that triggered the change (chembl, kegg, manual, etc.)"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the change was detected",
    )
    applied_at: Optional[datetime] = Field(
        default=None, description="When the change was applied to the database"
    )
    applied_by: Optional[str] = Field(
        default=None, description="User or system that applied the change"
    )

    # Status tracking
    reviewed: bool = Field(
        default=False, description="Whether change has been reviewed"
    )
    reviewed_at: Optional[datetime] = Field(default=None, description="When reviewed")
    reviewed_by: Optional[str] = Field(default=None, description="Who reviewed")
    approved: Optional[bool] = Field(default=None, description="Approval status")

    # Rollback support
    rolled_back: bool = Field(
        default=False, description="Whether this change was rolled back"
    )
    rolled_back_at: Optional[datetime] = Field(
        default=None, description="When rolled back"
    )
    rollback_change_id: Optional[str] = Field(
        default=None, description="ID of the rollback change record"
    )

    @property
    def can_rollback(self) -> bool:
        """Check if this change can still be rolled back"""
        if self.rolled_back:
            return False
        if not self.applied_at:
            return False
        rollback_deadline = self.applied_at + timedelta(days=ROLLBACK_DAYS)
        return datetime.now(timezone.utc) <= rollback_deadline

    @property
    def rollback_deadline(self) -> Optional[datetime]:
        """Get the rollback deadline for this change"""
        if not self.applied_at:
            return None
        return self.applied_at + timedelta(days=ROLLBACK_DAYS)

    @model_validator(mode="after")
    def compute_priority_from_fields(self):
        if self.field_changes and self.priority == ChangePriority.MEDIUM:
            max_priority = self._compute_priority_from_fields(self.field_changes)
            if max_priority != ChangePriority.MEDIUM:
                self.priority = max_priority
        return self

    def _compute_priority_from_fields(
        self, field_changes: list[FieldChange]
    ) -> ChangePriority:
        """Compute the highest priority from field changes"""
        priority_order = [
            ChangePriority.CRITICAL,
            ChangePriority.HIGH,
            ChangePriority.MEDIUM,
            ChangePriority.LOW,
        ]

        for priority in priority_order:
            if any(fc.priority == priority for fc in field_changes):
                return priority
        return ChangePriority.LOW


class ChangeSet(BaseModel):
    """
    A collection of changes to be reviewed and potentially applied.

    Generated by the change detector for batch review.
    """

    changeset_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique changeset identifier",
    )
    changes: list[DrugChange] = Field(
        default_factory=list, description="List of changes in this set"
    )
    source: str = Field(..., description="Source of the changes (e.g., weekly_sync)")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When changeset was created",
    )

    # Summary statistics
    @property
    def total_changes(self) -> int:
        return len(self.changes)

    @property
    def new_drugs(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.NEW)

    @property
    def updated_drugs(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.UPDATED)

    @property
    def deprecated_drugs(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.DEPRECATED)

    @property
    def restored_drugs(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.RESTORED)

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.changes if c.priority == ChangePriority.CRITICAL)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of this changeset"""
        return {
            "changeset_id": self.changeset_id,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "total_changes": self.total_changes,
            "by_type": {
                "new": self.new_drugs,
                "updated": self.updated_drugs,
                "deprecated": self.deprecated_drugs,
                "restored": self.restored_drugs,
            },
            "critical_count": self.critical_count,
        }


class ChangeDetector:
    """
    Detects changes between drug records using hash-based comparison.

    Features:
    - SHA-256 hash calculation (excluding timestamp fields)
    - Field-level diff detection
    - Priority classification based on changed fields
    - Rollback support within 30 days
    """

    # Field priority mapping
    FIELD_PRIORITIES: dict[str, ChangePriority] = {
        "atc_code": ChangePriority.CRITICAL,
        "atc_category": ChangePriority.CRITICAL,
        "targets": ChangePriority.HIGH,
        "indication": ChangePriority.HIGH,
        "smiles": ChangePriority.HIGH,
        "inchikey": ChangePriority.HIGH,
        "molecular_weight": ChangePriority.MEDIUM,
        "year_approved": ChangePriority.MEDIUM,
        "generation": ChangePriority.MEDIUM,
        "class_name": ChangePriority.MEDIUM,
        "company": ChangePriority.LOW,
        "synonyms": ChangePriority.LOW,
        "phase": ChangePriority.MEDIUM,
        "parent_drugs": ChangePriority.MEDIUM,
        "clinical_trials": ChangePriority.LOW,
    }

    @classmethod
    def compute_hash(cls, drug_data: dict[str, Any]) -> str:
        """
        Compute SHA-256 hash of drug data, excluding timestamp fields.

        Args:
            drug_data: Drug dictionary to hash

        Returns:
            Hex-encoded SHA-256 hash
        """
        # Create a copy and remove excluded fields
        hash_data = {k: v for k, v in drug_data.items() if k not in HASH_EXCLUDE_FIELDS}

        # Sort keys for consistent hashing
        sorted_json = json.dumps(hash_data, sort_keys=True, default=str)
        return hashlib.sha256(sorted_json.encode()).hexdigest()

    @classmethod
    def detect_field_changes(
        cls,
        old_data: dict[str, Any],
        new_data: dict[str, Any],
    ) -> list[FieldChange]:
        """
        Detect changes between two drug records at the field level.

        Args:
            old_data: Previous drug state
            new_data: New drug state

        Returns:
            List of FieldChange objects
        """
        changes: list[FieldChange] = []

        # Get all fields from both records
        all_fields = set(old_data.keys()) | set(new_data.keys())

        for field in all_fields:
            # Skip excluded fields
            if field in HASH_EXCLUDE_FIELDS:
                continue

            old_value = old_data.get(field)
            new_value = new_data.get(field)

            # Handle list comparison (order-independent)
            if isinstance(old_value, list) or isinstance(new_value, list):
                old_set = set(old_value or [])
                new_set = set(new_value or [])
                if old_set != new_set:
                    changes.append(
                        FieldChange(
                            field_name=field,
                            old_value=sorted(old_value) if old_value else None,
                            new_value=sorted(new_value) if new_value else None,
                            priority=cls.FIELD_PRIORITIES.get(
                                field, ChangePriority.MEDIUM
                            ),
                        )
                    )
            elif old_value != new_value:
                changes.append(
                    FieldChange(
                        field_name=field,
                        old_value=old_value,
                        new_value=new_value,
                        priority=cls.FIELD_PRIORITIES.get(field, ChangePriority.MEDIUM),
                    )
                )

        return changes

    @classmethod
    def detect_change(
        cls,
        old_drug: Optional[dict[str, Any]],
        new_drug: dict[str, Any],
        source: str,
    ) -> Optional[DrugChange]:
        """
        Detect what changed between old and new drug records.

        Args:
            old_drug: Previous drug state (None if new drug)
            new_drug: New drug state
            source: Source of the change

        Returns:
            DrugChange if there are changes, None otherwise
        """
        if old_drug is None:
            # New drug
            field_changes: list[FieldChange] = []
            for k, v in new_drug.items():
                if k not in HASH_EXCLUDE_FIELDS and v is not None:
                    field_changes.append(
                        FieldChange(
                            field_name=k,
                            old_value=None,
                            new_value=v,
                            priority=cls.FIELD_PRIORITIES.get(k, ChangePriority.MEDIUM),
                        )
                    )
            return DrugChange(
                drug_id=new_drug["id"],
                change_type=ChangeType.NEW,
                field_changes=field_changes,
                old_snapshot=None,
                new_snapshot=new_drug,
                source=source,
            )

        # Check if hashes match
        old_hash = cls.compute_hash(old_drug)
        new_hash = cls.compute_hash(new_drug)

        if old_hash == new_hash:
            return None  # No changes

        # Detect field-level changes
        field_changes = cls.detect_field_changes(old_drug, new_drug)

        if not field_changes:
            return None  # Only timestamp changes

        return DrugChange(
            drug_id=new_drug["id"],
            change_type=ChangeType.UPDATED,
            field_changes=field_changes,
            old_snapshot=old_drug,
            new_snapshot=new_drug,
            source=source,
        )

    @classmethod
    def detect_deprecation(
        cls,
        drug: dict[str, Any],
        source: str,
        reason: Optional[str] = None,
    ) -> DrugChange:
        """
        Create a deprecation change record.

        Args:
            drug: Drug to deprecate
            source: Source of the deprecation
            reason: Optional reason for deprecation

        Returns:
            DrugChange marking the drug as deprecated
        """
        return DrugChange(
            drug_id=drug["id"],
            change_type=ChangeType.DEPRECATED,
            field_changes=[
                FieldChange(
                    field_name="deprecated",
                    old_value=False,
                    new_value=True,
                    priority=ChangePriority.HIGH,
                )
            ],
            old_snapshot=drug,
            new_snapshot={**drug, "deprecated": True, "deprecation_reason": reason},
            source=source,
        )

    @classmethod
    def create_rollback_change(
        cls,
        original_change: DrugChange,
        source: str = "manual_rollback",
    ) -> DrugChange:
        """
        Create a rollback change that reverses an original change.

        Args:
            original_change: The change to roll back
            source: Source of the rollback

        Returns:
            DrugChange that reverses the original

        Raises:
            ValueError: If change cannot be rolled back
        """
        if not original_change.can_rollback:
            raise ValueError(
                f"Change {original_change.change_id} cannot be rolled back. "
                f"Deadline was {original_change.rollback_deadline}"
            )

        # Swap old and new snapshots
        field_changes = [
            FieldChange(
                field_name=fc.field_name,
                old_value=fc.new_value,
                new_value=fc.old_value,
                priority=fc.priority,
            )
            for fc in original_change.field_changes
        ]

        change_type = (
            ChangeType.RESTORED
            if original_change.change_type == ChangeType.DEPRECATED
            else ChangeType.UPDATED
        )

        return DrugChange(
            drug_id=original_change.drug_id,
            change_type=change_type,
            field_changes=field_changes,
            old_snapshot=original_change.new_snapshot,
            new_snapshot=original_change.old_snapshot,
            source=source,
            rollback_change_id=original_change.change_id,
        )


class ChangeSetSummary(BaseModel):
    """Summary response for API endpoints"""

    changeset_id: str
    source: str
    created_at: datetime
    total_changes: int
    by_type: dict[str, int]
    critical_count: int
    changes: list[dict[str, Any]] = Field(default_factory=list)
