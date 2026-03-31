# DrugTree - Project Knowledge Base

## Overview

**DrugTree** is a visual drug exploration tool built around a human body atlas, ATC therapeutic classification, route-aware drug detail pages, drug genealogy, a graph knowledge engine, and an ATC-aware disease graph.

**Stack**: Vanilla JS + RDKit.js (frontend) | FastAPI Python + SQLite (backend) | JSON/ETL pipelines (data) | Playwright (e2e tests)

## Current Repo Reality

- Canonical drug source: `data/drugs.json` — dict `{"drugs": [...], ...}` with 7,359 drugs
- Canonical disease source: `data/diseases.json` — dict `{"diseases": [...], "metadata": {...}}` with 50 diseases
- Canonical disease-drug edge source: `data/disease_drug_edges.json`
- Canonical ontology source: `data/ontology/body-ontology.json`
- Processed/derived outputs: `data/processed/drug_families.json`, `data/processed/lineage_edges.json`
- Frontend `src/frontend/data/*.json` and `*.js` files are generated embeds, not the source of truth
- Root `package.json` holds Playwright for e2e; frontend tests live in `tests/frontend/`
- Primary drug detail UI is the page-level `#drug-detail-page` route (`#drug/{id}`), not the legacy modal overlay
- Disease view rendering is ATC-aware and prunes empty branches from the visible disease→drug tree
- High-signal regression coverage lives in `tests/frontend/e2e/p0-regression.spec.ts`

## Project Structure

```text
DrugTree/
├── data/
│   ├── drugs.json                    # canonical drug database (7,359 drugs)
│   ├── diseases.json                 # disease hierarchy (50 diseases)
│   ├── disease_drug_edges.json       # disease ↔ drug relationships
│   ├── ontology/body-ontology.json   # body region definitions
│   ├── processed/                    # derived data (families, lineages)
│   ├── curated/                      # manual overrides
│   ├── seeds/                        # seed data for ETL
│   ├── changes/                      # change-log entries
│   ├── checkpoints/                  # ETL progress snapshots
│   └── reports/                      # ETL & analysis reports
├── scripts/
│   └── build_frontend_embeds.py      # regenerate frontend data embeds
├── src/frontend/
│   ├── index.html
│   ├── css/style.css
│   ├── assets/                       # SVG body atlas
│   ├── js/
│   │   ├── app.js                    # main DrugTreeApp class
│   │   ├── app-state.js              # application state management
│   │   ├── structure.js              # RDKit.js molecule viewer
│   │   ├── components/               # UI components
│   │   │   ├── approval-chips.js
│   │   │   ├── disease-panel.js
│   │   │   ├── mechanism-card.js
│   │   │   └── orphan-badge.js
│   │   ├── stores/                   # state stores
│   │   │   ├── graphStore.js
│   │   │   └── selectionStore.js
│   │   └── views/                    # view renderers
│   │       ├── diseaseView.js
│   │       └── genealogyView.js
│   └── data/                         # generated mirrors/embeds (NOT canonical)
├── src/backend/
│   ├── main.py                       # FastAPI entry point
│   ├── requirements.txt
│   ├── run_etl.sh                    # ETL pipeline launcher
│   ├── routers/                      # API route modules
│   │   ├── admin.py, diseases.py, drugs.py, graph.py
│   ├── models/                       # Pydantic & DB models
│   │   ├── drug.py, disease.py, drug_family.py, lineage.py
│   │   ├── graph.py, nodes.py, audit.py, change.py
│   │   ├── override.py, provenance.py, version.py
│   ├── services/                     # business logic
│   │   ├── graph_index.py, graph_queries.py, tree_builder.py
│   │   ├── validation_pipeline.py, change_detector.py
│   │   ├── audit_logger.py, update_scheduler.py
│   ├── etl/                          # data pipelines
│   │   ├── drug_etl.py, disease_etl.py, atc_orchestrator.py
│   │   ├── family_builder.py, lineage_builder.py
│   │   ├── override_loader.py, dag_validator.py
│   │   ├── atc_batch_chembl.py, atc_batch_kegg.py, atc_batch_pubchem.py
│   │   ├── chembl_client.py, kegg_*.py, pubchem_client.py
│   │   ├── fda_client.py, clinicaltrials_client.py
│   │   └── classify_remaining_drugs.py, reclassify_category_v.py
│   ├── db/                           # SQLite connection & schema
│   │   ├── connection.py, schema/
│   ├── migrations/                   # SQL migrations
│   │   ├── 001_schema.sql, 001_add_disease_tables.sql
│   ├── cache/                        # API response caching
│   ├── export/                       # data exporters
│   │   └── json_exporter.py
│   ├── config/                       # scheduling config
│   └── validation/                   # migration & data validators
├── tests/
│   ├── backend/                      # pytest suites (20+ test files)
│   └── frontend/                     # Playwright e2e + Node integration tests
└── package.json                      # Playwright dependency (root level)
```

## Core Concepts

- **ATC Categories (14)**: A, B, C, D, G, H, J, L, M, N, P, R, S, V
- **Body Regions (14)**: SVG atlas regions aligned to ontology metadata
- **Explicit disease graph**: disease search/panel and disease-drug relationships driven by `data/diseases.json` plus `data/disease_drug_edges.json`, not by body-region coincidence
- **Route-aware drug detail flow**: selecting a drug opens a deep-linkable `#drug/{id}` detail surface with browser-back support
- **ATC-aware disease universe**: the disease tree respects the active ATC filter, removes empty branches, and uses density-aware layout
- **Graph knowledge engine**: multi-entity graph (drugs, diseases, targets, families) with neighborhood queries, evidence, and subgraph extraction
- **Change detection**: all data mutations are logged and auditable

## Development

```bash
# Frontend (static server)
cd src/frontend && python3 -m http.server 8080

# Backend (FastAPI + SQLite)
uvicorn src.backend.main:app --reload --port 8000

# Canonical ETL refresh
bash src/backend/run_etl.sh

# Regenerate frontend embeds only
python3 scripts/build_frontend_embeds.py
```

## Testing

```bash
# Backend test suites
pytest tests/backend/

# Frontend e2e (Playwright)
npx playwright test --config tests/frontend/playwright.config.ts

# Frontend data integration (Node)
node tests/frontend/e2e/disease-universe.mjs
```

Notes:
- `tests/frontend/playwright.config.ts` serves the frontend test harness on `http://localhost:8766` to avoid collisions with a backend/API server on `8765`
- Playwright report artifacts may be generated under nested `playwright-report/` directories and should remain gitignored

## Critical Constraints

- Do not reintroduce runtime dependency on `src/frontend/data/drugs-full.json` or `drugs-expanded.json`
- Do not treat `src/frontend/data/*.json` as canonical input
- Keep valid existing ATC codes stable; placeholder codes are the enrichment target
- Keep disease filtering edge-backed where explicit disease-drug edges exist
- Do not regress the route-aware detail flow back to modal-only behavior; tests should target `#drug-detail-page` and `#drug/{id}`
- Do not clear active ATC state as a side effect of disease selection; only clear stale body-region locks when the explicit disease edge filter takes over
- Wrap external data-source calls in error handling; network lookups must degrade gracefully
- Database files (`drugtree.db`, `*.sqlite`) are local runtime artifacts — never commit
- ETL checkpoints and change logs in `data/changes/` are local state

## References

- `README.md` — project overview & quick start
- `src/frontend/AGENTS.md` — frontend notes
- `src/backend/AGENTS.md` — backend notes
- `tests/AGENTS.md` — testing notes
