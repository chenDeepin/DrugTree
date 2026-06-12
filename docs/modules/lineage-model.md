# Lineage Model

Defines the drug lineage edge system: relationship types, confidence scoring, provenance hierarchy, and DAG structure.

> **Source of truth**: `src/backend/models/lineage.py`, `data/processed/lineage_edges.json`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Edge Types](#2-edge-types)
3. [LineageEdge Schema](#3-lineageedge-schema)
4. [Confidence Scoring](#4-confidence-scoring)
5. [Provenance Hierarchy](#5-provenance-hierarchy)
6. [Rationale Tags](#6-rationale-tags)
7. [DAG Structure](#7-dag-structure)
8. [Curation Workflow](#8-curation-workflow)

---

## 1. Overview

Drug lineage captures evolutionary relationships between drugs: how later compounds were derived from earlier ones. The system models these as directed edges in a DAG (directed acyclic graph), where `from_drug_id` is the predecessor and `to_drug_id` is the successor.

- **Current data**: `data/processed/lineage_edges.json` — derived from ChEMBL, KEGG, DrugBank sources
- **Index**: loaded by `GraphIndex` (`src/backend/services/graph_index.py`)
- **Schema version**: `1.1.0`

---

## 2. Edge Types

Eight relationship types defined in `EdgeType` (`src/backend/models/lineage.py`):

| Type | Value | Description |
|------|-------|-------------|
| Follow-on | `follow_on` | Direct successor compound |
| Generation successor | `generation_successor` | Next-generation drug in same class |
| Resistance branch | `resistance_branch` | Developed to overcome resistance |
| Safety branch | `safety_branch` | Developed for improved safety profile |
| Combination component | `combination_component` | Part of a combination therapy |
| Prodrug | `prodrug` | Inactive precursor of an active drug |
| Metabolite | `metabolite` | Active metabolite of a parent drug |
| Me-too | `me_too` | Structurally similar follow-on with no novel mechanism |

---

## 3. LineageEdge Schema

Full schema from `src/backend/models/lineage.py`:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `edge_id` | `str` | Yes | — | Unique identifier (e.g., `lovastatin_to_atorvastatin`) |
| `from_drug_id` | `str` | Yes | — | Predecessor drug ID (earlier in lineage) |
| `to_drug_id` | `str` | Yes | — | Successor drug ID (later in lineage) |
| `edge_type` | `EdgeType` | Yes | — | Type of lineage relationship |
| `confidence` | `float` | Yes | — | Confidence score [0.0–1.0] |
| `generation_rationale` | `List[str]` | No | `[]` | Rationale tags explaining the relationship |
| `rationale_tags` | `List[str]` | No | `[]` | **DEPRECATED** — use `generation_rationale` |
| `score_breakdown` | `Dict[str, float]` | Yes | — | Component scores (chronology, mechanism, scaffold) |
| `provenance` | `Provenance` | No | `auto` | Source of edge (auto/curated/manual) |
| `explanation` | `str` | No | `null` | Human-readable explanation |
| `schema_version` | `str` | No | `"1.1.0"` | Schema version (pattern: `\d+\.\d+\.\d+`) |

### Example

```json
{
  "edge_id": "lovastatin_to_atorvastatin",
  "from_drug_id": "lovastatin",
  "to_drug_id": "atorvastatin",
  "edge_type": "generation_successor",
  "confidence": 0.87,
  "generation_rationale": ["first_in_class", "same_target", "similar_scaffold"],
  "score_breakdown": {
    "chronology_score": 0.8,
    "mechanism_score": 0.95,
    "scaffold_score": 0.85
  },
  "provenance": "auto",
  "explanation": "Atorvastatin is a 2nd-generation statin derived from lovastatin",
  "schema_version": "1.1.0"
}
```

---

## 4. Confidence Scoring

Each lineage edge carries a composite confidence score (0.0–1.0) with explainable breakdown.

### Score Components

| Component | Weight | Description |
|-----------|--------|-------------|
| `chronology_score` | — | Temporal relationship: did the successor come after the predecessor? |
| `mechanism_score` | — | Shared mechanism of action (target pathway similarity) |
| `scaffold_score` | — | Structural similarity (shared chemical scaffold) |

The final confidence is a weighted combination of these components, computed by the ETL pipeline in `src/backend/etl/lineage_builder.py`.

### Score Interpretation

| Range | Confidence Level | Typical Scenarios |
|-------|-----------------|-------------------|
| 0.8–1.0 | High | Same target, clear chronological successor, similar scaffold |
| 0.5–0.8 | Medium | Same class but different scaffold, or partial target overlap |
| 0.0–0.5 | Low | Weak structural similarity only, inferred relationship |

---

## 5. Provenance Hierarchy

Three provenance levels with strict precedence (`src/backend/models/lineage.py`):

```python
class Provenance(str, Enum):
    auto = "auto"      # Computed by ETL pipeline
    curated = "curated" # Reviewed and approved by curator
    manual = "manual"   # Directly entered by domain expert
```

**Precedence**: `manual > curated > auto`

- **Manual** entries override both curated and auto for the same edge
- **Curated** entries override auto
- **Auto** entries are the default from the ETL pipeline
- The `src/backend/etl/override_loader.py` loads manual overrides from `data/curated/`

---

## 6. Rationale Tags

Tags explaining *why* a lineage relationship exists. Defined in `RationaleTag`:

| Tag | Value | Description |
|-----|-------|-------------|
| First in class | `first_in_class` | Drug was the first in its therapeutic class |
| Me-too | `me_too` | Follow-on with no novel mechanism |
| Improved PK | `improved_pk` | Better pharmacokinetic properties |
| Combination | `combination` | Designed for combination therapy |
| Prodrug | `prodrug` | Designed as a prodrug |
| Metabolite | `metabolite` | Identified as active metabolite |
| Same target | `same_target` | Shares molecular target with predecessor |
| Similar scaffold | `similar_scaffold` | Shares core chemical scaffold |
| Sequential generation | `sequential_generation` | Next in a generational series |

---

## 7. DAG Structure

Lineage edges form a directed acyclic graph (DAG):

- **Direction**: `from_drug_id` → `to_drug_id` (predecessor → successor)
- **Root nodes**: First-in-class drugs with no incoming edges
- **Leaf nodes**: Latest-generation drugs with no outgoing edges
- **Multi-parent**: A drug can have multiple predecessors (e.g., combination of two lineages)
- **No cycles**: The ETL pipeline validates acyclicity via `src/backend/etl/dag_validator.py`

### Traversal

The `GraphIndex` provides:
- `get_outgoing_edges(drug_id)`: drugs derived *from* this one (successors)
- `get_incoming_edges(drug_id)`: predecessor drugs (what this was derived from)
- `get_neighborhood(drug_id, max_hops)`: BFS traversal up to N hops

### Genealogy Tree

The frontend genealogy view (`src/frontend/js/views/genealogyView.js`) renders a D3 tree visualization for a selected drug, showing:
- Ancestors (incoming edges, top of tree)
- Descendants (outgoing edges, bottom of tree)
- Edge confidence as line opacity
- Edge type as line style
- Scientist-mode detail evidence text from graph edge confidence/provenance
- Scientist-mode tooltips with provenance and edge explanation when present

---

## 8. Curation Workflow

### Adding/Modifying Lineage Edges

1. **Auto-detected**: Run `bash src/backend/run_etl.sh` to recompute from source data
2. **Curated override**: Add to `data/curated/lineage_overrides.json` with `provenance: "curated"`
3. **Manual entry**: Add to `data/curated/lineage_overrides.json` with `provenance: "manual"`

### Validation

- `src/backend/etl/dag_validator.py` checks for cycles after ETL
- `src/backend/services/validation_pipeline.py` validates edge schema compliance
- Score breakdown must contain at least the three required component scores
