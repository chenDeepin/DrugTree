# 🌳 DrugTree

> A visual universe of drugs — explore structures, therapeutic areas, drug genealogy, and disease hierarchies at a glance.

## Vision

**Problem**: Drug databases are fragmented, require logins, and hide structures behind captchas. It's hard to see how drugs relate across generations or therapeutic areas.

**Solution**: An interactive human body atlas showing all approved small-molecule drugs, with one-click structure viewing, drug genealogy trees, and disease navigation.

## Features

### Core Features
- 🗺️ **Central Body Atlas** - Interactive human body with clickable organs and floating ATC tags
- 🧬 **Structure Viewer** - Instant 2D molecular visualization via RDKit.js
- 🌳 **Drug Genealogy** - See how drugs evolved across generations (parent drugs → successors)
- 🦠 **Disease Navigation** - Browse drugs by disease hierarchy (ICD-10 style)
- 🔍 **Dual Display Modes** - Public (simplified) and Scientist (detailed) views

### Data Features
- **61 Approved Small-Molecule Drugs** with verified SMILES and full ATC classification
- **14 ATC Level 1 Categories** with color-coded navigation
- **14 Body Regions** mapped to therapeutic areas
- **Drug Families** - Group related drugs by mechanism/target
- **Drug Lineages** - Track evolutionary relationships

## Quick Start

```bash
# Clone
git clone https://github.com/chenDeepin/DrugTree.git
cd DrugTree

# Start local server
cd src/frontend
python3 -m http.server 8080

# Open in browser
open http://localhost:8080
```

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
│  Matching Drugs (X results)                              │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐              │
│  │Drug1│ │Drug2│ │Drug3│ │Drug4│ │Drug5│ ...          │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘              │
└─────────────────────────────────────────────────────────┘
```

### Project Structure

```
DrugTree/
├── docs/
│   ├── PROJECT_PLAN.md              # Full specification
│   ├── DATA_SCHEMA.md               # Drug data structure
│   └── CENTRAL_BODY_ATLAS_IMPLEMENTATION.md
├── data/
│   ├── drugs/                        # Drug data files
│   └── ontology/
│       └── body_ontology.json        # 14 body regions
├── src/
│   ├── frontend/                     # Main web app
│   │   ├── index.html               # Entry point
│   │   ├── css/style.css            # Dark atlas theme
│   │   ├── js/
│   │   │   ├── app.js               # DrugTreeApp class
│   │   │   ├── structure.js         # RDKit.js viewer
│   │   │   └── body-map.js          # Body map handler
│   │   └── data/drugs-full.json     # 61 drugs with ATC
│   └── backend/                      # FastAPI service
│       ├── main.py                  # Entry point
│       ├── routers/drugs.py         # REST endpoints
│       ├── models/drug.py           # Pydantic schemas
│       └── etl/drug_etl.py          # ETL pipeline
└── tests/
    ├── backend/                      # pytest tests
    └── frontend/                     # Node test harness
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vanilla JS + RDKit.js |
| Backend | FastAPI (Python) |
| Data | ChEMBL + DrugBank + PubChem |
| Hosting | GitHub Pages (MVP) |

## ATC Categories (14 Total)

| Code | Category | Color |
|------|----------|-------|
| A | Alimentary & Metabolism | Green |
| B | Blood & Blood-forming | Red |
| C | Cardiovascular | Pink |
| D | Dermatological | Orange |
| G | Genito-urinary | Purple |
| H | Systemic Hormones | Brown |
| J | Anti-infectives | Blue |
| L | Antineoplastic | Dark Red |
| M | Musculo-skeletal | Grey |
| N | Nervous System | Deep Purple |
| P | Antiparasitic | Teal |
| R | Respiratory | Cyan |
| S | Sensory Organs | Indigo |
| V | Various | Grey |

## Data Schemas

### Drug Schema
```json
{
  "id": "atorvastatin",
  "name": "Atorvastatin",
  "smiles": "CC(C)C1=...",
  "inchikey": "XUKUURHRXDUEBC-UHFFFAOYSA-N",
  "atc_code": "C10AA05",
  "atc_category": "C",
  "molecular_weight": 558.64,
  "phase": "IV",
  "year_approved": 1996,
  "generation": 2,
  "indication": "Hypercholesterolemia",
  "targets": ["HMG-CoA reductase"],
  "company": "Pfizer",
  "synonyms": ["Lipitor", "Sortis"],
  "class": "Statin",
  "parent_drugs": ["lovastatin"],
  "derived_drugs": ["rosuvastatin"]
}
```

### Drug Family Schema
```json
{
  "id": "statin-family",
  "name": "Statin Family",
  "description": "HMG-CoA reductase inhibitors",
  "therapeutic_class": "Lipid-lowering",
  "drugs": ["atorvastatin", "simvastatin", "lovastatin", "pravastatin"],
  "parent_families": [],
  "child_families": []
}
```

### Lineage Schema
```json
{
  "id": "statin-lineage",
  "name": "Statin Lineage",
  "description": "Evolution of statin drugs",
  "root_drugs": ["lovastatin"],
  "generations": [
    {
      "generation": 1,
      "drugs": ["lovastastin", "pravastatin"]
    },
    {
      "generation": 2,
      "drugs": ["simvastatin", "atorvastatin"]
    },
    {
      "generation": 3,
      "drugs": ["rosuvastatin"]
    }
  ]
}
```

## Backend API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/drugs` | GET | List all drugs (with pagination) |
| `/api/drugs/{id}` | GET | Get drug by ID |
| `/api/drugs/search` | GET | Search drugs by query |
| `/api/families` | GET | List all drug families |
| `/api/families/{id}` | GET | Get family by ID |
| `/api/lineages` | GET | List all lineages |
| `/api/lineages/{id}` | GET | Get lineage by ID |
| `/api/diseases` | GET | List disease hierarchy |
| `/api/diseases/{id}/drugs` | GET | Get drugs for disease |

## Status

✅ **Phase 1: MVP Complete** - 61 drugs, ATC classification, body atlas
✅ **Phase 2: Graph Evolution Complete** - Genealogy, families, lineages, disease hierarchy

### Completed Waves
- **WAVE 1**: Foundation (backend models, ETL, graph schema)
- **WAVE 2**: Data Layer (family builder, lineage builder, graph index)
- **WAVE 3**: Curation + API (override loader, DAG validator, REST endpoints)
- **WAVE 4**: Frontend Genealogy (graph store, selection store, genealogy view)
- **WAVE 5**: Frontend Disease (disease view, hierarchy navigation)

### Upcoming
- **Phase 3**: 3D structure viewer, drug comparison, clinical trial data
- **Phase 4**: Scale to 1000+ drugs, performance optimization, CDN deployment

## Documentation

- [Project Plan](docs/PROJECT_PLAN.md) - Full architecture and roadmap
- [Data Schema](docs/DATA_SCHEMA.md) - Drug data structure
- [Central Body Atlas](docs/CENTRAL_BODY_ATLAS_IMPLEMENTATION.md) - UI transformation guide
- [Backend Guide](src/AGENTS.md) - Backend architecture
- [Frontend Guide](src/frontend/AGENTS.md) - Frontend components

## License

MIT

## Author

Built by chenDeepin 🎯
