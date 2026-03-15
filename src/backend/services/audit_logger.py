"""
DrugTree - Audit Logger Service

Comprehensive audit logging with async batch inserts, 90-day retention, and archival support.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from models.audit import (
    AuditAction,
    AuditActor,
    AuditBatch,
    AuditLog,
    AuditQuery,
    AuditSummary,
    BATCH_INSERT_THRESHOLD,
    RETENTION_DAYS_ONLINE,
    RETENTION_DAYS_ARCHIVE,
)
from models.change import DrugChange

logger = logging.getLogger(__name__)


class AuditLoggerService:
    """
    Service for comprehensive audit logging.

    Features:
    - Async batch inserts (>100 logs/sec)
    - 90-day online retention
    - Archive to filesystem
    - Query endpoints with filtering
    - Middleware for automatic API logging
    - Compliance export
    """

    def __init__(
        self,
        logs_path: Optional[Path] = None,
        archive_path: Optional[Path] = None,
        batch_size: int = BATCH_INSERT_THRESHOLD,
    ):
        """
        Initialize audit logger service.

        Args:
            logs_path: Path to store active logs
            archive_path: Path to store archived logs
            batch_size: Number of logs before batch insert
        """
        self.logs_path = logs_path or Path("data/audit_logs")
        self.archive_path = archive_path or self.logs_path / "archive"
        self.batch_size = batch_size

        # Create directories
        self.logs_path.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)

        # In-memory buffer for batch inserts
        self._pending_logs: List[AuditLog] = []
        self._log_buffer: Dict[str, AuditLog] = {}

        # Lock for thread-safe batch operations
        self._lock = asyncio.Lock()

    async def log(
        self,
        action: AuditAction,
        entity_type: str,
        actor: AuditActor,
        entity_id: Optional[str] = None,
        before_value: Optional[Dict[str, Any]] = None,
        after_value: Optional[Dict[str, Any]] = None,
        field_changes: Optional[List[str]] = None,
        source: str = "unknown",
        success: bool = True,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        correlation_id: Optional[str] = None,
        parent_log_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Create and queue an audit log entry.

        Args:
            action: Type of action performed
            entity_type: Type of entity affected
            actor: Who performed the action
            entity_id: ID of affected entity
            before_value: State before change
            after_value: State after change
            field_changes: Fields that changed
            source: Source system/module
            success: Whether action succeeded
            error_message: Error if failed
            error_code: Error code if applicable
            correlation_id: ID to correlate related actions
            parent_log_id: Parent log for hierarchical actions
            metadata: Additional context data

        Returns:
            Created AuditLog entry
        """
        log_id = f"log_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"

        log_entry = AuditLog(
            log_id=log_id,
            timestamp=datetime.utcnow(),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            before_value=AuditLog.sanitize_value(before_value)
            if before_value
            else None,
            after_value=AuditLog.sanitize_value(after_value) if after_value else None,
            field_changes=field_changes,
            source=source,
            success=success,
            error_message=error_message,
            error_code=error_code,
            correlation_id=correlation_id,
            parent_log_id=parent_log_id,
            metadata=metadata or {},
        )

        # Add to buffer
        async with self._lock:
            self._pending_logs.append(log_entry)
            self._log_buffer[log_id] = log_entry

            # Flush if batch size reached
            if len(self._pending_logs) >= self.batch_size:
                await self._flush_batch()

        logger.debug(f"Logged audit entry: {log_id} - {action.value}")
        return log_entry

    async def log_drug_change(
        self,
        change: DrugChange,
        actor: AuditActor,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """
        Log a drug data change.

        Args:
            change: DrugChange to log
            actor: Who performed the action
            success: Whether change succeeded
            error_message: Error if failed

        Returns:
            Created AuditLog entry
        """
        action_map = {
            "new": AuditAction.DRUG_CREATE,
            "updated": AuditAction.DRUG_UPDATE,
            "deprecated": AuditAction.DRUG_DEPRECATED,
            "restored": AuditAction.DRUG_RESTORED,
        }

        return await self.log(
            action=action_map.get(change.change_type.value, AuditAction.DRUG_UPDATE),
            entity_type="drug",
            entity_id=change.drug_id,
            actor=actor,
            before_value=change.old_snapshot,
            after_value=change.new_snapshot,
            field_changes=[fc.field_name for fc in change.field_changes],
            source=change.source,
            success=success,
            error_message=error_message,
            correlation_id=change.change_id,
        )

    async def log_sync_event(
        self,
        status: str,
        actor: AuditActor,
        drugs_processed: int = 0,
        changes_detected: int = 0,
        errors: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> AuditLog:
        """
        Log a sync operation event.

        Args:
            status: 'started', 'completed', or 'failed'
            actor: Who/what triggered the sync
            drugs_processed: Number of drugs processed
            changes_detected: Number of changes detected
            errors: List of error messages
            correlation_id: Sync job ID

        Returns:
            Created AuditLog entry
        """
        action_map = {
            "started": AuditAction.SYNC_STARTED,
            "completed": AuditAction.SYNC_COMPLETED,
            "failed": AuditAction.SYNC_FAILED,
        }

        return await self.log(
            action=action_map[status],
            entity_type="sync",
            actor=actor,
            source="update_scheduler",
            success=(status != "failed"),
            error_message="\n".join(errors) if errors else None,
            correlation_id=correlation_id,
            metadata={
                "drugs_processed": drugs_processed,
                "changes_detected": changes_detected,
                "error_count": len(errors) if errors else 0,
            },
        )

    async def log_api_call(
        self,
        method: str,
        path: str,
        actor: AuditActor,
        status_code: int,
        response_time_ms: float,
        request_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> AuditLog:
        """
        Log an API call.

        Args:
            method: HTTP method
            path: Request path
            actor: Who made the request
            status_code: Response status code
            response_time_ms: Response time in milliseconds
            request_id: Request ID
            error: Error message if failed

        Returns:
            Created AuditLog entry
        """
        return await self.log(
            action=AuditAction.API_ERROR if error else AuditAction.API_CALL,
            entity_type="api",
            entity_id=request_id,
            actor=actor,
            source="api_middleware",
            success=(error is None),
            error_message=error,
            correlation_id=request_id,
            metadata={
                "method": method,
                "path": path,
                "status_code": status_code,
                "response_time_ms": response_time_ms,
            },
        )

    async def query_logs(
        self,
        query: AuditQuery,
    ) -> List[AuditLog]:
        """
        Query audit logs with filters.

        Args:
            query: Query parameters

        Returns:
            List of matching AuditLog entries
        """
        results = []

        # Check in-memory buffer
        for log in self._log_buffer.values():
            if self._matches_query(log, query):
                results.append(log)

        # Check disk files
        for log_file in self.logs_path.glob("*.json"):
            if not query.include_archived and log_file.parent == self.archive_path:
                continue

            try:
                with open(log_file) as f:
                    data = json.load(f)
                log = AuditLog(**data)

                if self._matches_query(log, query):
                    results.append(log)
            except Exception as e:
                logger.warning(f"Failed to load log {log_file}: {e}")

        # Sort by timestamp (newest first)
        results.sort(key=lambda x: x.timestamp, reverse=True)

        # Apply pagination
        return results[query.offset : query.offset + query.limit]

    def _matches_query(self, log: AuditLog, query: AuditQuery) -> bool:
        """Check if log matches query filters."""
        if query.start_date and log.timestamp < query.start_date:
            return False
        if query.end_date and log.timestamp > query.end_date:
            return False
        if query.actions and log.action not in query.actions:
            return False
        if query.entity_type and log.entity_type != query.entity_type:
            return False
        if query.entity_id and log.entity_id != query.entity_id:
            return False
        if query.actor_type and log.actor.type != query.actor_type:
            return False
        if query.actor_id and log.actor.id != query.actor_id:
            return False
        if query.success_only is not None and log.success != query.success_only:
            return False
        if not query.include_archived and log.archived:
            return False
        return True

    async def get_summary(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AuditSummary:
        """
        Get summary of audit activity in period.

        Args:
            start_date: Period start
            end_date: Period end

        Returns:
            AuditSummary with statistics
        """
        query = AuditQuery(
            start_date=start_date,
            end_date=end_date,
            include_archived=False,
            limit=10000,  # Large limit for summary calculation
        )

        logs = await self.query_logs(query)

        by_action: Dict[str, int] = {}
        by_entity_type: Dict[str, int] = {}
        by_actor_type: Dict[str, int] = {}
        errors: List[Dict[str, Any]] = []
        success_count = 0

        for log in logs:
            # Count by action
            action_key = log.action.value
            by_action[action_key] = by_action.get(action_key, 0) + 1

            # Count by entity type
            by_entity_type[log.entity_type] = by_entity_type.get(log.entity_type, 0) + 1

            # Count by actor type
            by_actor_type[log.actor.type] = by_actor_type.get(log.actor.type, 0) + 1

            # Count successes
            if log.success:
                success_count += 1
            else:
                errors.append(
                    {
                        "log_id": log.log_id,
                        "action": log.action.value,
                        "error_message": log.error_message,
                        "timestamp": log.timestamp.isoformat(),
                    }
                )

        return AuditSummary(
            period_start=start_date,
            period_end=end_date,
            total_logs=len(logs),
            by_action=by_action,
            by_entity_type=by_entity_type,
            by_actor_type=by_actor_type,
            success_rate=(success_count / len(logs) * 100) if logs else 100.0,
            errors=errors[:50],  # Limit errors in summary
        )

    async def export_logs(
        self,
        start_date: datetime,
        end_date: datetime,
        output_path: Path,
    ) -> int:
        """
        Export logs to JSON file for compliance.

        Args:
            start_date: Export start date
            end_date: Export end date
            output_path: Path to export file

        Returns:
            Number of logs exported
        """
        query = AuditQuery(
            start_date=start_date,
            end_date=end_date,
            include_archived=True,
            limit=100000,
        )

        logs = await self.query_logs(query)

        export_data = {
            "export_timestamp": datetime.utcnow().isoformat(),
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "total_logs": len(logs),
            "logs": [log.model_dump() for log in logs],
        }

        with open(output_path, "w") as f:
            json.dump(export_data, f, default=str, indent=2)

        logger.info(f"Exported {len(logs)} audit logs to {output_path}")
        return len(logs)

    async def rotate_logs(self) -> Dict[str, int]:
        """
        Rotate logs: archive old logs, delete expired archives.

        Returns:
            Dict with counts of archived and deleted logs
        """
        cutoff_online = datetime.utcnow() - timedelta(days=RETENTION_DAYS_ONLINE)
        cutoff_archive = datetime.utcnow() - timedelta(days=RETENTION_DAYS_ARCHIVE)

        archived_count = 0
        deleted_count = 0

        # Archive old online logs
        for log_file in self.logs_path.glob("*.json"):
            if log_file.parent == self.archive_path:
                continue

            try:
                with open(log_file) as f:
                    data = json.load(f)
                log = AuditLog(**data)

                if log.timestamp < cutoff_online and not log.archived:
                    # Move to archive
                    archive_file = self.archive_path / log_file.name
                    log.archived = True
                    log.archived_at = datetime.utcnow()
                    log.archive_location = str(archive_file)

                    with open(archive_file, "w") as f:
                        json.dump(log.model_dump(), f, default=str)

                    log_file.unlink()
                    archived_count += 1
            except Exception as e:
                logger.warning(f"Failed to archive log {log_file}: {e}")

        # Delete expired archives
        for archive_file in self.archive_path.glob("*.json"):
            try:
                with open(archive_file) as f:
                    data = json.load(f)
                log = AuditLog(**data)

                if log.timestamp < cutoff_archive:
                    archive_file.unlink()
                    deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete archive {archive_file}: {e}")

        logger.info(f"Log rotation: archived={archived_count}, deleted={deleted_count}")
        return {
            "archived": archived_count,
            "deleted": deleted_count,
        }

    async def _flush_batch(self) -> None:
        """Flush pending logs to disk."""
        if not self._pending_logs:
            return

        batch = AuditBatch(
            logs=self._pending_logs.copy(),
            batch_id=f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}",
        )

        # Write batch to disk
        batch_file = self.logs_path / f"batch_{batch.batch_id}.json"
        try:
            with open(batch_file, "w") as f:
                json.dump(batch.model_dump(), f, default=str)

            logger.info(f"Flushed {len(self._pending_logs)} audit logs to {batch_file}")
            self._pending_logs.clear()
        except Exception as e:
            logger.error(f"Failed to flush audit batch: {e}")

    async def flush(self) -> None:
        """Force flush all pending logs."""
        async with self._lock:
            await self._flush_batch()

    async def get_log_by_id(self, log_id: str) -> Optional[AuditLog]:
        """
        Get a specific log by ID.

        Args:
            log_id: Log ID to look up

        Returns:
            AuditLog if found, None otherwise
        """
        # Check buffer first
        if log_id in self._log_buffer:
            return self._log_buffer[log_id]

        # Search disk files
        for log_file in self.logs_path.glob("**/*.json"):
            try:
                with open(log_file) as f:
                    data = json.load(f)

                # Handle both single logs and batches
                if "logs" in data:
                    # This is a batch file
                    for log_data in data["logs"]:
                        if log_data.get("log_id") == log_id:
                            return AuditLog(**log_data)
                else:
                    # Single log file
                    if data.get("log_id") == log_id:
                        return AuditLog(**data)
            except Exception as e:
                logger.warning(f"Failed to search log file {log_file}: {e}")

        return None


# Singleton service instance
_service: Optional[AuditLoggerService] = None


def get_audit_logger() -> AuditLoggerService:
    """Get or create singleton audit logger service."""
    global _service
    if _service is None:
        _service = AuditLoggerService()
    return _service


async def log_audit(
    action: AuditAction,
    entity_type: str,
    actor: AuditActor,
    **kwargs,
) -> AuditLog:
    """
    Convenience function to log an audit event using the singleton service.

    Args:
        action: Type of action performed
        entity_type: Type of entity affected
        actor: Who performed the action
        **kwargs: Additional log fields

    Returns:
        Created AuditLog entry
    """
    return await get_audit_logger().log(
        action=action,
        entity_type=entity_type,
        actor=actor,
        **kwargs,
    )
