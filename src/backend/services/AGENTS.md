# DrugTree Backend Services

## OVERVIEW
Service layer only, business logic between routers and data stores. Keep this file local to `src/backend/services/`.

## KEY SERVICES
- `graph_index.py`, in-memory adjacency index, unified graph for drugs, diseases, families, lineages, node and edge lookup.
- `graph_queries.py`, query layer over `graph_index`, N-hop neighborhoods, evidence retrieval, subgraph extraction, graph stats.
- `tree_builder.py`, disease hierarchy and body region tree construction.
- `validation_pipeline.py`, schema checks, completeness scoring, consistency rules, data quality gates.
- `change_detector.py`, hash-based diffing for data mutations, emits change records for audit trail.
- `audit_logger.py`, who changed what, when, why, durable audit history.
- `update_scheduler.py`, periodic update scheduling config, planned and documentation driven.
- Other service files, keep them thin, focused, and layered on the same data model.

## CONVENTIONS
- Read from canonical `data/`, not generated frontend mirrors.
- Prefer pure helpers, small units, explicit inputs and outputs.
- Use Pydantic validation at boundaries.
- Wrap external calls in try/except with graceful fallback.
- Keep async HTTP flows async, no sync request helpers.

## ANTI-PATTERNS
- No router code here.
- No direct edits to generated frontend data.
- No hidden state changes across validation, detection, or audit paths.
- No broad catch-all logic that hides failed graph or data updates.
- Do not duplicate `__all__` exports — `services/__init__.py` already has duplicates.
