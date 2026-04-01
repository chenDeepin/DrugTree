# 🌳 DrugTree

> A visual universe of drugs — explore structures, therapeutic areas, drug genealogy, and disease hierarchies at a glance.

## Vision

**Problem**: Drug databases are fragmented, require logins, and hide structures behind captchas. It's hard to see how drugs relate across generations or therapeutic areas.

**Solution**: An interactive human body atlas showing all approved small-molecule drugs, with deep-linkable drug detail pages, zoomable genealogy trees, and ATC-aware disease navigation.

## Features

### Core Features
- 🗺️ **Central Body Atlas** - Interactive human body with clickable organs and floating ATC tags
- 🧬 **Structure Viewer** - Instant 2D molecular visualization via RDKit.js
- 🧭 **Route-Aware Drug Detail Pages** - Open any drug as a deep-linkable `#drug/{id}` detail surface with browser-back support
- 🌳 **Drug Genealogy** - See how drugs evolved across generations (parent drugs → successors)
- 🦠 **Disease Navigation** - Browse drugs by an ATC-aware disease hierarchy that prunes empty branches from the visible tree
- 🔍 **Dual Display Modes** - Public (simplified) and Scientist (detailed) views
- 🔎 **Genealogy Zoom Controls** - Zoom in, zoom out, and reset the lineage tree in scientist detail views

### Data Features
- **7,359 Small-Molecule Drugs** from ChEMBL, KEGG, DrugBank, and FDA sources
- **55.4% ATC Coverage** (4,079 drugs with valid ATC codes, 3,280 awaiting enrichment)
- **14 ATC Level 1 Categories** with color-coded navigation
- **14 Body Regions** mapped to therapeutic areas
- **Drug Families** - Group related drugs by mechanism/target
- **Drug Lineages** - Track evolutionary relationships
- **Drug Targets** - Protein target lookup with disease associations
- **Graph Knowledge Engine** - Unified drug-disease-target graph with evidence
- **Source Provenance** - Track where each drug's data originated
- **Canonical Root Data Files** - frontend embeds are generated from repo-root datasets

## Quick Start

```bash
# Clone
git clone https://github.com/chenDeepin/DrugTree.git
cd DrugTree

# Start frontend (static server)
cd src/frontend
python3 -m http.server 8080

# Open in browser
open http://localhost:8080

# Optional backend (FastAPI + SQLite)
uvicorn src.backend.main:app --reload --port 8000

# Frontend regression tests
npx playwright test --config tests/frontend/playwright.config.ts

# Frontend data integration checks
node tests/frontend/e2e/disease-universe.mjs
```

> **Test harness note**: `tests/frontend/playwright.config.ts` serves the frontend on `http://localhost:8766` to avoid collisions with a backend/API service on `8765`.

> **Important**: `http://127.0.0.1:8000/` is the API service, not the atlas UI. Open the static frontend URL (`http://127.0.0.1:8080/`) to review the body map and drug data in a browser.

## Architecture

### UI Layout: Central Body Atlas

```
┌─────────────────────────────────────────────────────────┐
│  Topbar (Glassmorphism)                                 │
│  [DrugTree] [Search...] [Clear] [Public/Scientist]      │
├─────────────────────────────────────────────────────────┤
│  Atlas Hero Section                                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │    [N] ←←←  ┌─────────────┐  →→→ [S]             │  │
│  │    [R] ←←   │   Human     │   →→ [C]             │  │
│  │    [L] ←←   │    Body     │   →→ [B]             │  │
│  │    [M] ←←   │   (Glow)    │   →→ [D]             │  │
│  │    [P] ←←   └─────────────┘   →→ [G]             │  │
│  │    [A] ←←                     →→ [H]             │  │
│  │    [J] ←←                     →→ [V]             │  │
│  └───────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│  Active Filters: [ATC: C ✕] [Search: statin ✕]         │
├─────────────────────────────────────────────────────────┤
│  Route-aware Detail: /#drug/atorvastatin                │
│  Deep-linkable detail page with structure + genealogy   │
├─────────────────────────────────────────────────────────┤
│  Matching Drugs (X results)                              │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐              │
│  │Drug1│ │Drug2│ │Drug3│ │Drug4│ │Drug5│ ...          │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘              │
└─────────────────────────────────────────────────────────┘
```

### Project Structure

```
DrugTree/
├── data/
│   ├── drugs.json                    # canonical drug database (7,359 drugs)
│   ├── diseases.json                 # disease hierarchy (50 diseases)
│   ├── disease_drug_edges.json       # disease-drug relationships
│   ├── ontology/body-ontology.json   # body region definitions
│   ├── processed/                    # derived data (families, lineages)
│   ├── curated/                      # manual overrides
│   ├── seeds/                        # seed data for ETL
│   └── changes/                      # change-log entries
├── scripts/
│   └── build_frontend_embeds.py      # regenerate frontend data embeds
├── src/
│   ├── frontend/                     # Vanilla JS web app
│   │   ├── index.html               # Entry point
│   │   ├── css/style.css            # Dark atlas theme
│   │   ├── assets/                   # SVG body atlas
│   │   ├── js/
│   │   │   ├── app.js               # DrugTreeApp class
│   │   │   ├── app-state.js         # State management helpers
│   │   │   ├── structure.js         # RDKit.js molecule viewer
│   │   │   ├── components/          # UI components
│   │   │   ├── stores/              # State stores
│   │   │   └── views/               # View renderers
│   │   └── data/                    # generated mirrors/embeds
│   └── backend/                      # FastAPI + SQLite service
│       ├── main.py                  # Entry point
│       ├── run_etl.sh               # ETL pipeline launcher
│       ├── routers/                 # API route modules (drugs, diseases, targets, graph, admin)
│       ├── models/                  # Pydantic & DB models
│       ├── services/                # Business logic & graph engine
│       ├── etl/                     # drug / disease / ATC / target pipelines
│       ├── db/                      # SQLite connection & schema
│       ├── migrations/              # SQL migrations
│       ├── cache/                   # API response caching
│       ├── export/                  # Data exporters
│       └── validation/              # Migration & data validators
└── tests/
    ├── backend/                      # pytest suites
    └── frontend/                     # Playwright e2e + Node tests
        └── e2e/p0-regression.spec.ts # route/detail/disease high-signal regressions
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vanilla JS + RDKit.js |
| Backend | FastAPI (Python) + SQLite |
| Data | ChEMBL + DrugBank + PubChem + KEGG + FDA |
| E2E Tests | Playwright |
| Hosting | GitHub Pages (MVP) |

## ATC Categories (14 Total)

| Code | Category | Color | Drugs (valid ATC) |
|------|----------|-------|-------------------|
| A | Alimentary & Metabolism | Green | ~300+ |
| B | Blood & Blood-forming | Red | ~250+ |
| C | Cardiovascular | Pink | ~400+ |
| D | Dermatological | Orange | ~200+ |
| G | Genito-urinary | Purple | ~250+ |
| H | Systemic Hormones | Brown | ~150+ |
| J | Anti-infectives | Blue | ~800+ |
| L | Antineoplastic | Dark Red | ~600+ |
| M | Musculo-skeletal | Grey | ~200+ |
| N | Nervous System | Deep Purple | ~700+ |
| P | Antiparasitic | Teal | ~100+ |
| R | Respiratory | Cyan | ~300+ |
| S | Sensory Organs | Indigo | ~150+ |
| V | Various | Grey | ~3,097 (many need re-classification) |

> **Note**: Exact counts vary as ATC enrichment continues. See `/data/drugs.json` for current state.

## Data Schemas

### Drug Schema
```json
{
  "id": "atorvastatin",
  "name": "atorvastatin",
  "smiles": "CC(C)OC(=O)C(C)(C)Oc1ccc(C(=O)c2ccc(Cl)cc2)cc1",
  "inchikey": "YMTINGFKWWXKFG-UHFFFAOYSA-N",
  "atc_code": "C10AA05",
  "atc_category": "C",
  "molecular_weight": 360.84,
  "phase": "IV",
  "year_approved": null,
  "generation": 1,
  "indication": "approved",
  "targets": [],
  "company": null,
  "synonyms": [],
  "class": null,
  "body_region": "blood_immune",
  "secondary_body_regions": ["eye_ear", "heart_vascular", "kidney_urinary", "liver_biliary_pancreas"],
  "chembl_id": "CHEMBL1487",
  "kegg_id": "D00565",
  "clinical_trials": ["NCT00504829", "NCT00362323"]
}
```

### Drug Family Schema
```json
{
  "family_id": "target_hmg_coa_reductase_7169b791",
  "label": "Hmg Coa Reductase Target Family",
  "family_basis": "target",
  "prototype_drug_id": "atorvastatin",
  "member_drug_ids": ["atorvastatin", "simvastatin", "lovastatin", "pravastatin"],
  "representative_target_ids": ["HMG-CoA reductase"],
  "description": "Drugs targeting hmg coa reductase",
  "atc_codes": ["C10AA05", "C10AA01", "C10AA02", "C10AA03"]
}
```

### Lineage Edge Schema
```json
{
  "edge_id": "omeprazole_to_lansoprazole",
  "from_drug_id": "omeprazole",
  "to_drug_id": "lansoprazole",
  "edge_type": "follow_on",
  "confidence": 0.843,
  "rationale_tags": [],
  "score_breakdown": {
    "chronology_score": 1.0,
    "mechanism_score": 1.0,
    "scaffold_score": 0.478
  },
  "provenance": "auto",
  "explanation": "Lansoprazole (1995) derived from Omeprazole (1989) | scores: chronology=1.0, mechanism=1.0, scaffold=0.48"
}
```

## Backend API Endpoints

All endpoints are prefixed with `/api/v1`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/drugs` | GET | List all drugs (with pagination, filters: `category`, `search`, `phase`) |
| `/api/v1/drugs/{id}` | GET | Get drug by ID |
| `/api/v1/drugs/search` | GET | Search drugs by name, target, class, or synonyms (`?q=query`) |
| `/api/v1/drugs/category/{category}` | GET | Filter drugs by ATC category (A-V) |
| `/api/v1/families` | GET | List all drug families |
| `/api/v1/families/{family_id}` | GET | Get family by ID |
| `/api/v1/lineages` | GET | List all lineage edges (filters: `drug_id`, `edge_type`) |
| `/api/v1/lineage/{drug_id}` | GET | Get genealogy tree for a drug (with `threshold` param) |
| `/api/v1/regions` | GET | List all body regions from ontology |
| `/api/v1/tree/disease/{disease_id}` | GET | Get body region and drugs for a disease |
| `/api/v1/graph/stats` | GET | Get graph index statistics |
| `/api/v1/graph/node/{node_id}` | GET | Get graph node by namespaced ID |
| `/api/v1/graph/neighborhood/{node_id}` | GET | N-hop neighborhood (`?max_hops=1-5`) |
| `/api/v1/graph/evidence/{edge_id}` | GET | Evidence supporting a graph edge |
| `/api/v1/graph/subgraph` | GET | Subgraph extraction (`?node_ids=a,b,c`) |
| `/api/v1/diseases` | GET | List disease hierarchy |
| `/api/v1/diseases/{id}` | GET | Get disease by ID |
| `/api/v1/diseases/{id}/drugs` | GET | Get drugs for a disease |
| `/api/v1/admin/health/data-quality` | GET | Data quality health check |
| `/api/v1/targets` | GET | List all drug targets (with pagination) |
| `/api/v1/targets/{target_id}` | GET | Get target detail by ID |


## Documentation

- [Project Plan](docs/PROJECT_PLAN.md) — Full architecture and roadmap
- [Central Body Atlas Implementation](docs/CENTRAL_BODY_ATLAS_IMPLEMENTATION.md) — Atlas design
- [Data Update Workflow](docs/DATA_UPDATE_WORKFLOW.md) — ETL pipeline documentation


## License

MIT

## Author

Built by chenDeepin 🎯
