# DrugTree Backend Models

## OVERVIEW
Model layer for Pydantic, SQLAlchemy, and schema tracking.

## KEY MODELS
- `drug.py`, core drug schemas, ATC, molecular properties, targets, synonyms, body region, external IDs.
- `disease.py`, disease hierarchy with parent and child links.
- `drug_family.py`, family basis, member drug IDs, prototype drug ID.
- `lineage.py`, follow-on and derivative edges, confidence, score breakdown, provenance. DEPRECATED: `rationale_tags` → `generation_rationale`.
- `graph.py`, node types, refs, evidence, and graph edges.
- `nodes.py`, disease, target, and cluster node variants.
- `audit.py`, audit trail records.
- `change.py`, change detection and tracking.
- `override.py`, manual data overrides.
- `provenance.py`, source provenance.
- `version.py`, schema versioning.

## CONVENTIONS
- Keep Pydantic and SQLAlchemy fields aligned.
- Preserve stable IDs, enums, and relationship names.
- Prefer explicit provenance on derived data.
- Keep score breakdowns and lineage metadata structured.

## ANTI-PATTERNS
- Don't edit generated mirrors outside canonical model sources.
- Don't rename public fields without migration support.
- Don't drop provenance, confidence, or audit history.
- Don't blur disease, drug, family, and graph node responsibilities.
