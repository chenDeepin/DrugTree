# Target Layer Readiness Plan

Plan for expanding DrugTree's molecular target layer (EGFR, HMG-CoA reductase, etc.) without destabilizing public mode.

> **Status**: Planning only (no code/data edits).
> **Scope**: Target nodes + `drug_target` edges + scientist-mode UX enablement path.
> **Constraint**: Public mode behavior/performance must remain stable.

---

## 0) Current Baseline

### Backend and schema reality
- `src/backend/models/graph.py`
  - node types: `drug`, `disease`, `target`, `cluster`
  - edge types: `lineage`, `disease_drug`, `drug_target`, `family_member`
- `src/backend/models/nodes.py`
  - `TargetNode(id, symbol, name?, disease_ids[])`, computed `full_id="target:{id}"`
- `src/backend/models/disease.py`
  - `Target(id, symbol, name, modality, disease_ids, uniprot_id, hgnc_id, entrez_id)`
- `src/backend/services/graph_queries.py`
  - `_resolve_target_node()` currently placeholder-only (`label=target_id`, `extra={}`)
  - neighborhood/subgraph currently include lineage + disease_drug, not hydrated drug_target
- `src/backend/services/graph_index.py`
  - indexes drugs/families/lineage only; no target index

### Frontend and mode gating reality
- `src/frontend/js/stores/graphStore.js`
  - `loadGraph({ drugs, diseases, bodyOntology, diseaseDrugEdges })`
  - no `targets` / `drugTargetEdges` state
- `src/frontend/js/app.js`
  - mode control is `switchMode(mode)` with `this.mode` in `{public, scientist}`
  - scientist-only blocks already exist (`.scientist-only`)
  - no target lazy-load or strict target gate yet

### Graph contract alignment
- `docs/modules/graph-data-contract.md` planned artifacts:
  - `data/graph/nodes/targets.json`
  - `data/graph/edges/drug_target.json`

---

## 1) Target Prerequisites (Before Any Target UX)

### 1.1 Required graph artifacts
Must exist and validate before UI work:
1. `data/graph/nodes/targets.json`
2. `data/graph/edges/drug_target.json`

Minimum envelope: `schema_version`, `total`, and `nodes[]` / `edges[]`.

### 1.2 Minimum viable target node fields
- `id` (stable canonical key)
- `symbol`
- `name`
- `disease_ids[]`
- `modality`
- external IDs when available: `uniprot_id`, `hgnc_id`, `entrez_id`

### 1.3 Minimum viable drug-target edge fields
- `edge_id`, `edge_type="drug_target"`
- `source_id="drug:{drug_id}"`, `target_id="target:{target_id}"`
- `confidence`
- unified metadata from graph contract: `source`, `source_record_id`, `curation_status`, `updated_at`
- action context: `modality`, `action_type` (if available)

### 1.4 Target-disease association rule
Use explicit evidence-backed association, not body-region coincidence.
- preferred: curated/direct source associations
- fallback: inferred from disease-linked drugs sharing target, with reduced confidence/provenance

### 1.5 Target grouping prerequisite
At least one grouping axis required before target navigation UX:
- protein family/class (kinase/GPCR/enzyme)
- pathway grouping (KEGG or equivalent)
- optional source-native hierarchy (e.g., ChEMBL target class)

---

## 2) Data Sources Assessment

| Source | Useful output | Strength | Limitation | Role in pipeline |
|---|---|---|---|---|
| UniProt | canonical protein identity, names, accessions | stable identifiers | weak for direct drug potency edges | target identity authority |
| ChEMBL | bioactivity + mechanism (IC50/Ki/Kd/EC50) | strongest edge evidence | assay heterogeneity/normalization cost | primary `drug_target` edge source |
| KEGG | pathway/functional context | useful grouping layer | uneven edge-level depth | enrichment/classification |
| `data/drugs.json` `targets[]` | immediate seed hints | already present in canonical drugs | string-only, unnormalized, low provenance | bootstrap only |

**Policy**: identity from UniProt/HGNC, edge evidence from ChEMBL, context from KEGG, current `targets[]` only as seed input.

---

## 3) Phased Rollout (Rollback-safe)

## Phase 1 — Backend target resolution (API-only)
**Goal**: Enable structured target node/edge resolution in backend APIs; no frontend UX change.

**Depends on**:
- `data/graph/nodes/targets.json`
- `data/graph/edges/drug_target.json`

**Touchpoints**:
- `src/backend/services/graph_index.py`: add target indexes
- `src/backend/services/graph_queries.py`:
  - hydrate `_resolve_target_node()` from target artifact
  - include `drug_target` edges in neighborhood/subgraph when relevant

**Verification**:
- `/api/v1/graph/node/target:{id}` returns rich `GraphNodeRef`
- current drug/disease/cluster API behavior unchanged

**Rollback criteria**:
- API contract regression for existing node types
- latency/error regressions beyond baseline
- rollback action: disable target artifact path, keep placeholder target resolver

## Phase 2 — Scientist-mode target display
**Goal**: Show targets only when `this.mode === 'scientist'`.

**Depends on**: Phase 1 + frontend target state extensions.

**Touchpoints**:
- `src/frontend/js/stores/graphStore.js`: optional `{ targets, drugTargetEdges }` loading
- `src/frontend/js/app.js`: strict target rendering gate:
  - `if (this.mode !== 'scientist') return;`

**Verification**:
- public mode DOM/filter behavior unchanged
- scientist mode displays target details/snippets correctly

**Rollback criteria**:
- any target leak into public mode
- scientist modal/card regressions from target widgets
- rollback action: disable target UI feature flag

## Phase 3 — Target-aware scientist filtering/navigation
**Goal**: Add scientist-only target filters and drilldowns.

**Depends on**: Phase 2 + normalized IDs + grouping metadata.

**Scope**:
- scientist target chip/filter/search
- drilldowns: Disease → Target → Drug and Drug → Target → Related drugs

**Verification**:
- filter intersections correct vs `drug_target` edges
- no interference with public ATC/body-region filters

**Rollback criteria**:
- incorrect intersections or degraded response/render performance
- rollback action: disable filters, retain Phase 2 display-only behavior

## Phase 4 — Target neighborhood visualization
**Goal**: Render target nodes in graph neighborhood view (scientist mode).

**Depends on**: Phase 3 + bounded backend expansion strategy.

**Scope**:
- mixed-node rendering (`drug/disease/target/cluster`)
- bounded node/edge caps + hop limits

**Verification**:
- stable render latency and bounded payload size
- edge evidence displayed per graph contract

**Rollback criteria**:
- graph instability, payload blow-up, or unusable layouts
- rollback action: revert to drug+disease neighborhood visualization

---

## 4) Public Mode Safety Guardrails

1. **Visibility isolation**: no targets, no target filters, no target neighborhood nodes in public mode.
2. **Strict code gate**: every target UI path must guard on scientist mode (`this.mode !== 'scientist'`).
3. **Topbar isolation**: public topbar and active filter chips must remain target-free.
4. **Load isolation**: target data should load lazily on scientist activation/first scientist target interaction.
5. **Performance isolation**: bound target fan-out with caps and fallback behavior.
6. **Contract isolation**: existing public API/UI payload shape remains stable during rollout.

---

## 5) Dependencies by Phase

| Dependency | P1 | P2 | P3 | P4 |
|---|:---:|:---:|:---:|:---:|
| `data/graph/nodes/targets.json` | ✅ | ✅ | ✅ | ✅ |
| `data/graph/edges/drug_target.json` | ✅ | ✅ | ✅ | ✅ |
| backend target resolution (`graph_queries.py`) | ✅ | ✅ | ✅ | ✅ |
| GraphStore target loading |  | ✅ | ✅ | ✅ |
| scientist target UI components |  | ✅ | ✅ | ✅ |
| scientist target filtering/navigation |  |  | ✅ | ✅ |
| mixed-node neighborhood visualization |  |  |  | ✅ |

---

## 6) Data Flow Diagrams (Text)

### 6.1 Backend target data flow
```text
UniProt + ChEMBL + KEGG + drugs.targets[]
  -> ETL normalization/merge
  -> data/graph/nodes/targets.json
  -> data/graph/edges/drug_target.json
  -> GraphIndex (target indexes)
  -> GraphQueryService (node/neighborhood/subgraph)
  -> /api/v1/graph/*
```

### 6.2 Frontend mode-gated flow
```text
App init (public default)
  -> load current payload (drugs/diseases/bodyOntology/diseaseDrugEdges)
  -> GraphStore.loadGraph(...)
  -> no target UI

switchMode('scientist')
  -> lazy-load target nodes/edges (if needed)
  -> hydrate GraphStore target maps
  -> enable scientist target cards/filters/neighborhood
```

---

## 7) Go / No-Go

- Do **not** enable target UX before contract artifacts and backend transition path are stable.
- Do **not** expose target controls in public mode.
- Do **not** ship any phase without explicit rollback readiness.
