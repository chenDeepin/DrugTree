# DrugTree - Project Knowledge Base

## OVERVIEW

**DrugTree** is a visual drug exploration tool featuring an interactive human body map with ATC therapeutic classification, Developed by C + Hephaestus Prime

### Purpose
- Visualize all approved small-molecule drugs organized by therapeutic area
- Interactive human body map with clickable organs
- Instant 2D/3D molecular structure viewing via RDKit.js
- Drug genealogy/lineage tracking
- Dual display modes: Public (simplified) and Scientist (detailed)

### Tech Stack
- **Frontend**: Vanilla JS, D3.js, 3Dmol.js / RDKit.js
- **Backend**: FastAPI Python (Phase 2)
- **Data**: ChEMBL + DrugBank + PubChem
- **Hosting**: GitHub Pages (MVP)

---

## Project Scale

- **57 files**, 4448 lines of code
- **3 large files** (>500 lines): `drug_etl.py` (819), `app.js` (992), `style.css` (1158)
- **Max depth**: 5 levels
- **61 drugs** in dataset

---

## Project Structure

```
DrugTree/
├── docs/                    # Documentation
│   ├── PROJECT_PLAN.md    # Full specification (2278 lines)
│   └── CENTRAL_BODY_ATLAS_IMPLEMENTATION.md
├── data/
│   ├── drugs/               # Drug data files
│   └── ontology/            # Body ontology (14 regions)
├── src/
│   ├── frontend/            # Main web app
│   │   ├── index.html     # Entry point (227 lines)
│   │   ├── css/style.css  # Dark atlas theme (1158 lines)
│   │   ├── js/app.js      # DrugTreeApp class (992 lines)
│   │   └── data/drugs-full.json  # 61 drugs with ATC
│   ├── backend/              # FastAPI service
│   │   ├── main.py          # Entry point (89 lines)
│   │   ├── routers/drugs.py # REST endpoints (203 lines)
│   │   ├── models/drug.py   # Pydantic schemas (102 lines)
│   │   └── etl/drug_etl.py  # ETL pipeline (819 lines)
│   └── AGENTS.md            # Backend guide
├── tests/
│   ├── backend/             # pytest tests
│   └── frontend/            # Node test harness
├── README.md
└── AGENTS.md (this file)
```

---

## UI Architecture: Central Body Atlas

### Overview
The DrugTree frontend uses a **Central Body Atlas** layout where the human body is the hero visual in the center of the page, surrounded by floating ATC therapeutic category tags. This creates an immersive medical atlas experience rather than a traditional dashboard.

### Layout Structure

```
┌─────────────────────────────────────────────────────────┐
│  Topbar (Glassmorphism)                                 │
│  [Brand] [Search] [Clear] [Mode Switch]                 │
├─────────────────────────────────────────────────────────┤
│  Atlas Hero Section                                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Atlas Stage (Radial Gradient Background)         │  │
│  │                                                    │  │
│  │    [N] ←←←  ┌─────────────┐  →→→ [S]             │  │
│  │    [R] ←←   │   Human     │   →→ [C]             │  │
│  │    [L] ←←   │    Body     │   →→ [B]             │  │
│  │    [M] ←←   │   (Glow)    │   →→ [D]             │  │
│  │    [P] ←←   └─────────────┘   →→ [G]             │  │
│  │    [A] ←←                     →→ [H]             │  │
│  │    [J] ←←                     →→ [V]             │  │
│  │                                                    │  │
│  │  Hint: Hover tag/region to preview · Click to lock│  │
│  └───────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│  Active Filters Bar                                      │
│  Active Filters: [ATC: C ✕] [Search: statin ✕]         │
├─────────────────────────────────────────────────────────┤
│  Results Section                                         │
│  Matching Drugs (X results)                              │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐              │
│  │Drug1│ │Drug2│ │Drug3│ │Drug4│ │Drug5│ ...          │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘              │
└─────────────────────────────────────────────────────────┘
```

### Key CSS Classes

#### App Shell
- `.app-shell` - Main container with dark theme
- `.topbar` - Glassmorphism header with search and controls
- `.page-main` - Main content area

#### Atlas Hero
- `.atlas-hero` - Hero section container
- `.atlas-stage` - Centered stage with radial gradient background
- `.atlas-body-wrap` - Body map wrapper with glow effect
- `.atlas-glow` - Soft blue-white luminous glow
- `.human-body-map` - SVG body map container
- `.body-hotspots` - Interactive body regions (future)

#### ATC Orbit Layer
- `.atc-orbit-layer` - Container for floating ATC tags
- `.atc-tag` - Individual ATC category button
- `.atc-tag.is-active` - Selected category (highlighted)
- `.atc-tag.is-muted` - Non-selected categories (dimmed)
- `.atc-tag.is-hovered` - Hover preview state
- `.atc-code` - ATC letter code (e.g., "N", "C")
- `.atc-name` - Category name (e.g., "Nervous", "Cardio")

#### Active Filters
- `.active-filters-bar` - Filter bar container
- `.filter-chips` - Container for active filter chips
- `.filter-chip` - Individual filter chip with remove button

#### Results
- `.results-section` - Drug results container
- `.results-header` - Header with count
- `.drug-grid` - Grid of drug cards

### Dark Theme CSS Variables

```css
:root {
  --bg-base: #0f172a;          /* Deep navy */
  --bg-elevated: #1e293b;      /* Elevated surfaces */
  --bg-surface: #334155;       /* Card backgrounds */
  --text-primary: #f1f5f9;     /* Light text */
  --text-secondary: #94a3b8;   /* Muted text */
  --border-subtle: rgba(255, 255, 255, 0.1);
  --glow-primary: rgba(59, 130, 246, 0.4);
  
  /* ATC Category Colors */
  --atc-a: #27ae60;  /* Alimentary - Green */
  --atc-b: #e74c3c;  /* Blood - Red */
  --atc-c: #e91e63;  /* Cardiovascular - Pink */
  --atc-d: #ff9800;  /* Dermatological - Orange */
  --atc-g: #9c27b0;  /* Genito-urinary - Purple */
  --atc-h: #795548;  /* Hormones - Brown */
  --atc-j: #2196f3;  /* Anti-infectives - Blue */
  --atc-l: #f44336;  /* Antineoplastic - Dark Red */
  --atc-m: #607d8b;  /* Musculo-skeletal - Grey */
  --atc-n: #673ab7;  /* Nervous - Deep Purple */
  --atc-p: #009688;  /* Antiparasitic - Teal */
  --atc-r: #00bcd4;  /* Respiratory - Cyan */
  --atc-s: #3f51b5;  /* Sensory - Indigo */
  --atc-v: #9e9e9e;  /* Various - Grey */
}
```

### ATC Tag Positioning

ATC tags are positioned absolutely around the body using CSS:

```css
.atc-tag[data-category="N"] { top: 10%; left: 20%; }   /* Nervous */
.atc-tag[data-category="S"] { top: 12%; right: 18%; }  /* Sensory */
.atc-tag[data-category="R"] { top: 28%; right: 24%; }  /* Respiratory */
.atc-tag[data-category="C"] { top: 30%; left: 26%; }   /* Cardiovascular */
.atc-tag[data-category="B"] { top: 40%; right: 14%; }  /* Blood */
.atc-tag[data-category="L"] { top: 40%; left: 14%; }   /* Oncology */
.atc-tag[data-category="D"] { top: 52%; right: 16%; }  /* Skin */
.atc-tag[data-category="G"] { top: 54%; left: 16%; }   /* GU/Breast */
.atc-tag[data-category="H"] { top: 66%; right: 18%; }  /* Hormones */
.atc-tag[data-category="M"] { top: 68%; left: 18%; }   /* Musculoskeletal */
.atc-tag[data-category="P"] { top: 80%; right: 20%; }  /* Parasites */
.atc-tag[data-category="A"] { top: 82%; left: 22%; }   /* Alimentary */
.atc-tag[data-category="J"] { bottom: 8%; right: 30%; }/* Anti-infectives */
.atc-tag[data-category="V"] { bottom: 8%; left: 30%; } /* Various */
```

---

## Key Files

### Entry Points
| File | Purpose | Notes |
|------|---------|-------|
| `src/frontend/index.html` | Main HTML entry (227 lines) | Central Body Atlas layout |
| `src/frontend/js/app.js` | Main application (1027 lines) | DrugTreeApp class with new methods |
| `src/frontend/js/structure.js` | Structure viewer | Uses RDKit.js for 2D rendering |
| `src/frontend/css/style.css` | Dark atlas theme (1158 lines) | Complete UI styling |

### Data Files
| File | Records | Description |
|------|---------|-------------|
| `src/frontend/data/drugs-full.json` | 61 | Approved small-molecule drugs with full ATC data |
| `data/ontology/body_ontology.json` | 14 regions | Body region mapping with ATC categories |

---

## Core Components

### 1. DrugTreeApp Class (`app.js`)
Main application controller managing:
- **State**: `drugs`, `filteredDrugs`, `selectedDrug`, `activeCategory`, `activeBodyRegion`, `mode`
- **Features**:
  - ATC category filtering (14 categories)
  - Body region filtering (14 regions)
  - Search by name/target/class
  - Hover preview (1.2s delay)
  - Drug modal with genealogy
  - Mode switching (Public/Scientist)

### 2. ATC Categories (14 Total)
```javascript
const ATC_CATEGORIES = {
  'A': { name: 'Alimentary & Metabolism', color: '#27ae60' },
  'B': { name: 'Blood & Blood-forming', color: '#e74c3c' },
  'C': { name: 'Cardiovascular', color: '#e91e63' },
  'D': { name: 'Dermatological', color: '#ff9800' },
  'G': { name: 'Genito-urinary', color: '#9c27b0' },
  'H': { name: 'Systemic Hormones', color: '#795548' },
  'J': { name: 'Anti-infectives', color: '#2196f3' },
  'L': { name: 'Antineoplastic', color: '#f44336' },
  'M': { name: 'Musculo-skeletal', color: '#607d8b' },
  'N': { name: 'Nervous System', color: '#673ab7' },
  'P': { name: 'Antiparasitic', color: '#009688' },
  'R': { name: 'Respiratory', color: '#00bcd4' },
  'S': { name: 'Sensory Organs', color: '#3f51b5' },
  'V': { name: 'Various', color: '#9e9e9e' }
};
```

### 3. Body Region Mapping
Body regions map to ATC categories:
```javascript
const atcToRegions = {
  'A': ['liver', 'intestine'],  // Alimentary
  'B': ['blood'],                    // Blood
  'C': ['heart', 'blood'],           // Cardiovascular
  'D': ['skin'],                     // Dermatological
  'G': ['kidney'],                   // Genito-urinary
  'H': ['hormone'],                  // Hormones
  'J': ['infection', 'blood'],       // Anti-infectives
  'L': ['immune', 'blood'],          // Antineoplastic
  'M': ['muscle'],                   // Musculo-skeletal
  'N': ['head'],                     // Nervous System
  'P': ['parasite', 'intestine'],   // Antiparasitic
  'R': ['lungs'],                    // Respiratory
  'S': ['eyes'],                     // Sensory Organs
  'V': ['various']                   // Various
};
```

---

## Data Schemas

### Drug Schema (`drugs-full.json`)
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
  "class": "Statin"
}
```

### Body Ontology Schema
```json
{
  "version": "1.0",
  "visible_regions": [...],     // 14 body regions
  "internal_ontology": {...},    // Detailed anatomy mapping
  "disease_to_anatomy": {...}  // Disease → region mapping
}
```

---

## Development Workflow

### Running Locically
```bash
# Option 1: Direct file open
open src/frontend/index.html

# Option 2: Local HTTP server (recommended)
cd src/frontend
python3 -m http.server 8080
# Open http://localhost:8080
```

### Development Port
- Default: `http://localhost:8080`
- Current running: `http://localhost:8765`

---

## Key Methods

### DrugTreeApp Methods
| Method | Purpose | Key Side Effects |
|--------|---------|-------------------|
| `init()` | Initialize app | Loads drugs, sets up events |
| `filterByCategory(cat)` | Filter by ATC | Updates `activeCategory`, `updateATCTagsState()`, `updateActiveFiltersBar()` |
| `filterByBodyRegion(region)` | Filter by body | Updates `activeBodyRegion`, calls new filter bar update |
| `switchMode(mode)` | Switch display mode | Toggles `mode`, re-renders |
| `initBodyMap()` | Generate body SVG | Creates interactive regions |
| `showDrugModal(drug)` | Display modal | Shows structure + details |
| `applyFilters()` | Combine all filters | Intersects category/body/search |
| `getDrugBodyRegions(drug)` | Map ATC → body | Returns relevant body regions |
| `updateGenealogy(drug)` | Show lineage | Renders parent/derived drugs |
| `setupATCTags()` | Wire ATC tag buttons | Click/hover handlers for `.atc-tag` elements |
| `handleATCTagHover(category, element)` | Hover preview | Adds `is-hovered`, triggers tooltip |
| `handleATCTagLeave(element)` | Clear hover | Removes hover state, clears timeout |
| `showATCTagPreview(category, element)` | Preview tooltip | Shows category name and drug count |
| `updateATCTagsState()` | Update tag classes | Applies `is-active`/`is-muted` classes |
| `updateActiveFiltersBar()` | Render filter chips | Shows chips for category/search/region |
| `clearFilters()` | Reset all filters | Resets to default state |
| `setupClearButton()` | Wire Clear button | Connects `#clear-filters` to `clearFilters()` |

---

## CSS Conventions

### Section Headers
All CSS sections use comment headers:
```css
/* Header */
/* Mode Switch */
/* Main Layout */
/* Filters Section */
/* Body Map */
/* Drug Grid */
/* Modal */
```

### CSS Variables
```css
:root {
  /* Dark Theme Base */
  --bg-base: #0f172a;          /* Deep navy */
  --bg-elevated: #1e293b;      /* Elevated surfaces */
  --bg-surface: #334155;       /* Card backgrounds */
  --text-primary: #f1f5f9;     /* Light text */
  --text-secondary: #94a3b8;   /* Muted text */
  --border-subtle: rgba(255, 255, 255, 0.1);
  --glow-primary: rgba(59, 130, 246, 0.4);
  
  /* ATC Category Colors */
  --atc-a: #27ae60;  /* Green - Alimentary */
  --atc-b: #e74c3c;  /* Red - Blood */
  --atc-c: #e91e63;  /* Pink - Cardiovascular */
  --atc-d: #ff9800;  /* Orange - Dermatological */
  --atc-g: #9c27b0;  /* Purple - Genito-urinary */
  --atc-h: #795548;  /* Brown - Hormones */
  --atc-j: #2196f3;  /* Blue - Anti-infectives */
  --atc-l: #f44336;  /* Dark Red - Antineoplastic */
  --atc-m: #607d8b;  /* Grey - Musculo-skeletal */
  --atc-n: #673ab7;  /* Deep Purple - Nervous */
  --atc-p: #009688;  /* Teal - Antiparasitic */
  --atc-r: #00bcd4;  /* Cyan - Respiratory */
  --atc-s: #3f51b5;  /* Indigo - Sensory */
  --atc-v: #9e9e9e;  /* Grey - Various */
}
```

### Scientist-Only Elements
```css
.scientist-only {
  display: none;  /* Hidden in Public mode */
}
.mode-scientist .scientist-only {
  display: block;  /* Shown in Scientist mode */
}
```

---

## Anti-Patterns & Gotchas

### ⚠️ Avoid (Frontend)
1. **Multi-select ATC filter** - MVP uses single-select only
2. **Different datasets per mode** - Same data, different visibility
3. **Biologics/peptides** - Only small molecules for v1
4. **Authentication** - No login required for MVP

### ⚠️ Avoid (Backend)
1. **Sync requests in endpoints** - Use `async def` with `httpx`
2. **Hardcoded API keys** - Use environment variables
3. **Skipping Pydantic validation** - Always validate input/output
4. **Unbounded queries** - Add pagination to list endpoints

### ⚠️ Common Mistakes (Frontend)
1. **Forgetting to call `initBodyMap()`** - Body map won't render
2. **Hardcoding ATC colors** - Use `ATC_CATEGORIES` object
3. **Skipping mode check** - Test both modes
4. **Missing hover delay** - Use 1200ms delay

### ⚠️ Common Mistakes (Backend)
1. **Missing CORS** - Frontend on different port needs CORS middleware
2. **No error handling** - Wrap external API calls (ChEMBL/PubChem) in try/except
3. **Blocking I/O** - Use async for all external calls

### ⚠️ Browser Compatibility
- Requires ES6+ support
- RDKit.js needs internet connection (CDN)
- SVG rendering for body map

---

## Testing

### Test Structure
```
tests/
├── backend/
│   └── test_drug_etl.py   # pytest tests for ETL
└── frontend/
    ├── test_app_state.mjs # State management tests
    └── test_file_safe_bootstrap.mjs  # Bootstrap tests
```

### Manual Testing Checklist
1. ✅ ATC filtering works for all 14 categories
2. ✅ Body region click highlights and filters
3. ✅ Hover preview shows after 1.2s
4. ✅ Search returns correct results
5. ✅ Modal displays structure + genealogy
6. ✅ Mode switch toggles scientist-only fields
7. ✅ All 61 drugs load correctly
8. ✅ ATC tags float around body with correct colors
9. ✅ Active filters bar shows filter chips
10. ✅ Clear button resets all filters
11. ✅ Dark theme renders correctly
12. ✅ Body map appears centered with glow effect

### Key Test Commands
```bash
# Start local server
cd src/frontend && python3 -m http.server 8080

# Check console for errors
# Open http://localhost:8080
# Test features manually
```

---

## Next Steps (Roadmap)

### Phase 1: MVP ✅ (Current)
- [x] 61 approved small-molecule drugs
- [x] ATC category filtering
- [x] Body region filtering
- [x] Mode switching (Public/Scientist)
- [x] Drug genealogy modal
- [x] RDKit.js structure viewer

### Phase 2: Backend Integration (Planned)
- [ ] FastAPI backend
- [ ] ChEMBL API integration
- [ ] DrugBank data import
- [ ] REST API endpoints
- [ ] Search optimization

### Phase 3: Advanced Features (Planned)
- [ ] 3D structure viewer (3Dmol.js)
- [ ] Drug comparison tool
- [ ] Clinical trial data
- [ ] Target interaction network
- [ ] Export functionality

### Phase 4: Scale (Planned)
- [ ] 1000+ drugs
- [ ] Performance optimization
- [ ] CDN deployment
- [ ] Analytics

---

## Files to Check Before Pushing

- [x] `src/frontend/js/app.js` - 1027 lines
- [x] `src/frontend/index.html` - 227 lines
- [x] `src/frontend/css/style.css` - 1158 lines
- [x] `src/frontend/data/drugs-full.json` - 61 drugs
- [x] `data/ontology/body_ontology.json` - 216 lines
- [x] `src/frontend/assets/human-body.svg` - Body map SVG
- [x] `docs/CENTRAL_BODY_ATLAS_IMPLEMENTATION.md` - UI transformation guide
- [x] `README.md` - Updated
- [x] `AGENTS.md` - This file

---

## Troubleshooting

### "Structure not loading"
- Check browser console for RDKit.js errors
- Verify internet connection (CDN required)
- Check SMILES validity in data

### "Body map not responding"
- Verify `initBodyMap()` called in `init()`
- Check `#body-map` element exists in HTML
- Inspect SVG generation in DevTools

### "Filtering not working"
- Check `activeCategory` and `activeBodyRegion` state
- Verify `applyFilters()` called after filter changes
- Check drug data has correct `atc_category` field

### "Mode switch not updating UI"
- Verify `switchMode()` updates `body.classList`
- Check `.scientist-only` CSS class exists
- Ensure modal re-reenders on mode change

---

## Commit Guidelines

### Commit Message Format
```
feat: Add feature description
fix: Bug fix description
docs: Documentation update
refactor: Code refactoring
test: Test additions
```

### Before Committing
1. ✅ All files load without errors
2. ✅ No console errors in browser
3. ✅ Manual testing checklist passed
4. ✅ Both modes work correctly
5. ✅ All 14 ATC categories filter properly

---

## References

- [PROJECT_PLAN.md](docs/PROJECT_PLAN.md) - Full specification
- [README.md](README.md) - Project overview
- [RDKit.js](https://www.rdkitjs.com/) - Structure rendering
- [WHO ATC Classification](https://www.whocc.no/atc_ddd_index_and_excisions/) - ATC system
