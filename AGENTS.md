# DrugTree - Project Knowledge Base

## Overview

**DrugTree**: Visual drug exploration tool with interactive human body map + ATC therapeutic classification.

**Tech**: Vanilla JS + RDKit.js (frontend) | FastAPI Python (backend) | ChEMBL + DrugBank + PubChem (data)

**Scale**: 57 files, 4448 LOC, 61 drugs | Large: `drug_etl.py` (819), `app.js` (992), `style.css` (1158)

---

## Project Structure

```
DrugTree/
├── src/frontend/          # Main web app (Vanilla JS)
│   ├── index.html         # Entry (227 lines)
│   ├── js/app.js          # DrugTreeApp class (992 lines)
│   └── data/drugs-full.json  # 61 drugs
├── src/backend/           # FastAPI service (Phase 2)
│   ├── main.py            # Entry (89 lines)
│   ├── routers/drugs.py   # REST endpoints (203 lines)
│   └── etl/drug_etl.py    # ETL pipeline (819 lines)
├── data/                  # Drug data + body ontology
├── tests/                 # pytest + Playwright tests
└── docs/                  # PROJECT_PLAN.md (2278 lines)
```

---

## Core Concepts

**ATC Categories (14)**: A (Alimentary), B (Blood), C (Cardiovascular), D (Dermatological), G (Genito-urinary), H (Hormones), J (Anti-infectives), L (Antineoplastic), M (Musculo-skeletal), N (Nervous), P (Antiparasitic), R (Respiratory), S (Sensory), V (Various)

**Body Regions (14)**: Interactive SVG map with clickable regions mapped to ATC categories.

**DrugTreeApp State**: `drugs`, `filteredDrugs`, `selectedDrug`, `activeCategory`, `activeBodyRegion`, `mode`

---

## Key Files

| File | Size | Purpose |
|------|------|---------|
| `src/frontend/index.html` | 227 lines | Entry point |
| `src/frontend/js/app.js` | 992 lines | DrugTreeApp class |
| `src/frontend/css/style.css` | 1158 lines | Dark atlas theme |
| `src/frontend/data/drugs-full.json` | 61 drugs | Drug data |
| `src/backend/etl/drug_etl.py` | 819 lines | ETL pipeline |
| `data/ontology/body_ontology.json` | 14 regions | Body mapping |

---

## Development

```bash
# Start local server
cd src/frontend && python3 -m http.server 8080

# Run backend tests
cd src/backend && pytest

# Run frontend tests
cd tests/frontend && node test_runner.mjs
```

---

## Critical Anti-patterns

- **NEVER** modify curated drugs in `drugs-full.json`
- **NEVER** modify original edge objects in lineage
- **NO** multi-select ATC filter (MVP single-select only)
- **NO** biologics/peptides (small molecules only)
- **ALWAYS** use 1200ms hover delay for previews
- **ALWAYS** wrap external API calls in try/except

---

## Testing

- **Backend**: pytest (15 test files in `tests/backend/`)
- **Frontend**: Playwright E2E (7 test files in `tests/frontend/`)

---

## Next Steps

- Phase 2: FastAPI backend + ChEMBL API integration
- Phase 3: 3D structure viewer (3Dmol.js)
- Phase 4: Scale to 1000+ drugs

---

## References

- `docs/PROJECT_PLAN.md` - Full specification
- `src/frontend/AGENTS.md` - Frontend guide
- `src/backend/AGENTS.md` - Backend guide
- [WHO ATC Classification](https://www.whocc.no/atc_ddd_index_and_excisions/)

