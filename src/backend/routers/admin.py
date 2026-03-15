"""
DrugTree - Admin Router

Administrative endpoints for data sync, rollback, and audit log queries.

NOTE: All admin endpoints require authentication.
Add appropriate authentication middleware to this router
or ensure it protected by route-level authentication.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from models.audit import (
    AuditAction,
    AuditActor,
    AuditLog,
    AuditQuery,
    AuditSummary,
)
from models.change import (
    ChangeSetSummary,
    ChangeType,
)
from services.audit_logger import get_audit_logger
from services.change_detector import get_change_detector
from services.update_scheduler import get_scheduler
from services.validation_pipeline import get_validation_pipeline


router = APIRouter(prefix="/admin", tags=["admin"])


# Request/Response Models
class TriggerSyncRequest(BaseModel):
    """Request to trigger manual sync."""

    source: Optional[str] = Field(None, description="Specific source to sync")
    force: bool = Field(default=False, description="Force sync even if one is running")


class TriggerSyncResponse(BaseModel):
    """Response from trigger sync."""

    success: bool
    message: str
    job_id: Optional[str] = None


class RollbackRequest(BaseModel):
    """Request to rollback a change."""

    reason: Optional[str] = Field(None, description="Reason for rollback")


class RollbackResponse(BaseModel):
    """Response from rollback."""

    success: bool
    message: str
    rollback_change_id: Optional[str] = None


class AuditLogListResponse(BaseModel):
    """Response for audit log list."""

    total: int
    logs: List[AuditLog]


class ValidationReportResponse(BaseModel):
    """Response for validation report."""

    report_id: str
    timestamp: datetime
    overall_status: str
    summary: dict
    metrics: dict
    alerts: List[str]


class DataQualityHealthResponse(BaseModel):
    """Response for data quality health check."""

    status: str
    last_validation: Optional[datetime]
    atc_coverage: float
    provenance_coverage: float
    structure_validity: float
    total_drugs: int
    validation_summary: dict
    alerts: List[str]


# Endpoints
@router.post("/trigger-sync", response_model=TriggerSyncResponse)
async def trigger_sync(request: TriggerSyncRequest) -> TriggerSyncResponse:
    """
    Trigger a manual data synchronization.

    This endpoint allows administrators to manually trigger a data sync
    outside of the scheduled weekly sync.

    **Authentication Required**: Admin role

    **Rate Limited**: 1 request per 5 minutes
    """
    scheduler = get_scheduler()

    try:
        # Check if sync is already running
        status = scheduler.get_sync_status()
        if status.get("running") and not request.force:
            return TriggerSyncResponse(
                success=False,
                message="Sync already in progress. Use force=true to override.",
            )

        # Trigger sync
        sources = [request.source] if request.source else None
        await scheduler.trigger_manual_sync(sources=sources)

        return TriggerSyncResponse(
            success=True,
            message="Sync triggered successfully",
            job_id=status.get("current_job_id"),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger sync: {str(e)}")


@router.post("/rollback/{change_id}", response_model=RollbackResponse)
async def rollback_change(
    change_id: str,
    request: RollbackRequest,
) -> RollbackResponse:
    """
    Rollback a previously applied change.

    **Constraints**:
    - Change must have been applied within the last 30 days
    - Change must not already be rolled back
    - Requires admin authentication

    **Path Parameters**:
    - change_id: Unique identifier of the change to rollback

    **Request Body**:
    - reason: Optional reason for the rollback
    """
    detector = get_change_detector()
    audit_logger = get_audit_logger()

    try:
        # Get the original change
        original = await detector.get_change(change_id)
        if not original:
            raise HTTPException(status_code=404, detail=f"Change {change_id} not found")

        # Attempt rollback
        rollback = await detector.rollback_change(
            change_id,
            rolled_back_by="admin_api",
        )

        if not rollback:
            return RollbackResponse(
                success=False,
                message="Rollback failed - check if change is within 30-day window",
            )

        # Log the rollback action
        await audit_logger.log(
            action=AuditAction.CHANGE_ROLLED_BACK,
            entity_type="change",
            entity_id=change_id,
            actor=AuditActor(
                type="user",
                id="admin_api",
                name=None,
                ip_address=None,
                user_agent=None,
            ),
            source="admin_api",
            metadata={
                "original_change_id": change_id,
                "rollback_change_id": rollback.change_id,
                "reason": request.reason,
            },
        )

        return RollbackResponse(
            success=True,
            message=f"Change {change_id} rolled back successfully",
            rollback_change_id=rollback.change_id,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def query_audit_logs(
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    action: Optional[List[AuditAction]] = Query(None, description="Filter by actions"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    actor_type: Optional[str] = Query(None, description="Filter by actor type"),
    success_only: Optional[bool] = Query(
        None, description="Show only successful actions"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Result offset"),
) -> AuditLogListResponse:
    """
    Query audit logs with filters.

    **Authentication Required**: Admin role

    **Query Parameters**:
    - start_date: Filter logs from this date
    - end_date: Filter logs until this date
    - action: Filter by action types (can specify multiple)
    - entity_type: Filter by entity type (drug, sync, change, api)
    - entity_id: Filter by specific entity ID
    - actor_type: Filter by actor type (user, system, api)
    - success_only: Only show successful actions
    - limit: Maximum number of results (1-1000)
    - offset: Pagination offset
    """
    audit_logger = get_audit_logger()

    query = AuditQuery(
        start_date=start_date,
        end_date=end_date,
        actions=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_type=actor_type,
        success_only=success_only,
        limit=limit,
        offset=offset,
        include_archived=False,
    )

    try:
        logs = await audit_logger.query_logs(query)

        return AuditLogListResponse(
            total=len(logs),  # Note: This should be total matching, not just returned
            logs=logs,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to query audit logs: {str(e)}"
        )


@router.get("/audit-logs/summary", response_model=AuditSummary)
async def get_audit_summary(
    start_date: datetime = Query(..., description="Period start date"),
    end_date: datetime = Query(..., description="Period end date"),
) -> AuditSummary:
    """
    Get summary of audit activity for a period.

    **Authentication Required**: Admin role

    **Query Parameters**:
    - start_date: Period start date (required)
    - end_date: Period end date (required)
    """
    audit_logger = get_audit_logger()

    try:
        summary = await audit_logger.get_summary(start_date, end_date)
        return summary

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get audit summary: {str(e)}"
        )


@router.get("/validation-reports")
async def list_validation_reports(
    limit: int = Query(10, ge=1, le=100),
) -> List[ValidationReportResponse]:
    """
    List recent validation reports.

    **Authentication Required**: Admin role

    **Query Parameters**:
    - limit: Maximum number of reports to return
    """
    reports_path = Path("data/reports")
    reports = []

    if not reports_path.exists():
        return []

    # Get all report files
    report_files = sorted(
        reports_path.glob("validation_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for report_file in report_files[:limit]:
        try:
            import json

            with open(report_file) as f:
                data = json.load(f)

            reports.append(
                ValidationReportResponse(
                    report_id=data["report_id"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    overall_status=data["overall_status"],
                    summary=data["summary"],
                    metrics=data["metrics"],
                    alerts=data.get("alerts_triggered", []),
                )
            )
        except Exception:
            continue

    return reports


# Health endpoint (public, no auth required)
@router.get("/health/data-quality", response_model=DataQualityHealthResponse)
async def get_data_quality_health() -> DataQualityHealthResponse:
    """
    Get current data quality health status.

    This endpoint is used by monitoring systems to verify data quality.
    No authentication required.

    **Response Fields**:
    - status: Overall health status (pass/warning/critical/unknown)
    - last_validation: When the last validation ran
    - atc_coverage: Percentage of drugs with valid ATC codes
    - provenance_coverage: Percentage of drugs with provenance tracking
    - structure_validity: Percentage of valid molecular structures
    - total_drugs: Total number of drugs in database
    - validation_summary: Summary of validation checks
    - alerts: List of active alerts
    """
    pipeline = get_validation_pipeline()

    try:
        health = pipeline.get_health_status()
        return DataQualityHealthResponse(**health)

    except Exception as e:
        return DataQualityHealthResponse(
            status="unknown",
            last_validation=None,
            atc_coverage=0.0,
            provenance_coverage=0.0,
            structure_validity=0.0,
            total_drugs=0,
            validation_summary={
                "total_checks": 0,
                "passed": 0,
                "failed": 0,
                "critical_failures": 0,
            },
            alerts=[f"Health check failed: {str(e)}"],
        )
