"""
DrugTree - Audit Models

Pydantic models for audit logging with 90-day retention and compliance support.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import json


class AuditAction(str, Enum):
    """Types of auditable actions."""

    # Data operations
    DRUG_CREATE = "drug_create"
    DRUG_UPDATE = "drug_update"
    DRUG_DELETE = "drug_delete"
    DRUG_DEPRECATED = "drug_deprecated"
    DRUG_RESTORED = "drug_restored"

    # Sync operations
    SYNC_STARTED = "sync_started"
    SYNC_COMPLETED = "sync_completed"
    SYNC_FAILED = "sync_failed"

    # Change management
    CHANGE_APPLIED = "change_applied"
    CHANGE_ROLLED_BACK = "change_rolled_back"
    CHANGE_APPROVED = "change_approved"

    # API operations
    API_CALL = "api_call"
    API_ERROR = "api_error"
    API_AUTH = "api_auth"

    # Admin operations
    ADMIN_TRIGGER_SYNC = "admin_trigger_sync"
    ADMIN_FORCE_UPDATE = "admin_force_update"
    ADMIN_CONFIG_CHANGE = "admin_config_change"

    # System operations
    VALIDATION_RUN = "validation_run"
    CLEANUP_RUN = "cleanup_run"
    BACKUP_CREATED = "backup_created"


class AuditActor(BaseModel):
    """Identity of who performed an action."""

    type: str = Field(..., description="Type of actor: 'user', 'system', 'api'")
    id: Optional[str] = Field(None, description="User ID or system identifier")
    name: Optional[str] = Field(None, description="Human-readable name")
    ip_address: Optional[str] = Field(
        None, description="IP address for external requests"
    )
    user_agent: Optional[str] = Field(None, description="User agent for API calls")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "user",
                    "id": "user_123",
                    "name": "John Doe",
                    "ip_address": "192.168.1.1",
                },
                {
                    "type": "system",
                    "id": "scheduler",
                    "name": "Weekly Sync Job",
                },
            ]
        }
    }


class AuditLog(BaseModel):
    """
    Comprehensive audit log entry.

    Features:
    - 90-day online retention
    - Sensitive data filtering
    - JSON export for compliance
    - Async batch insert support
    """

    # Identification
    log_id: str = Field(..., description="Unique log entry ID")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the action occurred"
    )

    # Action details
    action: AuditAction = Field(..., description="Type of action performed")
    entity_type: str = Field(
        ..., description="Type of entity: 'drug', 'sync', 'change', 'api'"
    )
    entity_id: Optional[str] = Field(None, description="ID of affected entity")

    # Actor information
    actor: AuditActor = Field(..., description="Who performed the action")

    # Change tracking
    before_value: Optional[Dict[str, Any]] = Field(
        None, description="State before change (sanitized)"
    )
    after_value: Optional[Dict[str, Any]] = Field(
        None, description="State after change (sanitized)"
    )
    field_changes: Optional[List[str]] = Field(
        None, description="List of fields that changed"
    )

    # Context
    source: str = Field(default="unknown", description="Source system or module")
    correlation_id: Optional[str] = Field(
        None, description="ID to correlate related actions"
    )
    parent_log_id: Optional[str] = Field(
        None, description="Parent log entry for hierarchical actions"
    )

    # Result
    success: bool = Field(default=True, description="Whether action succeeded")
    error_message: Optional[str] = Field(None, description="Error if action failed")
    error_code: Optional[str] = Field(None, description="Error code if applicable")

    # Additional metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context-specific data"
    )

    # Retention
    retention_days: int = Field(default=90, description="Days to retain online")
    archived: bool = Field(
        default=False, description="Whether archived to cold storage"
    )
    archived_at: Optional[datetime] = Field(None, description="When archived")
    archive_location: Optional[str] = Field(None, description="Archive path/URL")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "log_id": "log_20240101_abc123",
                    "timestamp": "2024-01-01T10:30:00Z",
                    "action": "drug_update",
                    "entity_type": "drug",
                    "entity_id": "atorvastatin",
                    "actor": {
                        "type": "system",
                        "id": "weekly_sync",
                        "name": "Weekly Data Sync",
                    },
                    "before_value": {"molecular_weight": 348.48},
                    "after_value": {"molecular_weight": 350.00},
                    "field_changes": ["molecular_weight"],
                    "source": "change_detector",
                    "success": True,
                }
            ]
        }
    }

    def to_json(self) -> str:
        """Export to JSON for compliance."""
        return self.model_dump_json(indent=2)

    @property
    def is_expired(self) -> bool:
        """Check if log entry is past retention period."""
        if self.archived:
            return True
        age = datetime.utcnow() - self.timestamp
        return age.days > self.retention_days

    @staticmethod
    def sanitize_value(value: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove sensitive data from values before logging.

        Sensitive fields are replaced with [REDACTED].
        """
        SENSITIVE_FIELDS = {
            "api_key",
            "password",
            "secret",
            "token",
            "credential",
            "auth_header",
            "authorization",
            "smtp_password",
            "database_password",
            "slack_webhook_url",
        }

        if not value:
            return value

        sanitized = {}
        for key, val in value.items():
            if key.lower() in SENSITIVE_FIELDS:
                sanitized[key] = "[REDACTED]"
            elif isinstance(val, dict):
                sanitized[key] = AuditLog.sanitize_value(val)
            elif isinstance(val, str) and any(
                sensitive in val.lower()
                for sensitive in ["password", "api_key", "secret"]
            ):
                # Check if string contains sensitive data
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = val

        return sanitized


class AuditQuery(BaseModel):
    """Query parameters for audit log search."""

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    actions: Optional[List[AuditAction]] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    actor_type: Optional[str] = None
    actor_id: Optional[str] = None
    success_only: Optional[bool] = None
    include_archived: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AuditBatch(BaseModel):
    """Batch of audit logs for efficient insertion."""

    logs: List[AuditLog] = Field(default_factory=list)
    batch_id: str = Field(..., description="Batch identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def size(self) -> int:
        """Number of logs in batch."""
        return len(self.logs)

    def add_log(self, log: AuditLog) -> None:
        """Add a log entry to the batch."""
        self.logs.append(log)


class AuditSummary(BaseModel):
    """Summary of audit activity."""

    period_start: datetime
    period_end: datetime

    total_logs: int
    by_action: Dict[str, int]
    by_entity_type: Dict[str, int]
    by_actor_type: Dict[str, int]

    success_rate: float = Field(..., description="Percentage of successful actions")

    errors: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of error details"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "period_start": "2024-01-01T00:00:00Z",
                    "period_end": "2024-01-31T23:59:59Z",
                    "total_logs": 1250,
                    "by_action": {
                        "drug_update": 500,
                        "api_call": 450,
                        "sync_completed": 4,
                    },
                    "by_entity_type": {"drug": 500, "api": 450, "sync": 4},
                    "by_actor_type": {"system": 504, "user": 450, "api": 296},
                    "success_rate": 99.2,
                    "errors": [],
                }
            ]
        }
    }


# Constants
AUDIT_LOGS_TABLE = "audit_logs"
RETENTION_DAYS_ONLINE = 90
RETENTION_DAYS_ARCHIVE = 365  # Keep archives for 1 year
BATCH_INSERT_THRESHOLD = 100  # Batch inserts when this many logs pending
