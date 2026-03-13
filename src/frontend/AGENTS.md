# DrugTree Frontend - Application Guide

## Overview

This is the main frontend application for DrugTree - a visual drug exploration tool with ATC therapeutic classification.

---

## Quick Start

```bash
# Start local development server
cd src/frontend
python3 -m http.server 8080

# Open in browser
open http://localhost:8080
```

---

## File Structure

```
frontend/
├── index.html          # Main HTML entry (169 lines)
├── css/
│   └── style.css       # Main stylesheet (851 lines)
├── js/
│   ├── app.js          # DrugTreeApp class (766 lines)
│   ├── structure.js    # RDKit.js structure viewer
│   └── body-map.js     # (Legacy) body map handler
├── data/
│   ├── drugs-full.json # 61 drugs with full ATC data
│   └── sample-drugs.json # Sample data (legacy)
└── assets/
    └── human-body.svg  # (Optional) body map SVG
```

---

## Core Architecture

### DrugTreeApp Class

The main application controller located in `js/app.js`.

#### State Properties
```javascript
{
  drugs: [],              // All loaded drugs
  filteredDrugs: [],      // Currently filtered drugs
  selectedDrug: null,     // Currently selected drug
  activeCategory: 'all',  // Current ATC category filter
  activeBodyRegion: null, // Current body region filter
  searchQuery: '',        // Search input value
  mode: 'public',         // 'public' or 'scientist'
  hoverTimeout: null,     // Hover delay timer
  hoverDelay: 1200,       // Hover delay in ms
  structureViewer: null,  // RDKit.js viewer instance
  bodyMap: null           // Body map SVG reference
}
```

#### Initialization Flow
```javascript
async init() {
  1. Initialize structure viewer (RDKit.js)
  2. Load drug data from JSON
  3. Setup event listeners
  4. Initialize body map SVG
  5. Set default mode (public)
  6. Render initial drug list
}
```

---

## ATC Categories

14 WHO ATC Level 1 categories with color coding:

| Code | Name | Color | CSS Variable |
|------|------|-------|--------------|
| A | Alimentary & Metabolism | #27ae60 | --atc-a |
| B | Blood & Blood-forming | #e74c3c | --atc-b |
| C | Cardiovascular | #e91e63 | --atc-c |
| D | Dermatological | #ff9800 | --atc-d |
| G | Genito-urinary | #9c27b0 | --atc-g |
| H | Systemic Hormones | #795548 | --atc-h |
| J | Anti-infectives | #2196f3 | --atc-j |
| L | Antineoplastic | #f44336 | --atc-l |
| M | Musculo-skeletal | #607d8b | --atc-m |
| N | Nervous System | #673ab7 | --atc-n |
| P | Antiparasitic | #009688 | --atc-p |
| R | Respiratory | #00bcd4 | --atc-r |
| S | Sensory Organs | #3f51b5 | --atc-s |
| V | Various | #9e9e9e | --atc-v |

---

## Body Map Regions

Interactive SVG body map with 14 clickable regions:

### Region Definitions (in `initBodyMap()`)
```javascript
const regions = [
  { id: 'head', name: 'Nervous System', category: 'N', path: '...' },
  { id: 'heart', name: 'Cardiovascular', category: 'C', path: '...' },
  { id: 'lungs', name: 'Respiratory', category: 'R', path: '...' },
  // ... 14 total regions
];
```

### ATC to Body Region Mapping
```javascript
const atcToRegions = {
  'A': ['liver', 'intestine'],
  'B': ['blood'],
  'C': ['heart', 'blood'],
  'D': ['skin'],
  'G': ['kidney'],
  'H': ['hormone'],
  'J': ['infection', 'blood'],
  'L': ['immune', 'blood'],
  'M': ['muscle'],
  'N': ['head'],
  'P': ['parasite', 'intestine'],
  'R': ['lungs'],
  'S': ['eyes'],
  'V': ['various']
};
```

---

## Display Modes

### Public Mode
- Simplified view for general audience
- Hides `.scientist-only` elements
- Shows basic drug information

### Scientist Mode
- Detailed scientific view
- Shows all drug properties
- Displays molecular weight, targets, year approved

### Mode Switching
```javascript
switchMode(mode) {
  this.mode = mode;
  document.body.classList.remove('mode-public', 'mode-scientist');
  document.body.classList.add(`mode-${mode}`);
  this.renderDrugList();
  if (this.selectedDrug) {
    this.showDrugModal(this.selectedDrug);
  }
}
```

---

## Filtering System

### Filter Methods
```javascript
// Filter by ATC category
filterByCategory(category) {
  this.activeCategory = category;
  this.activeBodyRegion = null;  // Clear body filter
  this.clearBodyMapHighlight();
  this.applyFilters();
}

// Filter by body region
filterByBodyRegion(region) {
  this.activeBodyRegion = region;
  this.activeCategory = 'all';  // Clear ATC filter
  this.applyFilters();
}

// Apply all filters
applyFilters() {
  this.filteredDrugs = this.drugs.filter(drug => {
    // Category filter
    // Body region filter
    // Search filter
  });
  this.renderDrugList();
}
```

### Filter Logic
1. **ATC Category**: Exact match on `atc_category` field
2. **Body Region**: Match via `getDrugBodyRegions()` mapping
3. **Search**: Partial match on name, targets, class, synonyms

---

## Drug Modal

### Modal Structure (in `showDrugModal()`)
```html
<div class="modal-content">
  <h2 id="modal-title">Drug Name</h2>
  <div class="modal-body">
    <div class="modal-left">
      <!-- Structure viewer -->
    </div>
    <div class="modal-right">
      <!-- Drug properties -->
      <!-- Genealogy section -->
    </div>
  </div>
</div>
```

### Modal Properties
- ATC Code (clickable to filter)
- Drug Class
- Indication
- Molecular Weight
- Generation
- Year Approved
- Targets
- Company
- Synonyms
- SMILES (with copy button)

---

## Drug Genealogy

### Genealogy Display (in `updateGenealogy()`)
Shows parent drugs and derived drugs:
- **Parent Drugs**: Drugs this drug was derived from
- **Successor Drugs**: Drugs derived from this drug

```javascript
updateGenealogy(drug) {
  // Find parent drugs
  const parents = drug.parent_drugs?.map(id => 
    this.drugs.find(d => d.id === id)
  );
  
  // Find successor drugs
  const successors = this.drugs.filter(d => 
    d.parent_drugs?.includes(drug.id)
  );
  
  // Render clickable links
}
```

---

## Structure Viewer

### RDKit.js Integration
Located in `js/structure.js`:
```javascript
class StructureViewer {
  async init() {
    await initRDKit();
  }
  
  renderStructure(smiles, container) {
    const mol = RDKit.getMol(smiles);
    const svg = mol.get_svg();
    container.innerHTML = svg;
  }
}
```

### Requirements
- Internet connection (CDN loaded)
- Modern browser with WebAssembly support
- Valid SMILES string

---

## Event Handlers

### Body Map Events
```javascript
// Click handler
handleBodyRegionClick(region) {
  this.clearBodyMapHighlight();
  // Highlight selected region
  // Update label
  this.filterByBodyRegion(region.id);
}

// Hover handler (with 1.2s delay)
handleBodyRegionHover(region, element) {
  this.hoverTimeout = setTimeout(() => {
    this.showBodyPreview(region, element);
  }, this.hoverDelay);
}

// Leave handler
handleBodyRegionLeave(element) {
  if (this.hoverTimeout) {
    clearTimeout(this.hoverTimeout);
  }
}
```

### Drug Card Events
```javascript
// Click to show modal
card.addEventListener('click', () => {
  this.selectDrug(drug);
  this.showDrugModal(drug);
});
```

---

## CSS Classes

### Mode Classes
```css
.mode-public { /* Public mode styles */ }
.mode-scientist { /* Scientist mode styles */ }
.scientist-only { /* Hidden in public mode */ }
```

### Component Classes
```css
.filter-btn { /* ATC filter buttons */ }
.filter-btn.active { /* Selected filter */ }
.drug-card { /* Drug card container */ }
.drug-card.selected { /* Selected drug */ }
.modal-overlay { /* Modal background */ }
.modal-content { /* Modal container */ }
.body-region { /* Body map region */ }
.body-region.active { /* Selected region */ }
```

---

## Data Loading

### Drug Data Loading
```javascript
async loadDrugData() {
  try {
    // Try full dataset first
    let response = await fetch('data/drugs-full.json');
    if (!response.ok) {
      // Fall back to sample data
      response = await fetch('data/sample-drugs.json');
    }
    const data = await response.json();
    this.drugs = data.drugs || [];
    this.filteredDrugs = [...this.drugs];
  } catch (error) {
    console.error('Failed to load drug data:', error);
    this.showError('Failed to load drug data');
  }
}
```

### Error Handling
```javascript
showError(message) {
  const container = document.getElementById('drug-grid');
  container.innerHTML = `<div class="error">${message}</div>`;
}
```

---

## Helper Methods

### Get Drug Body Regions
```javascript
getDrugBodyRegions(drug) {
  const atcToRegions = { /* ... */ };
  const category = drug.atc_category;
  return atcToRegions[category] || [];
}
```

### Copy SMILES
```javascript
async copySmiles() {
  const smiles = document.getElementById('modal-smiles')?.textContent;
  await navigator.clipboard.writeText(smiles);
  // Show success feedback
}
```

---

## Common Tasks

### Add a New Drug
1. Add drug object to `drugs-full.json`
2. Include all required fields (see Drug Schema)
3. Ensure valid SMILES string
4. Verify ATC code and category match

### Add a New ATC Category
1. Add to `ATC_CATEGORIES` in `app.js`
2. Add CSS variable to `:root` in `style.css`
3. Add filter button in `index.html`
4. Update body region mapping if needed

### Modify Body Map
1. Update `regions` array in `initBodyMap()`
2. Adjust SVG path coordinates
3. Update ATC to region mapping
4. Test click and hover events

---

## Debugging

### Console Logging
```javascript
console.log('DrugTree initialized with', this.drugs.length, 'drugs');
console.log(`Loaded ${this.drugs.length} drugs`);
```

### Common Issues

**"Structure not loading"**
- Check browser console for RDKit.js errors
- Verify internet connection
- Check SMILES validity

**"Body map not responding"**
- Verify `initBodyMap()` called
- Check `#body-map` element exists
- Inspect SVG in DevTools

**"Filters not working"**
- Check `activeCategory` state
- Verify `applyFilters()` called
- Check drug data structure

---

## Performance Notes

- Hover delay prevents excessive preview updates
- Drug cards rendered on-demand (no virtualization yet)
- Structure rendering is async via RDKit.js
- SVG body map is lightweight (no external images)

---

## Browser Support

- Chrome 80+
- Firefox 75+
- Safari 13+
- Edge 80+
- Requires ES6+ support
- Requires WebAssembly for RDKit.js

---

## Dependencies

- **RDKit.js** - Molecular structure rendering (CDN)
- No other external dependencies
- Vanilla JavaScript (no frameworks)

---

## Related Files

- [Root AGENTS.md](../../AGENTS.md) - Project overview
- [PROJECT_PLAN.md](../../docs/PROJECT_PLAN.md) - Full specification
- [body_ontology.json](../../data/ontology/body_ontology.json) - Body region data
