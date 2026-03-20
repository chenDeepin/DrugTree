# DrugTree - Project Knowledge Base

## Overview

**DrugTree** is a visual drug exploration tool built around a human body atlas, ATC therapeutic classification, drug genealogy, and an emerging disease graph.

**Stack**: Vanilla JS + RDKit.js (frontend) | FastAPI Python (backend) | JSON/ETL pipelines (data)

## Current Repo Reality

- Canonical drug source: `data/drugs.json`
- Canonical disease source: `data/diseases.json`
- Canonical disease-drug edge source: `data/disease_drug_edges.json`
- Canonical ontology source: `data/ontology/body-ontology.json`
- Frontend `src/frontend/data/*.json` and `*.js` files are generated embeds, not the source of truth
- Current atlas scale: `data/drugs.json` contains 7,359 drugs
- Current disease dataset is still small and ETL-generated from local seed data plus explicit disease-drug edges

## Project Structure

```text
DrugTree/
├── data/
│   ├── drugs.json
│   ├── diseases.json
│   ├── disease_drug_edges.json
│   └── ontology/body-ontology.json
├── scripts/
│   └── build_frontend_embeds.py
├── src/frontend/
│   ├── index.html
│   ├── js/app.js
│   ├── js/stores/graphStore.js
│   └── data/                    # generated mirrors/embeds
├── src/backend/
│   ├── main.py
│   ├── routers/
│   ├── models/
│   └── etl/
│       ├── drug_etl.py
│       ├── disease_etl.py
│       └── atc_orchestrator.py
└── tests/
    ├── backend/
    └── frontend/
```

## Core Concepts

- **ATC Categories (14)**: A, B, C, D, G, H, J, L, M, N, P, R, S, V
- **Body Regions (14)**: SVG atlas regions aligned to ontology metadata
- **Explicit disease graph**: disease search/panel and disease-drug relationships should be driven by `data/diseases.json` plus `data/disease_drug_edges.json`, not by body-region coincidence

## Development

```bash
# Frontend
cd src/frontend && python3 -m http.server 8080

# Backend
uvicorn src.backend.main:app --reload --port 8000

# Canonical ETL refresh
bash src/backend/run_etl.sh

# Regenerate frontend embeds only
python3 scripts/build_frontend_embeds.py
```

## Testing

```bash
# Focused backend suites
pytest tests/backend/test_drug_etl.py tests/backend/test_disease_api.py tests/backend/test_graph_index.py

# Frontend disease/data integration
node tests/frontend/e2e/disease-universe.mjs
```

## Critical Constraints

- Do not reintroduce runtime dependency on `src/frontend/data/drugs-full.json` or `drugs-expanded.json`
- Do not treat `src/frontend/data/*.json` as canonical input
- Keep valid existing ATC codes stable; placeholder codes are the enrichment target
- Keep disease filtering edge-backed where explicit disease-drug edges exist
- Wrap external data-source calls in error handling; network lookups must degrade gracefully

## References

- `README.md` - project overview
- `src/frontend/AGENTS.md` - frontend notes
- `src/backend/AGENTS.md` - backend notes
- `tests/AGENTS.md` - testing notes
