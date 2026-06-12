# DrugTree Architecture

**Status:** Living document · **Last reviewed:** 2026-06-13 (branch `main`, base commit `34933f0`, current optimization working tree)
**Audience:** Anyone optimizing or extending the backend, ETL, or data layer.
**Companion:** [UI-Architecture.md](./UI-Architecture.md) covers the frontend in the same depth.

This document is the system-level map. It captures *how the pieces fit and why*, the invariants you must not break, and the known seams for future optimization. For day-to-day "where do I edit" pointers, see the per-module `AGENTS.md` files referenced at the end.

---

## 1. System Shape

DrugTree is a **dual-stack monorepo** with two independent runtimes that communicate only over HTTP, plus a shared canonical data layer at the repo root.

```
                    ┌──────────────────────────────────────────┐
                    │         CANONICAL DATA (repo root)        │
                    │  data/drugs.json          (7,359 drugs)   │
                    │  data/diseases.json       (50 diseases)   │
                    │  data/disease_drug_edges.json             │
                    │  data/ontology/body-ontology.json         │
                    │  data/processed/{families,lineages}.json  │
                    │  data/graph/{nodes,edges}/*.json          │
                    └───────────────┬───────────────┬──────────┘
                                    │ reads          │ generates
                  ┌─────────────────▼──┐         ┌───▼────────────────────────┐
                  │   BACKEND (FastAPI) │         │ scripts/                   │
                  │   reads JSON at run │         │ build_frontend_embeds.py   │
                  │   SQLite for targets│         └───┬────────────────────────┘
                  └─────────┬──────────┘             │ writes
                            │ /api/v1/* (HTTP)        ▼
                            │              src/frontend/data/*.js  (embeds)
                            │                         │
                  ┌─────────▼─────────────────────────▼──────────┐
                  │           FRONTEND (vanilla JS)               │
                  │  API-first, falls back to embedded JS bundles │
                  └───────────────────────────────────────────────┘
```

**Three load-bearing facts that explain most design decisions:**

1. **JSON is the source of truth at runtime, not the database.** The backend serves `data/*.json` through an in-memory snapshot cache. SQLite (`drugtree.db`) is used *only* for the `targets` tables and is read-only at request time. ETL owns all writes to `data/`.
2. **The frontend can run with zero backend.** It tries the API first, then falls back to pre-generated `src/frontend/data/*.js` embeds. This is what makes GitHub Pages hosting possible. Embeds are **generated, never authored** — see §4.
3. **There is no build step and no app factory.** Backend is module-level `app = FastAPI(...)`; frontend is global `<script>` tags. Keep both true unless a deliberate decision changes it.

| Layer | Tech | Entry point |
|-------|------|-------------|
| Frontend | Vanilla JS + RDKit.js + D3 | `src/frontend/index.html` |
| Backend | FastAPI + SQLite | `src/backend/main.py` |
| ETL | Python (`httpx` for external calls) | `src/backend/run_etl.sh` |
| Embed build | Python | `scripts/build_frontend_embeds.py` |
| Tests | pytest + Playwright | `tests/backend/`, `tests/frontend/` |

---

## 2. Backend: Layered Anatomy

The backend is a clean **routers → services → models → data** stack. Routers never touch files directly; they call services. Services own caching and graph logic. Models are Pydantic schemas validated at the boundary.

```
HTTP request
   │
   ▼
main.py  ── CORS, request-timing middleware (X-DrugTree-Request-Ms), router wiring
   │
   ▼
routers/{drugs,diseases,targets,graph,admin}.py   ── prefix /api/v1, validation, pagination
   │
   ▼
services/   ── data_snapshot · graph_index · graph_queries · tree_builder
   │            validation_pipeline · change_detector · audit_logger
   │            update_scheduler · request_metrics
   │
   ▼
models/     ── Drug, Disease, DrugFamily, LineageEdge, GraphNodeRef, Provenance, ...
   │
   ▼
data layer  ── data/*.json (canonical, via DataSnapshotService)  +  drugtree.db (targets only)
```

### 2.1 Entry & wiring (`main.py`)
- CORS allow-list: `localhost:8080`, `localhost:8765`, `127.0.0.1` variants, and `https://chendeepin.github.io`.
- Routers registered under `/api/v1`: `drugs`, `diseases`, `targets`, `admin` (`/api/v1/admin`), `graph` (`/api/v1/graph`).
- A timing middleware records per-route latency into the singleton `RequestMetricsService` and stamps `X-DrugTree-Request-Ms`.
- Startup warms `DataSnapshotService` and `GraphIndex` through the FastAPI lifespan hook.
- `GET /health` returns `{status, version, drugs_count}` where `drugs_count` comes from `DataSnapshotService` (this is the live snapshot, not a stale file — the old audit note about "health reports 61 from drugs-full.json" is **resolved**).

### 2.2 Routers (the API surface)
All endpoints are listed in `README.md` and `routers/AGENTS.md`. Patterns worth internalizing:
- **List endpoints** take `limit`/`offset` and filter params; most cap `limit` (drugs/diseases at 1000, edges at 50000).
- **Validation** is Pydantic response models on the way out, query-param typing on the way in.
- **Targets router uses SQLite only for target tables**, but the blocking `sqlite3` work is isolated behind `run_in_threadpool()`. `GET /targets/{id}` uses one compound query to return the target, drug edges, disease edges, and xrefs in the same response shape.

### 2.3 Services (where the logic lives)

| Service | Responsibility | Caching behavior |
|---------|----------------|------------------|
| `data_snapshot.py` | Lazy-load + cache canonical `data/*.json` (drugs, diseases, edges, ontology) | Singleton; 24h TTL + file mtime/size check; SHA256 source hash for versioning; thread-safe (`Lock`) |
| `graph_index.py` | In-memory adjacency index (nodes, edges, edges-by-drug, adjacency sets, families) | Warmed at startup; `refresh()` reloads artifacts; lookup paths auto-refresh when graph source mtime/size changes |
| `graph_queries.py` | Neighborhood / subgraph / evidence queries on top of the index | Bucketed cache, 24h TTL, versioned by data source hash + graph source version; hard caps (96 neighbor nodes, 128 subgraph nodes, etc.); `refresh()` clears query caches |
| `tree_builder.py` | Project flat lineage edges → genealogy DAG for the UI | Per-call (threshold-parameterized) |
| `validation_pipeline.py` | Post-sync data-quality checks (ATC coverage, provenance, duplicates, schema) | On demand; feeds `/admin/health/data-quality` |
| `change_detector.py` | Hash-based diff + 30-day rollback window | — |
| `audit_logger.py` | Batched audit trail, 90-day retention | Batch flush at 100 entries |
| `update_scheduler.py` | APScheduler weekly sync (Sun 02:00 UTC) + manual trigger; per-source rate limits | — |
| `request_metrics.py` | Per-route latency aggregation | In-memory |

**The graph engine in one paragraph:** `GraphIndex` reads graph artifacts (`data/graph/nodes/*.json`, `edges/lineage.json`) with a fallback to `data/processed/*.json`, and builds five dictionaries for O(1) lookups: `_nodes`, `_edges`, `_edges_by_drug`, `_adjacency`, `_families`. Neighborhood queries are BFS over `_adjacency` bounded by `max_hops` (1–5) and the node/edge caps in `graph_queries.py`. DAG validity is checked with Kahn's algorithm. The index is a process-level singleton, but public lookup paths now check graph source mtime/size signatures and refresh automatically when source artifacts change; `POST /api/v1/admin/refresh` remains the explicit refresh hook after ETL.

### 2.4 Models
Pydantic schemas in `models/`: `Drug`/`DrugSummary` (drug.py), `Disease`/`DrugDiseaseEdge`/`RegionalApproval` (disease.py), `LineageEdge` (lineage.py), `DrugFamily` (drug_family.py), `GraphNodeRef`/`GraphEdgeRef` (graph.py), plus `AuditLog`, `ChangeSet`, `Provenance`, `Override`, `Version`. **Note:** `lineage.rationale_tags` is deprecated in favor of `generation_rationale`.

### 2.5 Data layer
- **Canonical JSON** is read through `DataSnapshotService` — never read `data/*.json` directly from a router.
- **SQLite (`drugtree.db`)** holds only `targets`, `drug_target_edges`, `target_disease_edges`, `target_xrefs` (schema in `db/schema/002_drugtree_schema.sql`). It is *not* committed (anti-pattern: committing `*.sqlite`).
- Target SQLite reads are read-only and run in a threadpool so they do not block the async event loop.

---

## 3. ETL Pipeline

ETL lives in `src/backend/etl/` (~37 files) and is launched via `run_etl.sh`. Grouped by purpose:

| Stage | Output | Key modules |
|-------|--------|-------------|
| Drug normalization | `data/drugs.json` | `drug_etl.py`, `drug_metadata.py`, `drug_transform_helpers.py` (uses `httpx` for KEGG calls) |
| ATC enrichment | ATC codes on drugs | `atc_orchestrator.py`, `atc_lookup_service.py`, `atc_enrichment_pipeline.py`, `atc_enrichment_models.py`, `atc_enrichment_reports.py`, `atc_utils.py`, `atc_batch_*`, `classify_remaining_drugs.py` |
| Lineage building | `data/processed/lineage_edges.json` | `lineage_builder.py` |
| Family clustering | `data/processed/drug_families.json` | `family_builder.py` |
| Disease ETL | `data/diseases.json` | `disease_etl.py`, `disease_etl_helpers.py`, `disease_source_loaders.py`, `normalize_diseases.py` |
| Target enrichment | targets tables / edges | `normalize_targets.py`, `fetch_opentargets.py`, `fetch_drugcentral.py` |
| Edge generation | graph + disease-drug edges | `generate_edges.py`, `load_graph_edges.py` |
| Validation | gate reports | `validation_pipeline.py`, `validation_pipeline_core.py`, `validation_models.py`, `dag_validator.py` |

**Conventions & gaps:**
- External calls should use `httpx` with try/except + graceful degradation. The five formerly sync-`requests` ATC/KEGG files were migrated to `httpx` on 2026-06-12.
- The named B7 split targets are now under the ~600-line review threshold: `atc_orchestrator.py` is the thin public wrapper/CLI, ATC lookup and enrichment stages live in focused modules, drug and disease ETL helpers are separated from orchestration, and validation models/core are split from the service entrypoint.
- After any data change, regenerate embeds: `python3 scripts/build_frontend_embeds.py`.

---

## 4. Data Flow & The Embed Contract

```
ETL (writes) ──► data/*.json (canonical)
                   │
                   ├──► Backend reads at runtime via DataSnapshotService
                   │
                   └──► scripts/build_frontend_embeds.py wraps each dataset
                        in a window.DRUGTREE_* global and writes
                        src/frontend/data/*.js  (the embeds)
```

**The embed contract (do not violate):**
- `src/frontend/data/*.js` and `*.json` are **generated mirrors**. Never hand-edit them. Edit `data/` then rebuild.
- Runtime must not depend on `drugs-full.json` or `drugs-expanded.json` (legacy).
- Valid ATC codes are stable; only placeholder `*99XX99` codes are enrichment targets.

Current embed payloads (2026-06-13): `drugs-shell.js` 3.3 MB eager (497.7 KB gzip, 332.3 KB Brotli), `drugs.js` 4.2 MB lazy-loaded on full-detail hydration/file launches (722.4 KB gzip, 480.9 KB Brotli), `graph-nodes.js` 1.1 MB lazy-loaded for graph features (136.0 KB gzip, 108.0 KB Brotli), `diseases.js` 85 KB, others small. Removing eager `drugs.js` cuts ~4.2 MB from the first HTML script payload. `scripts/build_frontend_embeds.py` writes `.gz` and, when `brotli` is installed, `.br` sidecars; `scripts/serve_frontend.py` serves those sidecars for local/test static hosting.

---

## 5. Invariants & Contracts

Breaking any of these is a regression, not a refactor:

1. **JSON is canonical at runtime.** Don't make routers read SQLite for drug/disease/edge data.
2. **DataSnapshotService is the only reader of canonical JSON.** Routers and services go through it.
3. **Graph index is a singleton with source checks.** Lookup paths auto-refresh when graph artifacts change; `POST /api/v1/admin/refresh` is still the explicit operational hook after ETL.
4. **API responses are Pydantic-validated** and list endpoints are paginated/capped.
5. **The frontend embed mirror is generated.** Source edits happen in `data/`.
6. **CORS allow-list is explicit.** Add new origins deliberately.
7. **No test files in `src/backend/`.** Tests live in `tests/`.
8. **External API calls degrade gracefully** (try/except, fallbacks).

---

## 6. Known Constraints & Optimization Seams (Backend)

Ranked roughly by leverage. These are the entry points for the "optimize the backend" track.

| # | Issue | Where | Impact | Direction |
|---|-------|-------|--------|-----------|
| B1 | **Graph cache auto-invalidation in place** | `graph_index.py`, `graph_queries.py`, `POST /api/v1/admin/refresh` | Prevents stale graph/snapshot/query caches after ETL or source artifact changes | Keep graph source-version tests with future graph artifact additions |
| B2 | **Target SQLite isolated from event loop** | `routers/targets.py` | Blocking SQLite work runs in `run_in_threadpool()` | Consider aiosqlite only if write/concurrency needs grow |
| B3 | **Target detail compound query** | `GET /targets/{id}` | Target, edges, and xrefs resolved through one helper/query path | Keep response shape stable |
| B4 | **Search/list gaps bounded** | `/drugs/search`, `/diseases/search/{q}`, `/diseases/region/{r}`, `/diseases/{id}/drugs`, `/drugs/category/{c}` | `limit`/`offset` with caps | Keep README endpoint table in sync |
| B5 | **Disease tree pagination added** | `/tree/disease/{id}` | No silent `[:20]` truncation | `limit` default 20, cap 100 |
| B6 | **Former sync `requests` files migrated** | see §3 | Uses `httpx` fallback behavior | Keep new ETL integrations on `httpx` |
| B7 | **Named ETL/validation split targets completed** | `atc_orchestrator`, `drug_etl`, `disease_etl`, `validation_pipeline` | Public wrappers are now small and stage helpers are explicit; focused tests cover the split | Remaining large non-plan modules (`graph_queries.py`, `audit_logger.py`, `load_graph_edges.py`) are separate future work |
| B8 | **Duplicate `__all__`** | `services/__init__.py` | Export drift risk | Don't add exports there; `main.py` imports routers directly |

**Performance note:** the in-memory model is fast for reads but assumes the dataset fits in process memory (it does today: ~5.5 MB drugs, ~100 KB diseases). Snapshot and graph caches are warmed at startup; target SQLite reads are still local file reads, but no longer run on the event loop.

---

## 7. How To Extend (Recipes)

- **Add an endpoint:** add a route to the relevant `routers/*.py`, delegate to a service (create one if logic is non-trivial), return a Pydantic model, add pagination if it lists. Document it in `README.md`.
- **Add a data field:** update ETL to populate it in `data/*.json`, extend the Pydantic model, regenerate embeds, then surface it in the frontend (mode-gated if expert-only — see UI-Architecture §8).
- **Add a graph relation:** extend the graph artifacts in `data/graph/`, ensure `graph_index.py` indexes it, expose via `graph_queries.py` and `routers/graph.py`.
- **Change canonical data:** edit `data/` → run validators → `python3 scripts/build_frontend_embeds.py` → `POST /api/v1/admin/refresh` or restart backend.

---

## 8. Reference Docs

- Per-module: `src/backend/AGENTS.md`, `routers/AGENTS.md`, `services/AGENTS.md`, `models/AGENTS.md`, `etl/AGENTS.md`
- Module contracts: `docs/modules/graph-data-contract.md`, `graph-schema.md`, `graph-transition-plan.md`, `lineage-model.md`, `disease-model.md`, `target-layer-readiness.md`
- Workflows: `docs/operations/data-update-workflow.md`, `docs/operations/release-gates.md`
- Performance: `docs/operations/benchmark-contract.md`
- Product intent: `docs/product/project-plan.md` (design log; note internal version drift toward the 14-region ontology model)
