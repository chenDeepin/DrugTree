# DrugTree Progress Summary

**Generated:** 2026-03-13

---

## Overview

**DrugTree** is a visual drug exploration tool featuring an interactive human body map with ATC therapeutic classification.

**Development Team:** C + Hephaestus Prime

---

## Goal

Build DrugTree in two phases:
- **Phase 1 (ALIGNED)**: Frontend with Central Body Atlas layout and ontology-driven interaction
- **Phase 2 (IN PROGRESS)**: Backend Integration with FastAPI + ETL pipelines

---

## Phase 1: Frontend - ALIGNED ✅

### Features Implemented
- ✅ Central Body Atlas HTML/CSS/JS implementation
- ✅ Dark atmospheric theme (deep navy `#0f172a`)
- ✅ Semi-anatomical centered body atlas wired to the live UI
- ✅ 14 floating ATC tags positioned around body
- ✅ Dual-filter atlas behavior (ATC + body region intersection)
- ✅ Ontology-aligned body region filtering
- ✅ Public/Scientist mode switching with different detail density
- ✅ Drug detail modal with structure viewer
- ✅ RDKit.js 2D molecule rendering
- ✅ Drug genealogy tracking

### Files Modified
| File | Lines | Description |
|------|-------|-------------|
| `src/frontend/index.html` | - | Central Body Atlas layout + modal/body hooks |
| `src/frontend/css/style.css` | - | Dark atlas theme styling + live body states |
| `src/frontend/js/app.js` | - | DrugTreeApp with ontology-backed atlas integration |
| `src/frontend/js/app-state.mjs` | - | Pure atlas state helpers |
| `src/frontend/js/app-state.js` | - | File-safe browser global wrapper for atlas state |
| `src/frontend/js/structure.js` | - | RDKit.js structure viewer |
| `src/frontend/data/body-ontology.json` | 14 regions | Frontend ontology snapshot |
| `src/frontend/data/drugs.json` | 7,359 drugs | Expanded frontend/backend runtime dataset |
| `src/frontend/data/drugs.js` | 7,359 drugs | File-safe embedded dataset for direct `index.html` launches |

---

## Phase 2: Backend & ETL - IN PROGRESS ⏳

### Backend Structure Created
```
src/backend/
├── __init__.py
├── requirements.txt
├── main.py              # FastAPI entry
├── models/
│   ├── __init__.py
│   └── drug.py          # Pydantic models
├── routers/
│   ├── __init__.py
│   └── drugs.py         # REST API endpoints
└── etl/
    ├── __init__.py
    └── drug_etl.py      # Full ETL pipeline (470+ lines)
```

### ETL Pipeline Complete ✅
- ✅ Extended `etl/drug_etl.py` for offline local-name enrichment
- ✅ Extracted **7,359 approved drug records** from ClinicalMol_hier compound master table
- ✅ Resolved names offline using local KEGG lookup TSVs
- ✅ Inferred ontology-aligned body regions from tissue data (`tissues_union` / `tissue_scores`)
- ✅ Output saved to `drugs.json`, mirrored to `drugs-expanded.json`, and embedded into file-safe JS assets

### Data Source
**ClinicalMol_hier Project:** `/media/chen/Machine_Disk/Python script/ClinicalMol_hier`
- `compound_master_table.tsv`: 22,228 compounds total, 7,379 approved rows
- 7,359 approved rows are usable as named drug records with local structural identity
- Remaining 20 approved rows are placebo-only / non-drug-name rows and are intentionally excluded

### ATC Category Distribution (7,359 drugs)
| ATC Code | Count | Category Name |
|----------|-------|---------------|
| A | 1,049 | Alimentary & Metabolism |
| B | 239 | Blood & Blood-forming |
| C | 478 | Cardiovascular |
| D | 29 | Dermatological |
| G | 19 | Genito-urinary |
| H | 3 | Systemic Hormones |
| M | 9 | Musculo-skeletal |
| R | 58 | Respiratory |
| S | 23 | Sensory Organs |
| V | 5,452 | Various |

### Frontend Integration
- ✅ Updated `app.js` to load from backend API with fallback to the expanded local JSON
- ✅ Added ontology-driven body map loading
- ✅ Added direct `file://` launch support through embedded JS assets for body SVG, ontology, and drugs
- ✅ Added mode-aware card and modal rendering
- ✅ Added loading state UI and error handling for API failures

---

## Known Issues 🐛

- The expanded dataset is much larger than the MVP snapshot, so pagination or virtualization is still a worthwhile follow-up for very broad result sets.
- ATC inference remains heuristic when the local source data does not provide richer therapeutic annotations.

---

## Data Files

| File | Drugs | Size | Status |
|------|-------|------|--------|
| `drugs-full.json` | 61 | 35KB | Original Phase 1 data |
| `drugs-expanded.json` | 7,359 | - | ETL mirror output |
| `drugs.json` | 7,359 | - | Backend/frontend runtime data |
| `drugs.js` | 7,359 | - | File-safe embedded frontend runtime data |

---

## Running the Application

### Start Backend
```bash
cd /media/chen/Machine_Disk/AgentDrugDiscov/Telegram_sessions/DrugTree/src
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### Start Frontend (Local Dev Server)
```bash
cd /media/chen/Machine_Disk/AgentDrugDiscov/Telegram_sessions/DrugTree/src/frontend
python3 -m http.server 8765
# Open http://localhost:8765
```

### Current Ports
- Frontend: `http://localhost:8765`
- Backend: `http://127.0.0.1:8000`

---

## API Endpoints

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/health` | GET | Health check + drug count | ✅ Uses `drugs.json` |
| `/api/v1/drugs` | GET | List all drugs | ✅ Returns expanded data |
| `/api/v1/drugs/{id}` | GET | Get single drug | ✅ Works |
| `/api/v1/drugs/search/{query}` | GET | Search drugs | ✅ Works |
| `/api/v1/stats` | GET | Drug statistics | ✅ Works |

---

## Tech Stack

### Frontend
- **Framework:** Vanilla JavaScript (ES6+)
- **Visualization:** D3.js, RDKit.js
- **Styling:** CSS3 with CSS Variables (dark theme)
- **Data:** Static JSON (Phase 1) → Backend API (Phase 2)

### Backend
- **Framework:** FastAPI (Python 3.9+)
- **Data Validation:** Pydantic
- **Server:** Uvicorn ASGI

### Data Sources (Priority Order)
1. **KEGG Drug** - Primary source (via ClinicalMol_hier)
2. **PubChem** - Structure data (SMILES, InChI)
3. **ChEMBL** - Backup for bioactivity

---

## Key Discoveries

1. **ClinicalMol_hier has pre-processed local KEGG lookup data** - huge time saver
2. **compound_master_table.tsv has 22,228 compounds** - Scalable foundation
3. **tissues_union / tissue_scores enable ontology placement** - enough to drive the atlas
4. **25 approved rows are placebo-only entries** - excluded from the live dataset
5. **Python reserved keyword issue** - `class` → `class_name` with alias

---

## ATC Categories (14 Total)

| Code | Name | Color |
|------|------|-------|
| A | Alimentary & Metabolism | Green `#27ae60` |
| B | Blood & Blood-forming | Red `#e74c3c` |
| C | Cardiovascular | Pink `#e91e63` |
| D | Dermatological | Orange `#ff9800` |
| G | Genito-urinary | Purple `#9c27b0` |
| H | Systemic Hormones | Brown `#795548` |
| J | Anti-infectives | Blue `#2196f3` |
| L | Antineoplastic | Dark Red `#f44336` |
| M | Musculo-skeletal | Grey `#607d8b` |
| N | Nervous System | Deep Purple `#673ab7` |
| P | Antiparasitic | Teal `#009688` |
| R | Respiratory | Cyan `#00bcd4` |
| S | Sensory Organs | Indigo `#3f51b5` |
| V | Various | Grey `#9e9e9e` |

---

## Next Steps

### Immediate
1. [ ] Verify frontend responsiveness with the larger dataset in real browser use
2. [ ] Add pagination or virtualization for broad result sets
3. [ ] Refine ATC/body placement inference beyond current heuristics

### Short-term
4. [ ] Test all 14 ontology regions against the expanded dataset
5. [ ] Verify body region filtering works with the new body placement fields
6. [ ] Test search functionality with 7,359 records

### Medium-term
8. [ ] KEGG enrichment for remaining 5,871 drugs
9. [ ] Add ChEMBL bioactivity data
10. [ ] Implement drug comparison tool
11. [ ] Add 3D structure viewer (3Dmol.js)

### Long-term
12. [ ] Deploy backend to cloud (Railway/Render)
13. [ ] Scale to 2,000+ drugs
14. [ ] Performance optimization
15. [ ] Add clinical trial data integration

---

## Constraints

- **Approved small-molecule drugs only** for v1
- **Mode switch must not reload different dataset** - same data, different visibility
- **Body must be visually dominant** in UI
- **Desktop-first design** - mobile responsive secondary
- **No authentication required** for MVP (rate limiting only)
- **KEGG Drug as primary data source** - user preference

---

## References

- [PROJECT_PLAN.md](docs/PROJECT_PLAN.md) - Full specification (2,278 lines)
- [CENTRAL_BODY_ATLAS_IMPLEMENTATION.md](docs/CENTRAL_BODY_ATLAS_IMPLEMENTATION.md) - UI transformation guide
- [README.md](README.md) - Project overview
- [AGENTS.md](AGENTS.md) - Project knowledge base
- [RDKit.js](https://www.rdkitjs.com/) - Structure rendering library
- [WHO ATC Classification](https://www.whocc.no/atc_ddd_index_and_excisions/) - ATC system reference

---

## Session History

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Frontend Central Body Atlas | ✅ Complete |
| ETL | Data pipeline from ClinicalMol_hier | ✅ Complete |
| Backend | FastAPI structure | ✅ Created |
| Integration | Frontend ↔ Backend API | ⏳ In Progress |
| Bug Fix | main.py data file path | ⏳ Pending |

---

## Contact & Credits

**Developed by:** C + Hephaestus Prime

**Data Sources:**
- KEGG Drug Database
- ClinicalMol_hier Project
- PubChem
- ChEMBL

---

*Last Updated: 2026-03-13*
