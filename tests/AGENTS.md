# DrugTree Tests - Testing Guide

## Overview

DrugTree uses pytest for backend verification and Node-based browser/data checks for the frontend.

## Canonical Test Inputs

- Drugs: `data/drugs.json`
- Diseases: `data/diseases.json`
- Disease-drug edges: `data/disease_drug_edges.json`
- Ontology: `data/ontology/body-ontology.json`

The generated frontend mirrors under `src/frontend/data/` are test inputs only when a frontend test explicitly exercises embed output.

## Run Commands

```bash
# Focused backend data/graph coverage
pytest tests/backend/test_atc_orchestrator.py tests/backend/test_drug_etl.py tests/backend/test_disease_api.py tests/backend/test_graph_index.py

# Full backend suite
pytest tests/backend/

# Frontend disease/data integration
node tests/frontend/e2e/disease-universe.mjs
```

## Test Expectations

- Backend disease tests should validate canonical disease records plus explicit disease-drug edges
- Frontend disease tests should assert edge-backed filtering, not body-region coincidence
- ATC tests should distinguish valid WHO ATC codes from placeholder `*99XX99` codes
- External API access should be mocked or bypassed in unit tests

## Cleanup

- Remove unused sample fixtures when they no longer back a real test
- Keep new fixtures minimal and deterministic
