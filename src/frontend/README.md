# DrugTree Frontend

## Overview

The frontend is a static Vanilla JS atlas UI that can run against the FastAPI backend or against generated local embed files.

## Data Model

- Canonical source data lives at repo-root `data/`
- `src/frontend/data/` contains generated mirrors plus JS globals for file-safe mode
- The disease UI now depends on:
  - `data/diseases.json`
  - `data/disease_drug_edges.json`
  - `data/ontology/body-ontology.json`

## Development

```bash
cd src/frontend
python3 -m http.server 8080
```

Open `http://localhost:8080`.

The FastAPI backend on port `8000` is API-only. It does not render the atlas UI unless you separately open the static frontend entrypoint above.

## Refreshing Embedded Data

```bash
python3 scripts/build_frontend_embeds.py
```

Run this after updating any canonical dataset under `data/`.

## Notes

- Do not add new frontend-only canonical datasets under `src/frontend/data/`
- Do not reintroduce `drugs-full.json` or `drugs-expanded.json` as runtime dependencies
- Disease filtering should stay explicit-edge-based
