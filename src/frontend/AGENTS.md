# DrugTree Frontend - Application Guide

## Overview

Frontend for the DrugTree atlas and disease graph.

**Stack**: Vanilla JS + RDKit.js  
**Canonical data source**: repo-root `data/`  
**Generated frontend data**: `src/frontend/data/`

## Key Files

```text
src/frontend/
├── index.html
├── css/style.css
├── js/app.js
├── js/components/disease-panel.js
├── js/stores/graphStore.js
└── data/
    ├── drugs.json
    ├── diseases.json
    ├── disease-drug-edges.json
    ├── body-ontology.json
    └── *.js                 # embedded globals generated from root data
```

## Current Data Flow

- Canonical drug data lives in `data/drugs.json`
- Canonical disease data lives in `data/diseases.json`
- Canonical disease-drug edges live in `data/disease_drug_edges.json`
- `scripts/build_frontend_embeds.py` mirrors those files into `src/frontend/data/`
- `app.js` should prefer backend APIs when available and fall back to the generated local embeds

## Critical Behaviors

- `DrugTreeApp.init()` loads drugs, diseases, disease-drug edges, and body ontology before graph boot
- Disease filtering should use explicit edge-linked `drug_id`s, not same-body-region inference
- `GraphStore.loadGraph()` now expects an object payload with `drugs`, `diseases`, `bodyOntology`, and `diseaseDrugEdges`
- Keep the 1200ms hover delay behavior intact

## Common Tasks

```bash
# Serve frontend
cd src/frontend && python3 -m http.server 8080

# Regenerate embedded data after ETL changes
python3 scripts/build_frontend_embeds.py
```

- Add or edit canonical datasets under repo-root `data/`, then regenerate embeds
- Do not hand-edit generated `src/frontend/data/*.js` files unless you are fixing the generator itself
- Do not reintroduce fallback reads from `drugs-full.json` or `drugs-expanded.json`
