"""
DrugTree - Change Detection Service

Service for detecting, applying, and rolling back drug data changes.
Implements hash-based diffing with 30-day rollback support.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from models.change import (
    ChangeDetector,
    ChangeSet,
    ChangeSetSummary,
    ChangeType,
    DrugChange,
    ROLLBACK_DAYS,
)
from models.drug import Drug

logger = logging.getLogger(__name__)


class ChangeDetectorService:
    """
    Service for managing drug data changes.

    Features:
    - Hash-based change detection
    - Change set generation and review
    - Apply/rollback changes
    - 30-day rollback window
    - Change history tracking
    """

    def __init__(
        self,
        data_path: Optional[Path] = None,
        changes_path: Optional[Path] = None,
    ):
        """
        Initialize change detector service.

        Args:
            data_path: Path to drug data files
            changes_path: Path to store change history
        """
        self.data_path = data_path or Path("data")
        self.changes_path = changes_path or self.data_path / "changes"
        self.changes_path.mkdir(parents=True, exist_ok=True)

        # In-memory change tracking (in production, use database)
        self._pending_changes: Dict[str, DrugChange] = {}
        self._applied_changes: Dict[str, DrugChange] = {}
        self._drug_hashes: Dict[str, str] = {}

    async def detect_all_changes(
        self,
        old_drugs: List[Dict[str, Any]],
        new_drugs: List[Dict[str, Any]],
        source: str = "weekly_sync",
    ) -> ChangeSet:
        """
        Detect all changes between old and new drug datasets.

        Args:
            old_drugs: Previous drug dataset
            new_drugs: New drug dataset
            source: Source of the changes

        Returns:
            ChangeSet with all detected changes
        """
        changes = []

        # Index drugs by ID
        old_index = {d["id"]: d for d in old_drugs}
        new_index = {d["id"]: d for d in new_drugs}

        # Detect new drugs
        for drug_id in new_index:
            if drug_id not in old_index:
                change = ChangeDetector.detect_change(None, new_index[drug_id], source)
                if change:
                    changes.append(change)
                    logger.info(f"Detected new drug: {drug_id}")

        # Detect updates and deprecations
        for drug_id in old_index:
            if drug_id in new_index:
                # Check for updates
                change = ChangeDetector.detect_change(
                    old_index[drug_id], new_index[drug_id], source
                )
                if change:
                    changes.append(change)
                    logger.debug(f"Detected update for drug: {drug_id}")
            else:
                # Drug was removed - mark as deprecated
                change = ChangeDetector.detect_deprecation(
                    old_index[drug_id], source, reason="Removed from source data"
                )
                changes.append(change)
                logger.info(f"Detected deprecated drug: {drug_id}")

        changeset = ChangeSet(
            changes=changes,
            source=source,
        )

        logger.info(
            f"Change detection complete: {len(changes)} changes "
            f"({changeset.new_drugs} new, {changeset.updated_drugs} updated, "
            f"{changeset.deprecated_drugs} deprecated)"
        )

        return changeset

    async def detect_single_change(
        self,
        old_drug: Optional[Dict[str, Any]],
        new_drug: Dict[str, Any],
        source: str,
    ) -> Optional[DrugChange]:
        """
        Detect changes for a single drug.

        Args:
            old_drug: Previous drug state (None if new)
            new_drug: New drug state
            source: Source of the change

        Returns:
            DrugChange if changes detected, None otherwise
        """
        return ChangeDetector.detect_change(old_drug, new_drug, source)

    def compute_drug_hash(self, drug: Dict[str, Any]) -> str:
        """
        Compute hash for a drug record.

        Args:
            drug: Drug dictionary

        Returns:
            SHA-256 hash string
        """
        return ChangeDetector.compute_hash(drug)

    async def apply_change(
        self,
        change: DrugChange,
        applied_by: Optional[str] = None,
    ) -> bool:
        """
        Apply a change to the drug database.

        Args:
            change: DrugChange to apply
            applied_by: User/system that applied the change

        Returns:
            True if applied successfully
        """
        if change.change_id in self._applied_changes:
            logger.warning(f"Change {change.change_id} already applied")
            return False

        try:
            # In production, this would update the database
            # For now, we just track it in memory
            change.applied_at = datetime.now(timezone.utc)
            change.applied_by = applied_by or "system"

            self._applied_changes[change.change_id] = change

            # Update drug hash
            if change.new_snapshot:
                self._drug_hashes[change.drug_id] = self.compute_drug_hash(
                    change.new_snapshot
                )

            # Save change to disk for persistence
            await self._save_change(change)

            logger.info(f"Applied change {change.change_id} for drug {change.drug_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to apply change {change.change_id}: {e}")
            return False

    async def apply_changeset(
        self,
        changeset: ChangeSet,
        applied_by: Optional[str] = None,
        filter_critical_only: bool = False,
    ) -> Tuple[int, int]:
        """
        Apply all changes in a changeset.

        Args:
            changeset: ChangeSet to apply
            applied_by: User/system applying changes
            filter_critical_only: If True, only apply critical changes

        Returns:
            Tuple of (success_count, failure_count)
        """
        success = 0
        failure = 0

        changes_to_apply = changeset.changes
        if filter_critical_only:
            from models.change import ChangePriority

            changes_to_apply = [
                c for c in changes_to_apply if c.priority == ChangePriority.CRITICAL
            ]

        for change in changes_to_apply:
            if await self.apply_change(change, applied_by):
                success += 1
            else:
                failure += 1

        logger.info(
            f"Applied changeset {changeset.changeset_id}: "
            f"{success} successful, {failure} failed"
        )

        return success, failure

    async def rollback_change(
        self,
        change_id: str,
        rolled_back_by: Optional[str] = None,
    ) -> Optional[DrugChange]:
        """
        Rollback a previously applied change.

        Args:
            change_id: ID of change to rollback
            rolled_back_by: User/system performing rollback

        Returns:
            Rollback DrugChange if successful, None otherwise

        Raises:
            ValueError: If change cannot be rolled back
        """
        if change_id not in self._applied_changes:
            logger.error(f"Change {change_id} not found in applied changes")
            return None

        original = self._applied_changes[change_id]

        if not original.can_rollback:
            raise ValueError(
                f"Change {change_id} cannot be rolled back. "
                f"Deadline was {original.rollback_deadline}"
            )

        try:
            # Create rollback change
            rollback = ChangeDetector.create_rollback_change(
                original, source=f"rollback_by_{rolled_back_by or 'system'}"
            )
            rollback.rolled_back_at = datetime.now(timezone.utc)

            # Apply the rollback
            await self.apply_change(rollback, rolled_back_by)

            # Mark original as rolled back
            original.rolled_back = True
            original.rolled_back_at = datetime.now(timezone.utc)
            original.rollback_change_id = rollback.change_id

            logger.info(
                f"Rolled back change {change_id}, "
                f"created rollback change {rollback.change_id}"
            )

            return rollback

        except Exception as e:
            logger.error(f"Failed to rollback change {change_id}: {e}")
            return None

    async def get_change(self, change_id: str) -> Optional[DrugChange]:
        """
        Get a change by ID.

        Args:
            change_id: Change ID to look up

        Returns:
            DrugChange if found, None otherwise
        """
        if change_id in self._applied_changes:
            return self._applied_changes[change_id]
        if change_id in self._pending_changes:
            return self._pending_changes[change_id]

        # Try to load from disk
        change_file = self.changes_path / f"{change_id}.json"
        if change_file.exists():
            try:
                with open(change_file) as f:
                    data = json.load(f)
                return DrugChange(**data)
            except Exception as e:
                logger.error(f"Failed to load change {change_id}: {e}")

        return None

    async def get_drug_history(
        self,
        drug_id: str,
        limit: int = 50,
    ) -> List[DrugChange]:
        """
        Get change history for a specific drug.

        Args:
            drug_id: Drug ID to look up
            limit: Maximum number of changes to return

        Returns:
            List of DrugChange objects for the drug
        """
        changes = []

        # Check applied changes
        for change in self._applied_changes.values():
            if change.drug_id == drug_id:
                changes.append(change)

        # Sort by timestamp (newest first)
        changes.sort(key=lambda c: c.timestamp, reverse=True)

        return changes[:limit]

    async def get_rollback_eligible(self) -> List[DrugChange]:
        """
        Get all changes that are still within rollback window.

        Returns:
            List of changes that can be rolled back
        """
        eligible = []
        for change in self._applied_changes.values():
            if change.can_rollback:
                eligible.append(change)

        # Sort by timestamp (oldest first - closest to deadline)
        eligible.sort(key=lambda c: c.applied_at or datetime.min)

        return eligible

    async def cleanup_expired_changes(self) -> int:
        """
        Remove changes older than rollback window.

        Returns:
            Number of changes cleaned up
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=ROLLBACK_DAYS)
        cleaned = 0

        to_remove = []
        for change_id, change in self._applied_changes.items():
            if change.applied_at and change.applied_at < cutoff:
                to_remove.append(change_id)

        for change_id in to_remove:
            del self._applied_changes[change_id]
            cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired changes")

        return cleaned

    async def _save_change(self, change: DrugChange) -> None:
        """Save change to disk for persistence."""
        change_file = self.changes_path / f"{change.change_id}.json"
        try:
            with open(change_file, "w") as f:
                json.dump(change.model_dump(), f, default=str, indent=2)
        except Exception as e:
            logger.error(f"Failed to save change {change.change_id}: {e}")

    def get_changeset_summary(self, changeset: ChangeSet) -> ChangeSetSummary:
        """
        Get a summary of a changeset for API responses.

        Args:
            changeset: ChangeSet to summarize

        Returns:
            ChangeSetSummary with key statistics
        """
        return ChangeSetSummary(
            changeset_id=changeset.changeset_id,
            source=changeset.source,
            created_at=changeset.created_at,
            total_changes=changeset.total_changes,
            by_type={
                "new": changeset.new_drugs,
                "updated": changeset.updated_drugs,
                "deprecated": changeset.deprecated_drugs,
                "restored": changeset.restored_drugs,
            },
            critical_count=changeset.critical_count,
            changes=[
                {
                    "change_id": c.change_id,
                    "drug_id": c.drug_id,
                    "change_type": c.change_type.value,
                    "priority": c.priority.value,
                    "fields_changed": [fc.field_name for fc in c.field_changes],
                }
                for c in changeset.changes
            ],
        )


# Singleton service instance
_service: Optional[ChangeDetectorService] = None


def get_change_detector() -> ChangeDetectorService:
    """Get or create singleton change detector service."""
    global _service
    if _service is None:
        _service = ChangeDetectorService()
    return _service
