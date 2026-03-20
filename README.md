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
- **7,359 Small-Molecule Drugs** from ChEMBL, KEGG, DrugBank, and FDA sources
- **55.4% ATC Coverage** (4,079 drugs with valid ATC codes, 3,280 awaiting enrichment)
- **14 ATC Level 1 Categories** with color-coded navigation
- **14 Body Regions** mapped to therapeutic areas
- **Drug Families** - Group related drugs by mechanism/target
- **Drug Lineages** - Track evolutionary relationships
- **Source Provenance** - Track where each drug's data originated
- **Canonical Root Data Files** - frontend embeds are generated from repo-root datasets

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

# Optional backend
uvicorn src.backend.main:app --reload --port 8000
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
│   ├── drugs.json
│   ├── diseases.json
│   ├── disease_drug_edges.json
│   └── ontology/
│       └── body-ontology.json
├── scripts/
│   └── build_frontend_embeds.py
├── src/
│   ├── frontend/                     # Main web app
│   │   ├── index.html               # Entry point
│   │   ├── css/style.css            # Dark atlas theme
│   │   ├── js/
│   │   │   ├── app.js               # DrugTreeApp class
│   │   │   ├── structure.js         # RDKit.js viewer
│   │   │   └── body-map.js          # Body map handler
│   │   └── data/                    # generated mirrors/embeds
│   └── backend/                      # FastAPI service
│       ├── main.py                  # Entry point
│       ├── routers/drugs.py         # REST endpoints
│       ├── models/drug.py           # Pydantic schemas
│       └── etl/                     # drug / disease / ATC pipelines
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



## Documentation

- [Project Plan](docs/PROJECT_PLAN.md) - Full architecture and roadmap
- [Data Schema](docs/DATA_SCHEMA.md) - Drug data structure


## License

MIT

## Author

Built by chenDeepin 🎯
