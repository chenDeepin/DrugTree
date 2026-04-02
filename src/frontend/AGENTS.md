# DrugTree Frontend Guide

## OVERVIEW
Vanilla JS DrugTree UI, RDKit.js for structures, no framework, no build step.

## KEY FILES
- `js/app.js`, `DrugTreeApp`, constructor, `init()`, event binding, render flow, hash routing (2436 lines)
- `js/app-state.js`, `DrugTreeState`
- `js/stores/graphStore.js`, `js/stores/selectionStore.js`, custom event pub/sub
- `js/structure.js`, RDKit.js 2D molecule rendering
- `js/components/approval-chips.js`, `disease-panel.js`, `mechanism-card.js`, `orphan-badge.js`
- `js/views/diseaseView.js`, ATC-aware tree rendering
- `js/views/genealogyView.js`, D3-like zoomable tree
- `data/`, generated embeds only, never canonical source

## ARCHITECTURE
- Main shell lives in `DrugTreeApp` — global-script based (not ES modules)
- Route changes use `handleHashChange()`, deep link shape `#drug/{id}`
- Public mode, Scientist mode toggle, different detail density
- Disease view prunes by explicit disease-drug edges, not body-region guessing
- Body region hover previews keep the 1200ms delay

## DATA FLOW
- Load order, API first, local embed fallback
- `loadDrugData()`
- `loadDiseaseData()`
- `loadDiseaseDrugEdges()`
- `loadBodyOntology()`
- Root `data/` is canonical
- `scripts/build_frontend_embeds.py` generates `src/frontend/data/`
- Frontend embeds mirror root datasets, they are derived only

## CONVENTIONS
- Prefer direct DOM returns from component functions
- Keep state changes inside stores, not ad hoc globals
- Preserve route state and back button behavior
- Keep ATC and disease trees aligned with backend payload shapes

## ANTI-PATTERNS
- No edits to generated `src/frontend/data/*.js` or `*.json`
- No runtime dependency on `drugs-full.json` or `drugs-expanded.json`
- No same-region disease inference
- No removal of Scientist mode detail, route deep links, or hover delay
