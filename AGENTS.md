# DrugTree - Project Knowledge Base

**Generated:** 2026-03-31
**Commit:** e37b5b1 | **Branch:** main

Visual drug exploration tool: human body atlas, ATC classification, route-aware drug detail, drug genealogy, graph knowledge engine, ATC-aware disease graph.

**Stack**: Vanilla JS + RDKit.js (frontend) | FastAPI + SQLite (backend) | JSON/ETL pipelines (data) | Playwright (e2e)

## Project Structure

```text
DrugTree/
├── data/                          # canonical data layer (root of truth)
│   ├── drugs.json                 # 7,359 drugs {"drugs": [...]}
│   ├── diseases.json              # 50 diseases {"diseases": [...]}
│   ├── disease_drug_edges.json    # disease↔drug edges
│   ├── ontology/body-ontology.json
│   ├── processed/                 # derived: families, lineages
│   ├── curated/                   # manual overrides
│   ├── seeds/                     # ETL seed data
│   ├── changes/                   # change-log entries (local state)
│   ├── checkpoints/               # ETL progress snapshots
│   └── reports/                   # ETL reports
├── src/frontend/                  # vanilla JS atlas UI
│   ├── js/app.js                  # DrugTreeApp class (2145 lines)
│   ├── js/components/             # approval-chips, disease-panel, mechanism-card, orphan-badge
│   ├── js/stores/                 # graphStore, selectionStore
│   ├── js/views/                  # diseaseView, genealogyView
│   └── data/                     # GENERATED embeds (not canonical)
├── src/backend/                   # FastAPI + SQLite service
│   ├── routers/                   # admin, diseases, drugs, graph
│   ├── models/                    # Pydantic + DB schemas (12 files)
│   ├── services/                  # graph engine, validation, audit (8 files)
│   ├── etl/                       # data pipelines (23 files)
│   ├── db/                        # SQLite connection & schema
│   └── migrations/                # SQL migrations
├── scripts/                       # build_frontend_embeds.py, data utils
├── tests/
│   ├── backend/                   # pytest (23 files)
│   └── frontend/                  # Playwright e2e + Node integration
├── docs/                          # architecture docs, specs
└── package.json                   # Playwright only (root-level)
```

## Where to Look

| Task | Location | Notes |
|------|----------|-------|
| Add/edit drug data | `data/drugs.json` → `scripts/build_frontend_embeds.py` | Never edit `src/frontend/data/` directly |
| Add disease relationships | `data/disease_drug_edges.json` | Edge-backed filtering, not body-region inference |
| ATC enrichment | `src/backend/etl/atc_orchestrator.py` | Orchestrates ChEMBL/KEGG/PubChem batch pipelines |
| Graph engine | `src/backend/services/graph_index.py` | In-memory adjacency index |
| Drug genealogy | `src/backend/etl/lineage_builder.py` | Follow-on/derivative edge scoring |
| Drug families | `src/backend/etl/family_builder.py` | Target/mechanism grouping |
| Frontend routing | `src/frontend/js/app.js` → `handleHashChange()` | Hash-based `#drug/{id}` routing |
| E2e regression | `tests/frontend/e2e/p0-regression.spec.ts` | High-signal route/detail/disease tests |
| API endpoints | `src/backend/main.py` + `routers/` | All prefixed `/api/v1/` |

## Conventions

- **No CI/CD**: No GitHub Actions, no Docker. All builds/tests are manual.
- **No framework**: Frontend is vanilla JS (no React/Vue). No build step.
- **Dual-stack monorepo**: Single repo, two independent stacks, API-only communication.
- **Generated data**: `src/frontend/data/*.json` and `*.js` are mirrors of canonical `data/` — never edit directly.
- **Port assignments**: 8080 (frontend dev), 8000 (backend), 8765 (backend API test), 8766 (Playwright test harness).
- **Root Playwright**: `package.json` at root has Playwright only; no npm scripts defined.

## Anti-Patterns (This Project)

- Do NOT treat `src/frontend/data/*.json` as canonical input
- Do NOT depend on `drugs-full.json` or `drugs-expanded.json` at runtime
- Do NOT regress `#drug-detail-page` to modal-only behavior
- Do NOT clear ATC state as side effect of disease selection
- Do NOT commit `drugtree.db` or `*.sqlite` files
- Do NOT hand-edit generated `src/frontend/data/*.js` files
- Keep valid ATC codes stable; only placeholder `*99XX99` codes are enrichment targets
- Wrap all external API calls (ChEMBL, KEGG, PubChem, FDA) in try/except with graceful degradation
- Use `async def` with `httpx` for backend — no sync requests
- Always validate with Pydantic models; add pagination to queries

## Commands

```bash
# Frontend
cd src/frontend && python3 -m http.server 8080

# Backend
uvicorn src.backend.main:app --reload --port 8000

# ETL refresh (full pipeline)
bash src/backend/run_etl.sh

# Frontend embeds only (after data changes)
python3 scripts/build_frontend_embeds.py

# Backend tests
pytest tests/backend/

# Frontend e2e
npx playwright test --config tests/frontend/playwright.config.ts

# Frontend data integration
node tests/frontend/e2e/disease-universe.mjs
```

## Notes

- `data/amr_pub_atc/` contains AMR publication-to-ATC mapping data
- `data/changes/` has 183 UUID-named JSON change-log files (local state, not committed)
- `.sisyphus/` is agent planning state — not project source
- CORS allows `localhost:8080`, `localhost:8765`, and `https://chendeepin.github.io`
- `docs/architecture/release-gates.md` defines wave-based release progression (documentation only, not enforced in code)

## References

- `src/frontend/AGENTS.md` — frontend architecture
- `src/backend/AGENTS.md` — backend API & services
- `src/backend/etl/AGENTS.md` — ETL pipeline patterns
- `src/backend/models/AGENTS.md` — data models & schemas
- `src/backend/services/AGENTS.md` — business logic & graph engine
- `src/frontend/js/AGENTS.md` — JS architecture & components
- `tests/AGENTS.md` — test patterns & conventions
