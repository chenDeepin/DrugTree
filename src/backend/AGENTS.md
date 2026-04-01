# DrugTree Backend - FastAPI service

## OVERVIEW
FastAPI + SQLite backend, async `httpx` for external calls, canonical data from repo-root `data/`.

## STRUCTURE
```
backend/
├── main.py          # app entry, CORS, DATA_PATH
├── routers/         # API surface
├── models/          # Pydantic and DB schemas
├── services/        # graph, validation, audit, scheduling
├── db/              # SQLite connection and schema
├── cache/           # API response caching
├── export/          # JSON export helpers
├── validation/      # migration and data validators
├── migrations/      # SQL and migration scripts
└── etl/             # pipeline code, see etl/AGENTS.md
```

## WHERE TO LOOK
- `main.py`, app setup, CORS, route wiring, `DATA_PATH`
- `routers/drugs.py`, drug, family, lineage endpoints
- `routers/diseases.py`, disease endpoints
- `routers/targets.py`, drug target lookup endpoints
- `routers/admin.py`, health and data-quality checks
- `routers/graph.py`, graph-native endpoints
- `routers/AGENTS.md`, full endpoint reference and router patterns
- `models/drug.py`, `disease.py`, `drug_family.py`, `lineage.py`
- `models/graph.py`, `nodes.py`, shared graph node types
- `models/audit.py`, `change.py`, `override.py`, `provenance.py`, `version.py`
- `services/graph_index.py`, in-memory adjacency index
- `services/graph_queries.py`, neighborhood, evidence, subgraph
- `services/tree_builder.py`, disease and hierarchy assembly
- `services/validation_pipeline.py`, `change_detector.py`, `audit_logger.py`
- `services/update_scheduler.py`, scheduled refresh logic
- `db/connection.py`, SQLite setup, `db/schema/`
- `migrations/001_schema.sql`, `001_add_disease_tables.sql`
- `scripts/migrate_drugs.py`, `scripts/migrate_atc.py`
- `validation/migration_validator.py`, schema and migration checks
- `export/json_exporter.py`, backend JSON output
- `models/AGENTS.md`, `services/AGENTS.md`, `etl/AGENTS.md` for deeper detail

## ANTI-PATTERNS
- Sync requests, use `async def` with `httpx`
- Direct edits to generated frontend mirrors or root data copies
- Skipping Pydantic validation
- Unbounded endpoints, add pagination or filters
- External API calls without try/except and fallback behavior
- Hardcoded secrets or local machine paths

## CONVENTIONS
- Keep schemas explicit and small, validate inputs and outputs
- Preserve SQLite compatibility, keep queries simple and indexed
- Use graceful degradation for ChEMBL, KEGG, PubChem, FDA calls
- Keep response caching and scheduler changes localized
- Treat root `data/` as source of truth, backend reads from it, ETL owns writes
