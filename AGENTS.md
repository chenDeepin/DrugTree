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

## Project Structure

```
DrugTree/
├── docs/                    # Documentation
│   ├── PROJECT_PLAN.md    # Full specification (2278 lines)
│   └── DATA_SCHEMA.md      # Data structure (if exists)
├── data/
│   ├── drugs/               # Drug data files
│   └── ontology/            # Body ontology (14 regions)
├── src/
│   ├── frontend/            # Main web app
│   │   ├── index.html     # Entry point
│   │   ├── css/style.css  # 851 lines
│   │   ├── js/
│   │   │   ├── app.js          # Main application (766 lines)
│   │   │   ├── structure.js   # RDKit.js structure viewer
│   │   │   └── body-map.js    # Legacy body map handler
│   │   └── data/
│   │       ├── drugs-full.json     # 61 drugs with ATC data
│   │       └── sample-drugs.json   # Sample data
│   ├── backend/              # Phase 2: FastAPI backend
│   └── etl/                 # Phase 2: Data pipelines
├── README.md
└── AGENTS.md (this file)
```

---

## Key Files

### Entry Points
| File | Purpose | Notes |
|------|---------|-------|
| `src/frontend/index.html` | Main HTML entry | Open directly or serve via HTTP |
| `src/frontend/js/app.js` | Main application | DrugTreeApp class orchestrates everything |
| `src/frontend/js/structure.js` | Structure viewer | Uses RDKit.js for 2D rendering |

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
| `filterByCategory(cat)` | Filter by ATC | Updates `activeCategory` |
| `filterByBodyRegion(region)` | Filter by body | Updates `activeBodyRegion` |
| `switchMode(mode)` | Switch display mode | Toggles `mode`, re-reenders |
| `initBodyMap()` | Generate body SVG | Creates interactive regions |
| `showDrugModal(drug)` | Display modal | Shows structure + details |
| `applyFilters()` | Combine all filters | Intersects category/body/search |
| `getDrugBodyRegions(drug)` | Map ATC → body | Returns relevant body regions |
| `updateGenealogy(drug)` | Show lineage | Renders parent/derived drugs |

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
  --primary-color: #3498db;
  --secondary-color: #2ecc71;
  --atc-a: #27ae60;  /* Green */
  --atc-c: #e91e63;  /* Pink */
  /* ... 14 total ATC colors */
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

### ⚠️ Avoid
1. **Multi-select ATC filter** - MVP uses single-select only
2. **Different datasets per mode** - Same data, different visibility
3. **Biologics/peptides** - Only small molecules for v1
4. **Authentication** - No login required for MVP

### ⚠️ Common Mistakes
1. **Forgetting to call `initBodyMap()`** - Body map won't render
2. **Hardcoding ATC colors** - Use `ATC_CATEGORIES` object
3. **Skipping mode check** - Test both modes
4. **Missing hover delay** - Use 1200ms delay

### ⚠️ Browser Compatibility
- Requires ES6+ support
- RDKit.js needs internet connection (CDN)
- SVG rendering for body map

---

## Testing

### Manual Testing Checklist
1. ☐ ATC filtering works for all 14 categories
2. ☐ Body region click highlights and filters
3. ☐ Hover preview shows after 1.2s
4. ☐ Search returns correct results
5. ☐ Modal displays structure + genealogy
6. ☐ Mode switch togg scientist-only fields
7. ☐ All 61 drugs load correctly

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

- [x] `src/frontend/js/app.js` - 766 lines
- [x] `src/frontend/index.html` - 169 lines
- [x] `src/frontend/css/style.css` - 851 lines
- [x] `src/frontend/data/drugs-full.json` - 61 drugs
- [x] `data/ontology/body_ontology.json` - 216 lines
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
