# Graph Transition Plan

Incremental migration from current canonical JSON files to the unified graph-native `data/graph/` directory defined in [graph-data-contract.md](./graph-data-contract.md).

> **Status**: Planning — no code or data changes yet.
> **Principle**: No big-bang migration. Every phase ships independently and rolls back cleanly.

---

## Transition Principles

1. **Dual-write before dual-read** — produce new artifacts before switching any consumer
2. **Fallback-first** — every new code path falls back to the current path on missing data
3. **API stability** — the HTTP API surface (`/api/v1/*`) never changes shape during migration
4. **One phase at a time** — a phase is complete only when all verification steps pass
5. **Explicit rollback points** — each phase documents the revert criteria

---

## Phase Dependency Map

```
Phase 1: Dual-Source ETL
    │
    ├──► Phase 2: GraphIndex Adapter (backend)
    │
    └──► Phase 3: Frontend Dual-Load (parallel with Phase 2)
              │
              └──► Phase 4: Primary Graph (requires 2 + 3 complete)
```

Phases 2 and 3 can proceed in parallel after Phase 1 ships.

---

## Phase 1 — Dual-Source ETL

**Goal**: Existing ETL produces both current canonical files AND new `data/graph/` artifacts. No consumer changes.

### What Changes

| Component | Change |
|-----------|--------|
| `scripts/build_graph_artifacts.py` (new) | Reads canonical sources, writes `data/graph/` per [graph-data-contract.md §2](./graph-data-contract.md#2-proposed-datagraph-layout) |
| `src/backend/run_etl.sh` | Appends `build_graph_artifacts.py` call after existing pipeline |

### What Stays the Same

- `data/drugs.json`, `data/diseases.json`, `data/disease_drug_edges.json` — unchanged, still canonical
- `data/processed/drug_families.json`, `data/processed/lineage_edges.json` — still produced
- `scripts/build_frontend_embeds.py` — still reads from `data/`, writes `src/frontend/data/`
- `GraphIndex`, `GraphStore`, all API endpoints — unchanged

### Verification

1. `build_graph_artifacts.py` exits 0
2. `data/graph/graph-meta.json` exists with `schema_version: "2.0.0"`
3. Node counts match: `data/graph/nodes/drugs.json` total == `data/drugs.json` drug count
4. Edge counts match: lineage edges == `data/processed/lineage_edges.json` total
5. `git diff` shows zero changes to any existing file
6. Existing backend tests (`pytest tests/backend/`) still pass

### Rollback

Delete `data/graph/`. Remove the appended line from `run_etl.sh`. Everything else is untouched.

---

## Phase 2 — GraphIndex Adapter

**Goal**: `GraphIndex` reads from `data/graph/` when available, falls back to current files. API unchanged.

### What Changes

| Component | Change |
|-----------|--------|
| `src/backend/services/graph_index.py` | New `GraphIndexV2` subclass that loads from `data/graph/` first, falls back to `data/processed/` + `data/drugs.json` |
| `src/backend/services/graph_queries.py` | `get_graph_index()` returns V2 when `data/graph/graph-meta.json` exists |
| Singleton wiring | `get_graph_index()` detects available data source at call time |

### Adapter Behavior

```python
def get_graph_index() -> GraphIndex:
    if (DATA_ROOT / "graph" / "graph-meta.json").exists():
        return GraphIndexV2()   # reads data/graph/
    return GraphIndex()          # reads data/processed/ + data/drugs.json (current)
```

### What Stays the Same

- All `/api/v1/graph/*` response shapes — identical
- `GraphIndex` class API (`.get_node()`, `.get_edges()`, `.get_family()`, etc.) — unchanged
- `graph_queries.py` method signatures — unchanged
- Current canonical files still generated (Phase 1 dual-write)

### Verification

1. With `data/graph/` absent: behavior identical to today (fallback path)
2. With `data/graph/` present: `/api/v1/graph/stats` returns same node/edge/family counts
3. `/api/v1/graph/neighborhood/{id}` results match between old and new loader
4. `/api/v1/lineage/{drug_id}` genealogy trees are identical
5. All backend tests pass with and without `data/graph/` present

### Rollback

Delete or rename `data/graph/`. `get_graph_index()` falls back to legacy `GraphIndex`. No code revert needed.

---

## Phase 3 — Frontend Dual-Load

**Goal**: `build_frontend_embeds.py` generates graph-native embeds alongside current format. `GraphStore` gets `loadFromGraph()` alongside existing `loadGraph()`.

### What Changes

| Component | Change |
|-----------|--------|
| `scripts/build_frontend_embeds.py` | New output: `src/frontend/data/graph-nodes.js` (`window.DRUGTREE_GRAPH_NODES`), `src/frontend/data/graph-edges.js` (`window.DRUGTREE_GRAPH_EDGES`), `src/frontend/data/graph-meta.js` (`window.DRUGTREE_GRAPH_META`). Existing outputs preserved. |
| `src/frontend/js/stores/graphStore.js` | New `loadFromGraph(graphPayload)` method that accepts `{nodes, edges, meta}` from graph-native embeds. Falls back to existing `loadGraph()` when graph globals absent. |
| `src/frontend/js/app.js` | Init detects `window.DRUGTREE_GRAPH_META` and calls `loadFromGraph()` when present, else `loadGraph()` |

### `loadFromGraph()` Mapping

| Graph Artifact | GraphStore Store | Transform |
|----------------|-----------------|-----------|
| `nodes` where `node_type == "drug"` | `this.nodes` (Map) | Strip `drug:` prefix → key by bare ID |
| `nodes` where `node_type == "disease"` | `this.diseaseHierarchy` (Map) | Strip `disease:` prefix |
| `edges` where `edge_type == "lineage"` | `this.edges` (Map) | Map `source_id`/`target_id` to existing edge shape |
| `edges` where `edge_type == "family_member"` | `this.families` (Map) | Reconstruct family groupings from edges |
| `meta.stats` | Logged to console | Verification counts match |

### What Stays the Same

- Existing `loadGraph(graphData)` method — untouched, still works
- `window.DRUGTREE_DRUGS_DATA`, `DRUGTREE_DISEASES_DATA`, etc. — still generated
- All UI rendering code — no changes
- API fallback when backend is running

### Verification

1. `build_frontend_embeds.py` produces both old and new embed files
2. With new globals present: `GraphStore.getStats()` reports same counts as `loadGraph()` path
3. With new globals absent: app loads identically to today
4. Playwright e2e tests (`npx playwright test`) pass in both modes
5. Disease panel renders identical drug lists in both modes
6. Genealogy view shows identical lineage trees in both modes

### Rollback

Remove graph-native `<script>` tags from `index.html`. Delete `src/frontend/data/graph-*.js`. App reverts to `loadGraph()` path.

---

## Phase 4 — Primary Graph

**Goal**: Graph-native data becomes the default. Current canonical files become secondary/fallback.

### What Changes

| Component | Change |
|-----------|--------|
| `src/backend/services/graph_index.py` | `get_graph_index()` defaults to `GraphIndexV2`; legacy `GraphIndex` only on explicit flag or missing `data/graph/` |
| `scripts/build_frontend_embeds.py` | Graph-native embeds become primary output; legacy embeds become optional (`--legacy` flag) |
| `src/frontend/js/app.js` | `loadFromGraph()` becomes default init path |
| `data/graph/graph-meta.json` | Now the authoritative data version marker |

### What Stays the Same

- HTTP API surface — zero changes
- `data/drugs.json`, `data/diseases.json` — still exist as ETL inputs
- `data/ontology/body-ontology.json` — stays as-is (config, not graph data)
- `data/curated/*` — override mechanism unchanged

### Deprecation Path (post-Phase 4)

After Phase 4 stabilizes for one full release cycle:
- Legacy `GraphIndex` class marked `@deprecated`
- Legacy embed generation removed from `build_frontend_embeds.py` default
- `loadGraph()` marked deprecated in `GraphStore`

### Verification

1. Full regression: all backend + frontend tests pass with graph-native as primary
2. Remove legacy embeds → app still works via graph-native path only
3. Remove `data/processed/` → backend still works via `data/graph/` only
4. `/api/v1/graph/stats` matches pre-Phase-4 baseline counts
5. Data quality check (`/api/v1/admin/health/data-quality`) reports no regressions

### Rollback

Flip `get_graph_index()` back to legacy-first. Restore legacy embed generation as default. `data/graph/` can remain — it's non-destructive.

---

## Component Dependency Matrix

| Component | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|-----------|---------|---------|---------|---------|
| `scripts/build_graph_artifacts.py` | **created** | — | — | updated |
| `scripts/build_frontend_embeds.py` | — | — | **updated** | updated |
| `src/backend/run_etl.sh` | **updated** | — | — | — |
| `src/backend/services/graph_index.py` | — | **updated** | — | updated |
| `src/backend/services/graph_queries.py` | — | **updated** | — | — |
| `src/frontend/js/stores/graphStore.js` | — | — | **updated** | updated |
| `src/frontend/js/app.js` | — | — | **updated** | updated |
| `src/frontend/data/graph-*.js` | — | — | **created** | primary |
| `data/graph/` | **created** | read | — | authoritative |
| `data/drugs.json` | input | input | input | input (still canonical source) |
| `data/processed/*.json` | produced | fallback | — | secondary |
| HTTP API (`/api/v1/*`) | — | — | — | — (never changes) |
| `src/backend/export/json_exporter.py` | — | — | — | optional update |

### Out-of-Order Risks

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Phase 2 without Phase 1 | `GraphIndexV2` has no data to read | Fallback to legacy `GraphIndex` handles this |
| Phase 3 without Phase 1 | No graph embeds to load | `loadGraph()` path still works |
| Phase 4 without Phase 2+3 | Backend and frontend still on legacy paths | Wasteful but not broken — graph files just unused |
| Phase 2 without Phase 3 (or vice versa) | No risk — they're independent after Phase 1 | Parallel development is safe |
