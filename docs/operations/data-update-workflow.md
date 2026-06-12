# DrugTree Data Update Workflow

## Overview

This document describes the end-to-end workflow for updating drug data in DrugTree, including the automated sync process, change detection, validation, and audit logging.

## Canonical Execution Path

The canonical execution path for database updates is `src/backend/run_etl.sh`.
It is the repo-truthful workflow for fetch, normalize, generate, artifact build, and SQLite load steps.

`src/backend/services/update_scheduler.py` is optional/planned service infrastructure.
It may orchestrate or trigger updates in the future, but it is not the current source of truth for how the ETL is executed today.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Data Update Pipeline                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   Data       │───►│   Change     │───►│  Validation  │          │
│  │   Sources    │    │   Detector   │    │  Pipeline    │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│         │                   │                   │                    │
│         ▼                   ▼                   ▼                    │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   ETL        │    │   Change     │    │   Audit      │          │
│  │   Clients    │    │   History    │    │   Logger     │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Update Scheduler (`update_scheduler.py`)

**Purpose**: Optional/planned service infrastructure for periodic orchestration

**Features**:
- Weekly sync job (Sunday 2 AM UTC)
- Manual trigger support
- Notification system (log file, email, Slack)
- Job status tracking

**Configuration** (`update_schedule.yaml`):
```yaml
schedule:
  weekly:
    day_of_week: sun
    hour: 2
    minute: 0
    timezone: UTC

sources:
  - name: chembl
    enabled: true
    priority: 1
  - name: kegg
    enabled: true
    priority: 2
```

**Usage**:
```python
from src.backend.services.update_scheduler import get_scheduler, start_scheduler

# Start scheduler
scheduler = get_scheduler()
start_scheduler()

# Inspect scheduler state
jobs = scheduler.get_scheduled_jobs()
status = scheduler.get_sync_status()

# Manual trigger
await scheduler.trigger_manual_sync()
```

---

### 2. Change Detector (`change_detector.py`)

**Purpose**: Detects and tracks changes to drug data

**Features**:
- Hash-based diffing (SHA-256)
- 30-day rollback support
- Field-level change tracking
- Priority classification (LOW, MEDIUM, HIGH, CRITICAL)

**Change Types**:
| Type | Description |
|------|-------------|
| NEW | New drug added |
| UPDATED | Existing drug modified |
| DEPRECATED | Drug marked as deprecated |
| RESTORED | Deprecated drug restored |

**Hash Exclusion Fields**:
The following fields are excluded from hash computation to avoid false positives:
- `updated_at`
- `provenance_timestamp`

**Usage**:
```python
from src.backend.services.change_detector import get_change_detector

detector = get_change_detector()

# Detect changes between datasets
changeset = await detector.detect_all_changes(
    old_drugs=previous_data,
    new_drugs=current_data,
    source="weekly_sync"
)

# Apply changes
success, failed = await detector.apply_changeset(changeset)

# Rollback within 30 days
rollback = await detector.rollback_change(change_id, rolled_back_by="admin")
```

---

### 3. Audit Logger (`audit_logger.py`)

**Purpose**: Comprehensive audit trail for all operations

**Features**:
- Async batch inserts (>100 logs/sec)
- 90-day online retention
- Archive to filesystem
- Sensitive data filtering
- Compliance export

**Auditable Actions**:
| Category | Actions |
|----------|---------|
| Data | drug_create, drug_update, drug_delete, drug_deprecated, drug_restored |
| Sync | sync_started, sync_completed, sync_failed |
| Change | change_applied, change_rolled_back, change_approved |
| API | api_call, api_error, api_auth |
| Admin | admin_trigger_sync, admin_force_update, admin_config_change |
| System | validation_run, cleanup_run, backup_created |

**Usage**:
```python
from src.backend.services.audit_logger import get_audit_logger, AuditActor, AuditAction

logger = get_audit_logger()

# Log an action
await logger.log(
    action=AuditAction.DRUG_UPDATE,
    entity_type="drug",
    entity_id="atorvastatin",
    actor=AuditActor(type="system", id="weekly_sync"),
    before_value={"molecular_weight": 348.48},
    after_value={"molecular_weight": 350.00},
    field_changes=["molecular_weight"],
)

# Query logs
from src.backend.models.audit import AuditQuery
logs = await logger.query_logs(AuditQuery(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31),
    actions=[AuditAction.DRUG_UPDATE],
))

# Export for compliance
await logger.export_logs(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31),
    output_path=Path("exports/audit_2024.json"),
)
```

---

### 4. Validation Pipeline (`validation_pipeline.py`)

**Purpose**: End-to-end validation of drug data quality

**Validation Checks**:
| Check | Description | Threshold |
|-------|-------------|-----------|
| ATC Coverage | Drugs with valid ATC codes | ≥85% |
| Provenance Integrity | Drugs with provenance tracking | 100% |
| Data Consistency | Cross-field consistency | 0 issues |
| Duplicate Detection | No duplicate SMILES/InChIKey | 0 duplicates |
| Schema Compliance | Required fields present | 0 violations |
| Relationship Integrity | Parent/successor references valid | 0 broken refs |
| Phase Distribution | Reasonable phase spread | Informational |
| Structure Validity | Valid SMILES format | 0 invalid |

**Alert Thresholds**:
- ATC coverage <85% → Alert
- ATC coverage <70% → Critical alert
- Duplicates detected → Alert
- Provenance incomplete → Warning

**Usage**:
```python
from src.backend.services.validation_pipeline import get_validation_pipeline

pipeline = get_validation_pipeline()

# Run full validation
report = await pipeline.run_validation(
    drugs=current_data,
    provenance_records=provenance,
    sync_job_id="sync_20240101"
)

print(f"Status: {report.overall_status}")
print(f"ATC Coverage: {report.atc_coverage_percent}%")

# Get health status
health = pipeline.get_health_status()
```

---

## Workflow

### Canonical CLI / ETL execution

```bash
bash src/backend/run_etl.sh
```

Use `run_etl.sh` for the real repo update path. It owns the current fetch/normalize/generate/build/load order.

### Automated Weekly Sync

```
1. Scheduler triggers at configured time
2. Update job starts:
   a. Fetch data from sources (ChEMBL, KEGG)
   b. Transform and normalize data
   c. Detect changes vs previous snapshot
   d. Generate changeset
3. Validation pipeline runs:
   a. ATC coverage check
   b. Provenance integrity check
   c. Data consistency check
   d. Duplicate detection
   e. Schema compliance
   f. Generate report
4. If validation passes:
   a. Apply changeset
   b. Log audit entries
   c. Archive old data
   d. Send success notification
5. If validation fails:
   a. Log errors
   b. Send alert notification
   c. Do not apply changes
```

### Manual Sync

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/admin/trigger-sync \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

There is no standalone scheduler CLI entrypoint in the current repo. Use the admin API or an interactive Python session if you need to trigger sync logic directly.

### Rollback

```bash
# Rollback a specific change within 30 days
curl -X POST http://localhost:8000/api/v1/admin/rollback/{change_id} \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## API Endpoints

### Admin Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/admin/trigger-sync` | POST | Trigger manual data sync |
| `/api/v1/admin/rollback/{change_id}` | POST | Rollback a change |
| `/api/v1/admin/audit-logs` | GET | Query audit logs with filters |
| `/api/v1/admin/validation-reports` | GET | List validation reports |

### Health Endpoint

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/admin/health/data-quality` | GET | Get current data quality metrics |

**Response Example**:
```json
{
  "status": "pass",
  "last_validation": "2024-01-15T02:00:00Z",
  "atc_coverage": 92.5,
  "provenance_coverage": 100.0,
  "structure_validity": 99.8,
  "total_drugs": 7359,
  "validation_summary": {
    "total_checks": 8,
    "passed": 7,
    "failed": 1,
    "critical_failures": 0
  },
  "alerts": []
}
```

---

## File Locations

```
data/
├── drugs/                    # Drug data files
├── changes/                  # Change history
│   └── *.json               # Individual change records
├── reports/                  # Validation reports
│   ├── validation_*.json    # Dated reports
│   └── validation_latest.json
├── audit_logs/              # Audit log storage
│   ├── batch_*.json         # Batch files
│   └── archive/             # Archived logs (90+ days old)
└── cache/                   # Cached data
    └── drug_hashes.json     # Hash cache
```

---

## Retention Policies

| Data Type | Online | Archive | Total |
|-----------|--------|---------|-------|
| Drug Data | Forever | N/A | Forever |
| Change Records | 30 days | N/A | 30 days |
| Audit Logs | 90 days | 275 days | 365 days |
| Validation Reports | 90 days | N/A | 90 days |

---

## Monitoring

### Logs

All components log to standard output with structured logging:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Validation complete", extra={
    "report_id": report.report_id,
    "status": report.overall_status,
    "drugs_validated": report.drug_count,
})
```

### Metrics

Key metrics to monitor:
- Sync job duration
- Changes detected per sync
- Validation pass rate
- ATC coverage percentage
- Audit log write latency

---

## Troubleshooting

### Sync Job Not Running

1. Check scheduler status:
   ```python
   scheduler = get_scheduler()
   print(scheduler.get_sync_status())
   print(scheduler.get_scheduled_jobs())
   ```

2. Verify configuration:
   ```bash
   cat src/backend/config/update_schedule.yaml
   ```

3. Check logs:
   ```bash
   grep "update_scheduler" logs/app.log
   ```

### Validation Failures

1. Check latest report:
   ```bash
   cat data/reports/validation_latest.json
   ```

2. Review specific failures:
   ```python
   for result in report.results:
       if not result.passed:
           print(f"{result.validation_type}: {result.message}")
   ```

### Rollback Issues

1. Verify change is within 30-day window:
   ```python
   change = await detector.get_change(change_id)
   print(f"Can rollback: {change.can_rollback}")
   print(f"Deadline: {change.rollback_deadline}")
   ```

---

## Best Practices

1. **Always validate before applying changes**
   ```python
   report = await pipeline.run_validation(drugs)
   if report.overall_status == "CRITICAL":
       raise ValidationError("Critical validation failures")
   ```

2. **Use audit logging for all operations**
   ```python
   await audit_logger.log_drug_change(change, actor)
   ```

3. **Keep rollback capability in mind**
   ```python
   # Store old snapshot before changes
   change.old_snapshot = drug.copy()
   ```

4. **Monitor alerts regularly**
   ```bash
   # Check for unacknowledged alerts
curl http://localhost:8000/api/v1/admin/health/data-quality
   ```

---

## Security Considerations

1. **Sensitive Data Filtering**
   - API keys, passwords, tokens are automatically redacted
   - Use `AuditLog.sanitize_value()` for custom data

2. **Access Control**
   - Admin endpoints require authentication
   - Use role-based access for sensitive operations

3. **Audit Trail Integrity**
   - Logs are append-only
   - Archives are stored with checksums

---

## References

- [Project plan](../product/project-plan.md) - Product and architecture roadmap
- [Database improvement review](../audits/database-improvement-review.md) - ATC enrichment and data-quality review
- [AGENTS.md](../../AGENTS.md) - Project knowledge base
- [src/backend/models/change.py](../../src/backend/models/change.py) - Change models
- [src/backend/models/audit.py](../../src/backend/models/audit.py) - Audit models
