# DrugTree Frontend State Model

Complete inventory of frontend state architecture as of current codebase.

## 1. State Buckets

### 1.1 Persistent State

State that survives across user interactions and is initialized during app startup.

#### DrugTreeApp Data Collections
- `this.drugs` — Array of all drug objects loaded from API/embedded data
- `this.diseases` — Array of all disease objects
- `this.diseaseDrugEdges` — Array of disease-drug relationship edges
- `this.diseaseDrugIdsByDiseaseId` — Map(disease_id → Set(drug_ids)) for O(1) edge lookup
- `this.bodyOntology` — Body ontology object containing visible_regions and disease_to_anatomy mappings

#### DrugTreeApp Data Indexes
- `this.regionMetaById` — Object mapping region IDs to metadata (display_name, description, icon)
- `this.regionElementsById` — Map(region_id → Array(SVG elements)) for efficient DOM updates

#### DrugTreeApp Configuration Constants
- `this.hoverDelay` — Number (1200ms) delay before showing hover previews
- `this.API_BASE_URL` — String ("http://127.0.0.1:8000/api/v1") for backend calls
- `ATC_CATEGORIES` — Object mapping ATC codes (A-V) to metadata (name, color)

#### DrugTreeApp Subsystem References
- `this.structureViewer` — StructureViewer instance (RDKit.js wrapper)
- `this.graphStore` — GraphStore instance (drug genealogy and disease hierarchy)
- `this.selectionStore` — SelectionStore instance (selection IDs and view modes)
- `this.diseasePanel` — DiseasePanel instance (disease search and filtering)
- `this.diseaseView` — DiseaseView instance (body→disease→drug tree visualization)
- `this.genealogyView` — GenealogyView instance (drug lineage tree visualization)

#### GraphStore Topology Data
- `this.families` — Map(family_id → family data) for drug families (unused in current code)
- `this.edges` — Map(edge_id → edge data) for drug lineage relationships
- `this.nodes` — Map(drug_id → node data) for all indexed drugs
- `this.diseaseHierarchy` — Map(disease_id → disease node data) including drugs array
- `this.diseaseNodes` — Map(disease_id → hierarchy node) for disease tree structure
- `this.bodyRegions` — Map(region_id → region data) indexed from ontology

#### DrugTreeState Global Constants (read-only)
- `ATC_TO_BODY_REGIONS` — Object mapping ATC categories to arrays of compatible body region IDs
- `DEFAULT_ACTIVE_CATEGORY` — String constant ("all")
- Module contains no mutable state — pure utility functions only

---

### 1.2 Transient State

State that changes with user interaction and is NOT persisted.

#### DrugTreeApp Selection State
- `this.selectedDrug` — Object or null (full drug object, mirrored from SelectionStore.selectedDrugId)
- `this.activeCategory` — String ("all" or ATC code A-V), toggles ATC filter
- `this.activeBodyRegion` — String or null, currently selected body region ID
- `this.activeDisease` — Object or null (full disease object, mirrored from SelectionStore.selectedDiseaseId)
- `this.hoveredRegion` — String or null, body region currently being hovered

#### DrugTreeApp Search and Filter State
- `this.searchQuery` — String, current text search input value (lowercased)
- `this.filteredDrugs` — Array, result of applyFilters() combining category, region, disease, and search filters
- `this.mode` — String ("public" or "scientist"), controls display mode of drug cards

#### DrugTreeApp View Mode State
- `this.viewMode` — String ("genealogy" or "disease"), controls which view section is visible

#### DrugTreeApp UI Transient
- `this.hoverTimeout` — Timeout ID or null, debounces hover preview display
- `this.diseaseHighlightedRegions` — Set(region_id), body regions highlighted by selected disease

#### DiseasePanel State
- `this.diseases` — Array, all loaded disease objects (copy of DrugTreeApp.diseases)
- `this.filteredDiseases` — Array, diseases passing search and orphan filter
- `this.activeDisease` — Object or null, currently selected disease (mirrors DrugTreeApp.activeDisease)
- `this.showOrphanOnly` — Boolean, whether to show only orphan-flagged diseases
- `this.searchQuery` — String, disease search input value (independent of DrugTreeApp.searchQuery)
- `this.isOpen` — Boolean, whether dropdown is currently visible
- `this.highlightedDiseaseIndex` — Number, index of disease currently highlighted for keyboard navigation
- `this.blurTimeoutId` — Timeout ID, delays dropdown close to handle click handlers

#### DiseaseView State
- `this.expandedNodes` — Set(disease_id), which disease nodes are expanded to show child drugs
- `this.currentRegionId` — String or null, body region being visualized
- `this.currentDiseaseId` — String or null, specific disease being highlighted

#### GenealogyView State
- `this.currentData` — Object, tree data from API (drug_id, drug_name, tree, statistics)
- `this.isScientistMode` — Boolean, whether to show confidence tooltips and edge colors
- `this._nodePositions` — Map(drug_id → {x, y}), cached node coordinates for cross-link rendering

#### StructureViewer State
- `this.rdkitLoader` — Object or null, loaded RDKit.js module reference
- `this.isReady` — Boolean, whether RDKit.js loaded successfully

---

### 1.3 Derived State

State computed on demand from other state, not stored directly.

#### DrugTreeApp Derived
- `this.filteredDrugs` — Computed by applyFilters() from drugs + activeCategory + activeBodyRegion + activeDisease + searchQuery

#### GraphStore Derived
- `this.loading` — Boolean, true during loadGraph() async operation
- `this.loaded` — Boolean, true after loadGraph() completes successfully
- `this.error` — String or null, error message from loadGraph() if it fails

#### DrugTreeState Pure Functions (derived on demand)
- `applyDrugFilters(drugs, state)` — Filters drugs by category, body region, and search query
- `resolveDrugBodyRegions(drug)` — Returns array of body region IDs for a drug (explicit or ATC-mapped)
- `buildBodyRegionLabel(drug, regionsById)` — Returns human-readable region label for drug card
- `buildPublicSummary(drug, regionsById)` — Returns user-friendly summary string for public mode
- `getModePresentation(mode)` — Returns object controlling which metadata to show based on mode
- `humanizeRegionId(regionId)` — Converts snake_case region IDs to human-readable labels
- `toggleCategory(activeCategory, clickedCategory)` — Returns new category (toggles between "all" and clicked)
- `toggleBodyRegion(activeBodyRegion, clickedRegion)` — Returns new region (toggles selection)

---

## 2. Store Ownership Map

| State Field | Owner | Purpose |
|------------|--------|---------|
| `drugs` | DrugTreeApp | Canonical drug data array |
| `diseases` | DrugTreeApp, DiseasePanel | Disease data array (DrugTreeApp is source of truth) |
| `diseaseDrugEdges` | DrugTreeApp | Disease-drug relationship edges |
| `diseaseDrugIdsByDiseaseId` | DrugTreeApp | O(1) lookup index for disease edges |
| `bodyOntology` | DrugTreeApp | Body region and disease hierarchy definitions |
| `regionMetaById` | DrugTreeApp | Region metadata for display |
| `regionElementsById` | DrugTreeApp | DOM element cache for body regions |
| `filteredDrugs` | DrugTreeApp | Computed result of applyFilters() |
| `selectedDrug` | DrugTreeApp | Full drug object for modal rendering |
| `activeCategory` | DrugTreeApp | Current ATC filter selection |
| `activeBodyRegion` | DrugTreeApp | Currently clicked body region |
| `activeDisease` | DrugTreeApp, DiseasePanel | Full disease object for filtering |
| `hoveredRegion` | DrugTreeApp | Region under mouse cursor |
| `searchQuery` | DrugTreeApp, DiseasePanel | Text search input (independent) |
| `mode` | DrugTreeApp | Display mode (public/scientist) |
| `viewMode` | DrugTreeApp, SelectionStore | Current view (genealogy/disease) |
| `hoverTimeout` | DrugTreeApp | Debounced hover preview trigger |
| `hoverDelay` | DrugTreeApp | Configured hover delay duration |
| `diseaseHighlightedRegions` | DrugTreeApp | Set of regions highlighted by disease |
| `selectedDrugId` | SelectionStore | Drug ID for selection events |
| `selectedDiseaseId` | SelectionStore | Disease ID for selection events |
| `selectedRegionId` | SelectionStore | Body region ID for selection events |
| `diseases` | DiseasePanel | Copy of disease data for search |
| `filteredDiseases` | DiseasePanel | Diseases passing search/orphan filters |
| `showOrphanOnly` | DiseasePanel | Orphan filter toggle state |
| `isOpen` | DiseasePanel | Dropdown visibility state |
| `highlightedDiseaseIndex` | DiseasePanel | Keyboard navigation highlight index |
| `blurTimeoutId` | DiseasePanel | Blur handler delay for dropdown close |
| `expandedNodes` | DiseaseView | Set of disease IDs with expanded children |
| `currentRegionId` | DiseaseView | Body region being visualized in tree |
| `currentDiseaseId` | DiseaseView | Specific disease highlighted in tree |
| `expandedNodes` | DiseaseView, GenealogyView (different semantics) | Disease: expand/collapse; Genealogy: internal D3 state |
| `currentData` | GenealogyView | Tree data structure from API |
| `isScientistMode` | GenealogyView | Toggles tooltips and edge colors |
| `_nodePositions` | GenealogyView | Cached node coordinates for cross-links |
| `families` | GraphStore | Drug family data (unused) |
| `edges` | GraphStore | Drug lineage edge data |
| `nodes` | GraphStore | Drug node data with full objects |
| `diseaseHierarchy` | GraphStore | Disease nodes with linked drugs |
| `diseaseNodes` | GraphStore | Hierarchy nodes for D3 tree |
| `bodyRegions` | GraphStore | Indexed body region metadata |
| `loading` | GraphStore | Async operation state |
| `loaded` | GraphStore | Data availability state |
| `error` | GraphStore | Error message state |
| `rdkitLoader` | StructureViewer | RDKit.js module reference |
| `isReady` | StructureViewer | RDKit.js load success flag |

---

## 3. Event Flow

### Drug Selection Pipeline
```
drug card click
  ↓
SelectionStore.setSelectedDrug(drugId, drugData)
  ↓
'drug:selected' event dispatched
  ↓
DrugTreeApp.handleDrugSelected({drugId, previousDrugId, drugData})
  ↓
this.selectDrug(drug, cardElement)  // card highlighting
this.showDrugModal(drug)
```

### Disease Selection Pipeline
```
disease panel select
  ↓
DiseasePanel.selectDisease(diseaseId)
  ↓
this.activeDisease = disease
this.highlightDiseaseRegions(disease)
  ↓
SelectionStore.setSelectedDisease(disease.id, disease)
  ↓
'disease:selected' event dispatched
  ↓
DrugTreeApp.handleDiseaseSelected({diseaseId, previousDiseaseId, diseaseData})
  ↓
this.activeDisease = disease
DiseasePanel.activeDisease = disease
this.activeCategory = "all"
this.highlightDiseaseRegions(disease) (via app.diseaseHighlightedRegions)
this.updateATCTagsState()
this.updateActiveFiltersBar()
this.applyFilters()
```

### Region Selection Pipeline
```
body region click
  ↓
DrugTreeApp.handleBodyRegionClick(regionId)
  ↓
nextRegionId = toggleBodyRegion(this.activeBodyRegion, regionId)
  ↓
SelectionStore.setSelectedRegion(nextRegionId, regionData)
  ↓
'region:selected' event dispatched
  ↓
DrugTreeApp.handleRegionSelected({regionId, previousRegionId, regionData})
  ↓
this.activeBodyRegion = nextRegionId
if (nextRegionId !== previousRegionId && this.activeDisease):
  SelectionStore.setSelectedDisease(null, null) or clear via app
this.hoveredRegion = null
this.removePreview(".body-preview")
this.updateBodyMapState()
this.updateBodyRegionLabel()
this.updateActiveFiltersBar()
this.applyFilters()
```

### View Mode Toggle Pipeline
```
view button click
  ↓
DrugTreeApp.setViewMode(mode)
  ↓
this.viewMode = mode
SelectionStore.setViewMode(mode)
  ↓
DrugTreeApp._applyViewModeUI(mode)
```

### Mode Switch Pipeline
```
mode button click
  ↓
DrugTreeApp.switchMode(mode)
  ↓
this.mode = mode
document.body.classList.remove("mode-public", "mode-scientist")
document.body.classList.add(`mode-${mode}`)
this.renderDrugList()
if (this.selectedDrug):
  this.showDrugModal(this.selectedDrug)
```

### Clear Filters Pipeline
```
clear button click
  ↓
DrugTreeApp.clearFilters()
  ↓
this.activeCategory = "all"
this.hoveredRegion = null
this.searchQuery = ""
SelectionStore.clear()
  ↓
'selection:cleared' event dispatched
  ↓
DrugTreeApp.handleSelectionCleared()
  ↓
this.activeDisease = null
this.activeBodyRegion = null
this.clearBodyMapHighlight()
DiseasePanel.activeDisease = null
this.updateBodyRegionLabel()
this.updateActiveFiltersBar()
this.applyFilters()
```

### ATC Category Filter Pipeline
```
ATC tag click
  ↓
DrugTreeApp.filterByCategory(category)
  ↓
this.activeCategory = toggleCategory(this.activeCategory, category)
  ↓
this.updateATCTagsState()
this.updateActiveFiltersBar()
this.applyFilters()
```

### Search Pipeline
```
search input event
  ↓
DrugTreeApp:
  this.searchQuery = event.target.value.toLowerCase()
  this.updateActiveFiltersBar()
  this.applyFilters()
DiseasePanel:
  this.searchQuery = event.target.value.toLowerCase()
  this.filterDiseases()
  this.render()
```

### GraphStore Load Pipeline
```
DrugTreeApp.init()
  ↓
loadDrugData()
loadDiseaseData()
loadDiseaseDrugEdges()
loadBodyOntology()
  ↓
DrugTreeApp.loadGraphData({drugs, diseases, bodyOntology, diseaseDrugEdges})
  ↓
GraphStore.loadGraph(graphData)
  ↓
this.loading = true
this.error = null
  ↓
this.families = new Map()
this.edges = new Map()
this.nodes = new Map()
this.diseaseHierarchy = new Map()
this.diseaseNodes = new Map()
this.bodyRegions = new Map()
  ↓
this.loaded = true
this.loading = false
```

---

## 4. State Duplication Notes

Several pieces of state are mirrored across different owners. These duplications exist because different components need access to different data shapes (IDs vs full objects).

### Drug Object Duplication
- `SelectionStore.selectedDrugId` (string ID)
- `DrugTreeApp.selectedDrug` (full object with id, name, smiles, etc.)
- **Rationale**: SelectionStore is the source of truth for selection IDs. DrugTreeApp caches the full object for modal rendering and card highlighting to avoid repeated lookups.

### View Mode Duplication
- `SelectionStore.viewMode`
- `DrugTreeApp.viewMode`
- **Rationale**: SelectionStore is the source of truth. DrugTreeApp keeps a local copy for its internal logic. When SelectionStore emits 'view:changed', DrugTreeApp syncs both via handleViewChanged().

### Disease Duplication
- `SelectionStore.selectedDiseaseId` (string ID)
- `DrugTreeApp.activeDisease` (full object with id, canonical_name, body_region, etc.)
- `DiseasePanel.activeDisease` (full object copy)
- **Rationale**: SelectionStore is the source of truth for the ID. Both DrugTreeApp and DiseasePanel need the full object for rendering and filtering. DiseasePanel receives its copy via DrugTreeApp.handleDiseaseSelected().

### Body Region Duplication
- `SelectionStore.selectedRegionId` (string ID)
- `DrugTreeApp.activeBodyRegion` (string ID)
- **Rationale**: SelectionStore is the source of truth. DrugTreeApp keeps a local copy for internal filtering logic.

### Disease Data Duplication
- `DrugTreeApp.diseases` (canonical array)
- `DiseasePanel.diseases` (copy of the array)
- **Rationale**: DrugTreeApp is the canonical data source. DiseasePanel gets a copy via DrugTreeApp.init() or loadDiseaseData() to support its search functionality.

---

## 5. Key Constraints

### Single Sources of Truth
- **SelectionStore** is the single source of truth for all selection IDs (drug, disease, region) and view mode
- **DrugTreeApp** is the source of truth for all full data objects (drugs, diseases, body ontology) and derived filtered results
- **GraphStore** is the source of truth for all graph topology (families, edges, nodes, disease hierarchy, body regions)

### Statelessness of Utility Layer
- **DrugTreeState** is a stateless utility namespace. It contains only:
  - Read-only constants (ATC_TO_BODY_REGIONS, DEFAULT_ACTIVE_CATEGORY)
  - Pure functions (no mutable internal state)
- No component should store mutable state in DrugTreeState

### Independent Search States
- **DiseasePanel.searchQuery** is completely independent of DrugTreeApp.searchQuery
- Rationale: Disease panel has its own search input field. The two searches filter different entities (diseases vs drugs) and should not interfere.

### Event-Driven State Updates
- SelectionStore uses CustomEvent pattern to emit: 'drug:selected', 'disease:selected', 'region:selected', 'selection:cleared', 'view:changed'
- DrugTreeApp registers listeners for these events in initStores() and updates its own state accordingly
- This creates a unidirectional data flow: SelectionStore → DrugTreeApp → UI updates

### Filter Composition
- applyFilters() combines four filter dimensions:
  1. ATC category (activeCategory)
  2. Body region (activeBodyRegion)
  3. Disease selection (activeDisease with explicit edge lookup)
  4. Text search (searchQuery)
- The filter chain is applied in order: all drugs → category filter → region filter → disease filter → search filter
- Each step reduces the result set

### Hover Preview Debouncing
- Both DrugTreeApp and DiseasePanel use timeout-based debouncing:
  - DrugTreeApp.hoverDelay (1200ms) before showing ATC tag or body region previews
  - DiseasePanel.blurTimeoutId (120ms) before closing dropdown on blur
- This prevents preview flickering and allows user time to move mouse to preview before it appears

### Cache and Index Patterns
- DiseaseDrugIdsByDiseaseId is a Map of Sets for O(1) edge lookup during disease filtering
- regionElementsById caches DOM elements for efficient class updates without querying the DOM
- GraphStore uses Maps for all topological data (families, edges, nodes, diseases, regions)

### Derived State Computation
- filteredDrugs is recomputed on every filter change via applyFilters()
- This means filter changes are expensive operations (O(n) over all drugs)
- getRenderableDrugs() adds an additional slice operation for result limiting
- Result limits: DEFAULT_RESULT_LIMIT (120) when filters active, STARTER_SET_LIMIT (72) when no filters

### D3 Visualization State
- DiseaseView and GenealogyView maintain internal D3.js state:
  - this.svg, this.g, this.tree, this.root (D3 selections and hierarchy)
  - Node positions cached for cross-links (GenealogyView._nodePositions)
  - Expanded nodes tracked via Sets for expand/collapse behavior
- These components handle their own rendering cycle independently of DrugTreeApp state

### Graph Loading Lifecycle
- GraphStore.loadGraph() has three mutually exclusive states:
  - loading: true → async load in progress
  - loaded: true → data successfully loaded
  - error: string/null → failure occurred
- DrugTreeApp calls loadGraphData() in init() after loading drugs, diseases, edges, and ontology

---

## Appendix: Event Reference

### Custom Events Emitted

#### From SelectionStore
- `'drug:selected'` — detail: {drugId, previousDrugId, drugData}
- `'disease:selected'` — detail: {diseaseId, previousDiseaseId, diseaseData}
- `'region:selected'` — detail: {regionId, previousRegionId, regionData}
- `'selection:cleared'` — detail: {}
- `'view:changed'` — detail: {mode, previousMode}

#### From DiseaseView
- `'node:clicked'` — detail: {id, type: 'region'|'disease'|'drug', data}

#### From GenealogyView
- `'genealogy:node:clicked'` — detail: {drugId, drugName}

---

## 7. Render Boundary Map

Defines discrete render surfaces, their current coupling problems, and the targeted scope for each boundary. The goal is to map every place the DOM is touched so that future refactors can narrow render scope without breaking visual consistency.

### 7.1 Render Boundary Definitions

#### B1 — Drug Grid

| Property | Value |
|----------|-------|
| **Boundary Name** | Drug Grid |
| **Current Trigger** | `applyFilters()` → `renderDrugList()`, `switchMode()`, `init()` |
| **Data Consumed** | `this.filteredDrugs`, `this.mode`, `this.selectedDrug`, `this.regionMetaById`, `this.structureViewer` |
| **DOM Owned** | `#drug-grid` (innerHTML), `#drug-count` (textContent), `#results-note` (textContent) |
| **Current Scope Problem** | Full innerHTML replacement on every filter keystroke. All drug cards (up to 120) are destroyed and recreated, including RDKit.js structure rendering for each card. Search typing at ~300ms intervals triggers complete grid rebuild. `switchMode()` also rebuilds entire grid just to toggle card metadata visibility. |
| **Targeted Scope** | Incremental DOM update: append/remove cards when filter result set changes, update text counts without touching cards. Mode switch should toggle CSS classes on existing cards, not rebuild them. |
| **Priority** | **HIGH** — Largest visual surface, most frequent user-triggered rerender, heaviest per-card cost (RDKit.js) |

#### B2 — Body Map Visual State

| Property | Values |
|----------|--------|
| **Boundary Name** | Body Map Visual State |
| **Current Trigger** | `applyFilters()` → `updateBodyMapState()`, `handleRegionSelected()`, `handleBodyRegionHover()`, `handleBodyRegionLeave()`, `clearBodyMapHighlight()`, `initBodyMap()` |
| **Data Consumed** | `this.drugs`, `this.activeCategory`, `this.activeBodyRegion`, `this.hoveredRegion`, `this.diseaseHighlightedRegions`, `this.regionElementsById` |
| **DOM Owned** | All `[data-region]` SVG elements — classList toggles: `is-active`, `is-hovered`, `is-muted`, `highlighted` |
| **Current Scope Problem** | **Coupled into `applyFilters()`** (L1046). Every search keystroke or ATC toggle recomputes drug counts for ALL 14 body regions via `applyDrugFilters()` per region (14 × O(n) filter passes) just to update `is-muted` classes, even when only the drug grid changed. Region drug counts are recalculated even though the active region did not change. |
| **Targeted Scope** | Only update body map classes when `activeCategory` or `activeBodyRegion` changes — not on search or disease changes. Cache region drug counts and invalidate only on category/region change. Hover/leave already narrowly scoped (only touches one region). |
| **Priority** | **HIGH** — Unnecessary O(14×n) computation on every search keystroke; body map is visually unchanged during text search |

#### B3 — ATC Tag States

| Property | Values |
|----------|--------|
| **Boundary Name** | ATC Tag States |
| **Current Trigger** | `filterByCategory()`, `handleDiseaseSelected()`, `clearFilters()` |
| **Data Consumed** | `this.activeCategory` |
| **DOM Owned** | All `.atc-tag` elements — classList: `is-active`, `is-muted` |
| **Current Scope Problem** | Already well-scoped. Only toggles classes on 14 tag elements. However, `handleDiseaseSelected()` forces `activeCategory = "all"` and re-runs `updateATCTagsState()` even if category was already "all". |
| **Targeted Scope** | Add a dirty check: skip update if `activeCategory` hasn't changed. Otherwise, current scope is acceptable. |
| **Priority** | **LOW** — Minimal DOM work (14 classList toggles), rarely a bottleneck |

#### B4 — Filter Chips Bar

| Property | Values |
|----------|--------|
| **Boundary Name** | Filter Chips Bar |
| **Current Trigger** | `filterByCategory()`, `handleDiseaseSelected()`, `handleRegionSelected()`, `handleSelectionCleared()`, `clearFilters()`, search input handler, individual chip `onRemove` callbacks |
| **Data Consumed** | `this.activeDisease`, `this.activeCategory`, `this.searchQuery`, `this.activeBodyRegion` |
| **DOM Owned** | `#filter-chips` (innerHTML rebuilt), `#active-filters` (classList toggle `has-filters`) |
| **Current Scope Problem** | Full innerHTML rebuild on every trigger. Each chip `onRemove` callback also calls `updateActiveFiltersBar()` + `applyFilters()`, causing double chip rebuild within the same user action. Called from every filter-change path, including search input (per keystroke). |
| **Targeted Scope** | Diff-based chip updates: add/remove individual chip elements instead of rebuilding. Skip update if the set of active filters hasn't changed (e.g., search keystroke that doesn't add/remove a filter category). |
| **Priority** | **MEDIUM** — Frequent rebuilds but small DOM surface; double-rebuild on chip remove is wasteful |

#### B5 — Body Region Label

| Property | Values |
|----------|--------|
| **Boundary Name** | Body Region Label |
| **Current Trigger** | `handleRegionSelected()`, `handleSelectionCleared()`, `clearFilters()`, `handleBodyRegionHover()`, `handleBodyRegionLeave()`, `initBodyMap()` |
| **Data Consumed** | `this.activeBodyRegion`, `this.hoveredRegion`, `this.activeCategory`, `this.searchQuery`, `this.regionMetaById` |
| **DOM Owned** | `#body-region-label` (textContent + classList `active`) |
| **Current Scope Problem** | Already narrow scope — single element text update. Recomputes drug count via `applyDrugFilters()` for the label on hover/leave, but this is a single-region filter (not 14×). No coupling into `applyFilters()`. |
| **Targeted Scope** | Current scope is acceptable. Could cache the count if region+category haven't changed since last computation. |
| **Priority** | **LOW** — Single DOM element, narrow scope already |

#### B6 — Drug Modal

| Property | Values |
|----------|--------|
| **Boundary Name** | Drug Modal |
| **Current Trigger** | `handleDrugSelected()` → `showDrugModal()`, `switchMode()` (re-shows modal if drug selected) |
| **Data Consumed** | `this.selectedDrug` (full object), `this.mode`, `this.drugs` (for genealogy lookups), `this.regionMetaById`, `this.structureViewer` |
| **DOM Owned** | `#modal-overlay` (classList `active`), `#modal-title`, `#modal-summary`, `#modal-region`, `#modal-atc-code`, `#modal-class`, `#modal-mw`, `#modal-phase`, `#modal-year`, `#modal-company`, `#modal-indication`, `#modal-targets`, `#modal-synonyms`, `#modal-inchikey`, `#modal-smiles`, `#modal-parents`, `#modal-successors`, `#modal-generation`, `#modal-structure`, `#genealogy-tree-container`, all `.scientist-only` elements |
| **Current Scope Problem** | Modal opening is inherently a one-shot render — all fields update at once. `switchMode()` re-renders entire modal just to toggle `.scientist-only` visibility, which could be a CSS-only change. Genealogy tree render (`renderGenealogyTree()`) does full SVG rebuild inside modal. |
| **Targeted Scope** | Mode switch should toggle `body` class only; `.scientist-only` visibility is already CSS-driven. Genealogy tree in modal could use D3 update pattern instead of full SVG rebuild. Modal open is correctly scoped as one-shot. |
| **Priority** | **MEDIUM** — Mode switch modal re-render is wasteful; modal open is acceptable |

#### B7 — Disease Panel

| Property | Values |
|----------|--------|
| **Boundary Name** | Disease Panel |
| **Current Trigger** | `DiseasePanel.init()`, `handleSearchInput()`, `handleSearchKeydown()`, `selectDisease()`, `clearDiseaseFilter()`, orphan toggle click, `handleDiseaseSelected()` (via app), `handleRegionSelected()` (clears disease), `handleSelectionCleared()` (clears disease) |
| **Data Consumed** | `this.activeDisease`, `this.filteredDiseases`, `this.showOrphanOnly`, `this.highlightedDiseaseIndex` |
| **DOM Owned** | `#selected-disease` (innerHTML), `#disease-list` (innerHTML), `#disease-stats` (innerHTML), `#disease-dropdown` (classList `open`), `#disease-search-input` (value, aria-expanded) |
| **Current Scope Problem** | `render()` rebuilds all three sub-sections (selected badge, list, stats) every time. Keyboard arrow navigation (`renderDiseaseList()`) rebuilds entire disease list HTML just to change highlight class. Stats (`renderStats()`) rarely change but re-render on every call. |
| **Targeted Scope** | Keyboard navigation should update only `is-highlighted` class on affected items. Stats should only render once or on disease data changes. Selected badge and list are correctly scoped for their triggers. |
| **Priority** | **MEDIUM** — Keyboard navigation causes visible list flicker; stats waste is minor |

#### B8 — Disease View (D3 Tree)

| Property | Values |
|----------|--------|
| **Boundary Name** | Disease View (D3 Tree) |
| **Current Trigger** | `_applyViewModeUI()` (when switching to disease view), `handleDiseaseSelected()`, `handleRegionSelected()`, `handleSelectionCleared()`, `clearFilters()` (all conditional on `viewMode === 'disease'`) |
| **Data Consumed** | `this.graphStore` (bodyRegions, diseaseNodes, node lookups), `this.currentRegionId`, `this.currentDiseaseId`, `this.expandedNodes` |
| **DOM Owned** | `#disease-view-container` → SVG → `g` groups for nodes and paths (D3 managed) |
| **Current Scope Problem** | `render(regionId, diseaseId)` does a full D3 tree rebuild: `container.innerHTML = ''`, new SVG, new hierarchy. Called on every region click and disease selection even when the region hasn't changed. Node expand/collapse (`expandNode`/`collapseNode`) correctly uses D3 update pattern but the top-level `render()` does not. |
| **Targeted Scope** | `render()` should diff against `currentRegionId`/`currentDiseaseId` and skip if unchanged. Region click that doesn't change the active disease within the same region should only update node highlighting, not rebuild the entire tree. |
| **Priority** | **HIGH** — Full D3 SVG rebuild is expensive; region clicks in disease view trigger unnecessary complete redraws |

#### B9 — Genealogy View (D3 Tree in Modal)

| Property | Values |
|----------|--------|
| **Boundary Name** | Genealogy View (D3 Tree in Modal) |
| **Current Trigger** | `showDrugModal()` → `renderGenealogyTree()` |
| **Data Consumed** | `drug` (id, name, generation, parent_drugs), `this.drugs` (for successor lookup), `this.isScientistMode` |
| **DOM Owned** | `#genealogy-tree-container` → SVG → `g` groups for nodes, links, cross-links, zoom controls |
| **Current Scope Problem** | Full SVG rebuild on every modal open. Acceptable because modal is one-shot (user opens one drug at a time). Cross-links rendered but limited to 3 per target. Node positions cached in `_nodePositions`. |
| **Targeted Scope** | Current scope is acceptable for modal use case. If genealogy were ever shown inline (not in modal), would need incremental D3 update pattern. |
| **Priority** | **LOW** — Modal-scoped, user-triggered, acceptable cost |

#### B10 — View Mode Section Toggle

| Property | Values |
|----------|--------|
| **Boundary Name** | View Mode Section Toggle |
| **Current Trigger** | `setViewMode()`, `handleViewChanged()` |
| **Data Consumed** | `this.viewMode` |
| **DOM Owned** | `#disease-view-section` (display style), `.results-section` (display style), `.view-btn` elements (classList `active`) |
| **Current Scope Problem** | Already narrow. Toggles display style on two sections and active class on two buttons. When switching to disease view, also calls `diseaseView.render()` which may be a full rebuild (see B8). |
| **Targeted Scope** | Current toggle scope is fine. The disease view render on switch is a B8 concern, not a B10 concern. |
| **Priority** | **LOW** — Already narrow scope |

### 7.2 Broad Rerender Call Chains

These are the four primary cascading call chains identified in the current codebase. Each chain touches multiple render boundaries in sequence, often unnecessarily.

#### Chain 1: `applyFilters()` Cascade

```
applyFilters()
├── compute this.filteredDrugs from drugs + category + region + disease + search
├── updateBodyMapState()                    ← B2: iterates ALL 14 regions, 14× applyDrugFilters()
└── renderDrugList()                        ← B1: full innerHTML rebuild of drug grid
```

**Problem**: Every search keystroke triggers both B2 and B1. Search queries do not affect body map visual state (only category/region changes should), yet B2 runs anyway with 14 filter passes.

**Targeted decomposition**:
```
applyFilters()
├── compute this.filteredDrugs
└── renderDrugList()                        ← B1 only

updateBodyMapState()                        ← B2: only called when activeCategory or activeBodyRegion changes
```

#### Chain 2: `handleDiseaseSelected()` Cascade

```
handleDiseaseSelected(detail)
├── this.activeDisease = disease
├── DiseasePanel.activeDisease = disease
├── DiseasePanel.render()                   ← B7
├── DiseasePanel.highlightDiseaseRegions()  ← B2 partial (highlighted class only)
├── this.activeCategory = "all"
├── updateATCTagsState()                    ← B3
├── updateActiveFiltersBar()                ← B4
├── applyFilters()                          ← Chain 1 (B2 + B1)
└── diseaseView.render(regionId, diseaseId) ← B8: full D3 rebuild
```

**Problem**: Disease selection touches 5 boundaries (B7, B2, B3, B4, B1, B8). The `applyFilters()` call triggers B2 body map update even though disease selection doesn't change the category filter visual (it was just set to "all"). ATC tag state is reset even if it was already "all".

**Targeted decomposition**: Same as Chain 1 fix — separate body map update from `applyFilters()`. Add dirty checks for ATC state.

#### Chain 3: `handleRegionSelected()` Cascade

```
handleRegionSelected(detail)
├── this.activeBodyRegion = nextRegionId
├── clear disease if region changed          ← B7 partial
├── this.hoveredRegion = null
├── removePreview(".body-preview")
├── updateBodyMapState()                    ← B2
├── updateBodyRegionLabel()                 ← B5
├── updateActiveFiltersBar()                ← B4
├── applyFilters()                          ← Chain 1 (B2 + B1) ← B2 runs TWICE
└── diseaseView.render(regionId, null)      ← B8
```

**Problem**: B2 runs **twice** — once explicitly via `updateBodyMapState()` and once inside `applyFilters()`. The second run is redundant because the region hasn't changed between the two calls.

**Targeted decomposition**: Remove `updateBodyMapState()` from `applyFilters()`. Keep the explicit call in `handleRegionSelected()`.

#### Chain 4: `clearFilters()` → `handleSelectionCleared()` Cascade

```
clearFilters()
├── this.activeCategory = "all"
├── this.hoveredRegion = null
├── this.searchQuery = ""
├── clear search input value
├── SelectionStore.clear()
│   └── 'selection:cleared' event
│       └── handleSelectionCleared()
│           ├── this.activeDisease = null
│           ├── this.activeBodyRegion = null
│           ├── clearBodyMapHighlight()      ← B2 partial
│           ├── DiseasePanel.render()        ← B7
│           ├── updateBodyRegionLabel()      ← B5
│           ├── updateActiveFiltersBar()     ← B4
│           ├── applyFilters()               ← Chain 1 (B2 + B1)
│           └── diseaseView.render(null)     ← B8
├── updateATCTagsState()                    ← B3 (also called)
├── updateActiveFiltersBar()                ← B4 (called TWICE total)
├── applyFilters()                          ← Chain 1 (B2 + B1) (also called, runs TWICE total)
├── updateBodyRegionLabel()                 ← B5 (called TWICE total)
└── diseaseView.render(null)                ← B8 (called TWICE total)
```

**Problem**: `clearFilters()` directly calls `updateATCTagsState()`, `updateActiveFiltersBar()`, `applyFilters()`, and `updateBodyRegionLabel()`. Then the SelectionStore `clear()` dispatches `selection:cleared`, which triggers `handleSelectionCleared()` that calls the **same four methods again**. This means B1, B2, B4, B5, and B8 all execute **twice** on every clear action.

**Targeted decomposition**: `clearFilters()` should only call `SelectionStore.clear()`. All downstream updates should happen in `handleSelectionCleared()` only. Remove the duplicated direct calls from `clearFilters()`.

### 7.3 Render Boundary Cross-Reference

| Boundary | Method | Triggered By | Touches Other Boundaries? |
|----------|--------|-------------|--------------------------|
| B1 Drug Grid | `renderDrugList()` | `applyFilters()`, `switchMode()` | No (leaf boundary) |
| B2 Body Map | `updateBodyMapState()` | `applyFilters()` ⚠️, `handleRegionSelected()`, hover/leave | No (leaf boundary) |
| B3 ATC Tags | `updateATCTagsState()` | `filterByCategory()`, `handleDiseaseSelected()`, `clearFilters()` | No (leaf boundary) |
| B4 Filter Chips | `updateActiveFiltersBar()` | Every filter change path | No (leaf boundary) |
| B5 Region Label | `updateBodyRegionLabel()` | Region selection, clear, hover/leave | No (leaf boundary) |
| B6 Modal | `showDrugModal()` | Drug selection, mode switch | Calls B9 (genealogy tree) |
| B7 Disease Panel | `DiseasePanel.render()` | Disease selection, clear, orphan toggle | No (leaf boundary) |
| B8 Disease View | `diseaseView.render()` | View switch, region/disease selection, clear | No (leaf boundary) |
| B9 Genealogy Tree | `renderGenealogyTree()` | Modal open (via `showDrugModal()`) | No (leaf boundary) |
| B10 View Toggle | `_applyViewModeUI()` | View mode switch | Calls B8 (disease view render) |

### 7.4 Optimization Priority Summary

| Priority | Boundary | Rationale | Estimated Impact |
|----------|----------|-----------|-----------------|
| **HIGH** | B2 Body Map | Decouple from `applyFilters()` — eliminate 14× O(n) filter passes on every search keystroke | Eliminates ~90% of unnecessary body map recomputes |
| **HIGH** | B1 Drug Grid | Incremental card updates instead of full innerHTML rebuild; defer structure rendering | Reduces per-keystroke DOM work from 120 card creates to 0–10 diffs |
| **HIGH** | B8 Disease View | Diff `currentRegionId`/`currentDiseaseId` before full D3 rebuild | Eliminates full SVG rebuilds when region/disease hasn't changed |
| **MEDIUM** | B4 Filter Chips | Diff-based chip add/remove; eliminate double-rebuild on chip remove | Reduces small but unnecessary innerHTML rebuilds |
| **MEDIUM** | B6 Modal | Mode switch should not re-render modal content | Eliminates modal rebuild on mode toggle |
| **MEDIUM** | B7 Disease Panel | Keyboard navigation should update class only, not rebuild list | Eliminates list flicker during arrow-key navigation |
| **MEDIUM** | Chain 4 | Deduplicate `clearFilters()` and `handleSelectionCleared()` calls | Eliminates 100% redundant double-render of 5 boundaries |
| **LOW** | B3 ATC Tags | Add dirty check for unchanged `activeCategory` | Minor: skips 14 classList toggles |
| **LOW** | B5 Region Label | Cache region drug count | Minor: skips one `applyDrugFilters()` call |
| **LOW** | B9 Genealogy Tree | Acceptable as-is for modal use case | None needed |
| **LOW** | B10 View Toggle | Already narrow scope | None needed |

---

## 8. Proposed Module Extraction Seams

Analysis of the 1,533-line `DrugTreeApp` class identifying safe seams for extracting focused controllers/renderers. This section maps existing methods to six candidate modules, each with a single primary responsibility.

### 8.1 Extraction Priority Order

Recommended extraction sequence from lowest risk to highest risk:

1. **DataLoader** (pure IO, zero DOM) → 2. **DrugGridRenderer** (rendering only) → 3. **PreviewController** (self-contained tooltip layer) → 4. **FilterController** (reads+writes app state) → 5. **AtlasController** (SVG+DOM heavy) → 6. **ModalController** (deepest coupling to stores + drug data)

### 8.2 Module Responsibility Matrix

| Module | Primary Responsibility | Methods to Extract (app.js lines) | State Dependencies (reads/writes on `this.`) | Store Dependencies | DOM Dependencies | Risk | Seam Safety |
|--------|----------------------|-----------------------------------|-----------------------------------------------|-------------------|-----------------|------|-------------|
| **DataLoader** | Load drug, disease, edge, and ontology data from API/embedded/fallback sources | `loadDrugData()` L321-393, `loadDiseaseData()` L395-438, `loadDiseaseDrugEdges()` L440-486, `loadBodyOntology()` L500-524, `rebuildDiseaseEdgeIndex()` L488-498, `fetchJsonWithTimeout()` L45-54 (top-level) | **Writes**: `drugs`, `filteredDrugs`, `diseases`, `diseaseDrugEdges`, `diseaseDrugIdsByDiseaseId`, `bodyOntology`, `regionMetaById`. **Reads**: none beyond embedded globals | None | `#drug-grid` (loading spinner in `loadDrugData` only) | **Low** | Purest seam. All methods are async data-fetch + fallback chains that write to app state. Only `loadDrugData` touches DOM for a loading spinner (trivial to move). No store interaction. Can be extracted as a standalone service that returns data objects, letting `init()` assign them. |
| **DrugGridRenderer** | Render drug cards into the grid and manage empty-state display | `renderDrugList()` L1057-1095, `createDrugCard()` L1142-1213, `buildEmptyState()` L1097-1140, `getRenderableDrugs()` L1050-1055 | **Reads**: `filteredDrugs`, `drugs`, `activeCategory`, `activeBodyRegion`, `activeDisease`, `searchQuery`, `selectedDrug`, `mode`, `regionMetaById`, `structureViewer`, `selectionStore`. **Writes**: none (rendering only) | `SelectionStore` (calls `setSelectedDrug` on card click) | `#drug-grid`, `#drug-count`, `#results-note` | **Low** | Rendering-only methods that read state but don't mutate it (except delegating selection to store). Card click handler delegates to `selectionStore.setSelectedDrug()`, not to app state directly. Pass required state as arguments to decouple. |
| **PreviewController** | Manage hover-triggered tooltip popups (ATC tag previews and body region previews) with viewport clamping | `showATCTagPreview()` L689-715, `showBodyPreview()` L778-802, `handleATCTagHover()` L676-681, `handleATCTagLeave()` L683-687, `removePreview()` L1503-1508, `clampToViewport()` L1489-1495, `clearHoverTimeout()` L1482-1487, `clearTransientPreviews()` L1497-1501 | **Reads**: `drugs`, `activeCategory`, `activeBodyRegion`, `searchQuery`, `regionMetaById`, `hoverDelay`. **Writes**: `hoverTimeout` | None | Creates/removes `.atc-preview` and `.body-preview` divs appended to `document.body` | **Low** | Self-contained tooltip layer. All preview divs are transient DOM elements with a fixed lifecycle (create → show → remove). The only shared mutable state is `hoverTimeout` which could be internalized. Reads `applyDrugFilters` for counts but that's a pure function from `DrugTreeState`. |
| **FilterController** | Manage ATC category filtering, search input, clear button, filter bar rendering, and filter application | `filterByCategory()` L804-809, `applyFilters()` L1029-1048, `updateActiveFiltersBar()` L866-940, `getRenderableDrugs()` L1050-1055, `clearFilters()` L811-832, `setupSearch()` L613-624, `setupClearButton()` L669-674, `setupATCTags()` L595-611, `updateATCTagsState()` L849-864 | **Reads**: `drugs`, `activeCategory`, `activeBodyRegion`, `activeDisease`, `searchQuery`, `diseaseDrugIdsByDiseaseId`. **Writes**: `activeCategory`, `filteredDrugs`, `searchQuery`, `hoveredRegion` | `SelectionStore` (calls `clear()` from `clearFilters`) | `#search-input`, `#clear-filters`, `.atc-tag`, `#filter-chips`, `#active-filters` | **Medium** | Reads and writes core filter state. `applyFilters()` triggers both `updateBodyMapState()` (cross-cut) and `renderDrugList()` (rendering). Extraction requires either a callback/event pattern for these downstream calls, or keeping `applyFilters` as an orchestrator in DrugTreeApp. The filter bar rendering (`updateActiveFiltersBar`) is self-contained DOM work. |
| **AtlasController** | Manage SVG body map initialization, region click/hover/leave interaction, visual state classes, and region labels | `initBodyMap()` L526-571, `handleBodyRegionClick()` L717-743, `handleBodyRegionHover()` L745-763, `handleBodyRegionLeave()` L765-776, `updateBodyMapState()` L942-971, `clearBodyMapHighlight()` L973-986, `updateBodyRegionLabel()` L988-1013, `getRegionMeta()` L1015-1023, `clearTransientPreviews()` L1497-1501, `updateAtlasSummary()` L572-584 | **Reads**: `drugs`, `activeCategory`, `activeBodyRegion`, `activeDisease`, `hoveredRegion`, `searchQuery`, `bodyOntology`, `regionMetaById`, `regionElementsById`, `diseaseHighlightedRegions`. **Writes**: `activeBodyRegion`, `hoveredRegion`, `regionElementsById` | `SelectionStore` (calls `setSelectedRegion` from `handleBodyRegionClick`) | `#body-map`, `#body-region-label`, `#atlas-summary`, SVG `[data-region]` elements | **Medium** | Heavy DOM coupling via SVG element caching in `regionElementsById`. `handleBodyRegionClick` cascades to filters + body label + disease view, making it an orchestrator method. `updateBodyMapState()` reads `applyDrugFilters` for per-region drug counts — requires passing drug data or a count function. `initBodyMap` attaches event listeners on SVG elements that call back into `this`. Seam is safe if the controller receives a reference to the app or uses a lightweight event bus for cascade calls. |
| **ModalController** | Show/close drug detail modal, render genealogy tree, handle SMILES copy | `showDrugModal()` L1225-1289, `closeModal()` L1452-1458, `copySmiles()` L1460-1480, `setupModal()` L626-640, `updateGenealogy()` L1291-1354, `renderGenealogyTree()` L1356-1378, `_buildGenealogyTreeData()` L1380-1450 | **Reads**: `drugs`, `selectedDrug`, `mode`, `regionMetaById`, `structureViewer`. **Writes**: none directly (modal state is DOM-only) | None directly (reads `selectedDrug` which is kept in sync by SelectionStore events) | `#modal-overlay`, `#modal-title`, `#modal-summary`, `#modal-region`, `#modal-atc-code`, `#modal-class`, `#modal-mw`, `#modal-phase`, `#modal-year`, `#modal-company`, `#modal-indication`, `#modal-targets`, `#modal-synonyms`, `#modal-inchikey`, `#modal-smiles`, `#modal-structure`, `#copy-smiles`, `.modal-close`, `.scientist-only`, `#genealogy-tree-container`, `#modal-parents`, `#modal-successors`, `#modal-generation` | **Medium-High** | Deepest DOM surface area (20+ element IDs). `showDrugModal` calls `updateGenealogy` → `renderGenealogyTree` → `_buildGenealogyTreeData` which traverses `this.drugs` for parent/successor lookups. Also calls `structureViewer.renderModalStructure()`. The genealogy chain is self-contained but reads the full `drugs` array. Modal also calls `filterByCategory` via ATC code click-back (cross-cutting). Extraction is safe if the controller receives `drugs` array and `regionMetaById` as constructor args, plus a callback for category filter navigation. |

### 8.3 Cross-Cutting Call Graph

The following shows which extraction modules call into other modules (through DrugTreeApp `this.` references), which must be replaced with event emission or callback injection during extraction:

```
DataLoader ──(writes state)──→ DrugTreeApp
    └── no downstream calls

FilterController ──(calls)──→ AtlasController.updateBodyMapState()
                   ├──→ DrugGridRenderer.renderDrugList()
                   └──→ AtlasController.updateBodyRegionLabel()

AtlasController ──(calls)──→ FilterController.applyFilters()
                   ├──→ FilterController.updateActiveFiltersBar()
                   └──→ SelectionStore.setSelectedRegion()

PreviewController ──(calls)──→ DrugTreeState.applyDrugFilters()  [pure fn, no module]
                     └──→ AtlasController.getRegionMeta()

ModalController ──(calls)──→ DrugTreeState.*  [pure fns, no module]
                  ├──→ StructureViewer.renderModalStructure()
                  ├──→ FilterController.filterByCategory()  [via ATC code click]
                  └──→ reads DrugTreeApp.drugs  [for genealogy traversal]

DrugGridRenderer ──(calls)──→ SelectionStore.setSelectedDrug()
                     ├──→ StructureViewer.renderStructure()
                     └──→ DrugTreeState.*  [pure fns]
```

### 8.4 Shared State Conflict Map

State fields that are read or written by multiple proposed modules simultaneously. These require careful ownership transfer or read-only delegation:

| State Field | Writer Module | Reader Modules | Resolution Strategy |
|-------------|--------------|----------------|-------------------|
| `this.filteredDrugs` | FilterController (writes) | DrugGridRenderer (reads) | FilterController owns; renderer receives as arg |
| `this.activeCategory` | FilterController (writes) | AtlasController, PreviewController (reads) | FilterController owns; others read via getter |
| `this.activeBodyRegion` | AtlasController (writes), FilterController (clears) | PreviewController, FilterController (reads) | AtlasController owns; FilterController clears via event |
| `this.hoverTimeout` | PreviewController (writes) | AtlasController (clears via `clearTransientPreviews`) | Internalize into PreviewController |
| `this.hoveredRegion` | AtlasController (writes), FilterController (clears) | AtlasController (reads) | AtlasController owns; FilterController clears via event |
| `this.regionElementsById` | AtlasController (writes+reads) | PreviewController (reads for anchor element) | AtlasController owns; expose getter |
| `this.regionMetaById` | DataLoader (writes) | AtlasController, ModalController, DrugGridRenderer (reads) | DataLoader writes once at init; others read via getter |

### 8.5 Recommended Extraction Contract

Each extracted module should follow this interface pattern:

```javascript
class ExtractedModule {
  constructor(app) {
    this.app = app;  // temporary — replace with specific interfaces
  }
}
```

During extraction, replace `this.app` references with narrower interfaces:

1. **Phase 1 — Extract with `app` reference**: Module holds `this.app` and calls methods directly. Validates the seam works.
2. **Phase 2 — Replace with callbacks/events**: Replace `this.app.method()` calls with callback injection or CustomEvent emission.
3. **Phase 3 — Remove `app` reference**: Module is fully decoupled, receives only what it needs via constructor or method arguments.

### 8.6 Already-Extracted Modules (Do Not Re-extract)

The following modules have already been extracted from DrugTreeApp and are NOT candidates for the seams above:

| Module | File | Initialized In |
|--------|------|---------------|
| DiseasePanel | `js/components/disease-panel.js` | `DrugTreeApp.init()` L115-118 |
| DiseaseView | `js/views/diseaseView.js` | `DrugTreeApp.initDiseaseView()` L169-176 |
| GenealogyView | `js/views/genealogyView.js` | `DrugTreeApp.initGenealogyView()` L178-183 |
| GraphStore | `js/stores/graphStore.js` | `DrugTreeApp.initStores()` L132-135 |
| SelectionStore | `js/stores/selectionStore.js` | `DrugTreeApp.initStores()` L137-155 |
| StructureViewer | `js/structure.js` | `DrugTreeApp.init()` L91-96 |

### 8.7 Line Coverage Summary

| Module | Total Lines | Approx % of app.js |
|--------|-----------|-------------------|
| DataLoader | ~195 lines (L45-54, L158-167, L321-524) | 12.7% |
| DrugGridRenderer | ~165 lines (L1050-1213) | 10.8% |
| PreviewController | ~140 lines (L676-715, L778-802, L1482-1508) | 9.1% |
| FilterController | ~235 lines (L595-624, L669-674, L804-864, L866-940, L1029-1055) | 15.3% |
| AtlasController | ~260 lines (L526-584, L717-776, L942-1023, L1497-1501) | 17.0% |
| ModalController | ~330 lines (L626-640, L1215-1289, L1291-1480) | 21.5% |
| **Total extractable** | **~1,325 lines** | **86.5%** |
| Remaining in DrugTreeApp (orchestration, lifecycle, handlers) | ~208 lines | 13.5% |

Successful extraction of all six modules would reduce DrugTreeApp from 1,533 lines to approximately 208 lines of orchestration code: `constructor()`, `init()`, `initStores()`, store event handlers (`handleDrugSelected`, `handleDiseaseSelected`, `handleRegionSelected`, `handleSelectionCleared`, `handleViewChanged`), `setupEventListeners()`, `setupViewToggle()`, `setViewMode()`, `_applyViewUI()`, `switchMode()`, `showError()`, and `reset()`.

---

## 9. Event-Driven Rendering Alignment

Authoritative event pipeline definition synthesizing the render boundary map (Section 7) and module extraction seams (Section 8) into a concrete architecture target. This section maps every state-changing UI action to a single canonical event path and identifies the direct state mutation exceptions that must be eliminated or explicitly accepted.

### 9.1 Authoritative Event Path Map

#### A1: Click drug card

| Property | Value |
|----------|-------|
| **Action** | User clicks a drug card in the grid |
| **Canonical Path** | `selectionStore.setSelectedDrug(id, drug)` → `'drug:selected'` event → `handleDrugSelected()` → `selectDrug()` (card highlight) + `showDrugModal()` (B6 modal open + B9 genealogy tree) |
| **Current Problem** | None after T2 fix. Card click routes through SelectionStore. |
| **Target Boundaries** | B6 (Drug Modal), B9 (Genealogy Tree) |

#### A2: Click body region

| Property | Value |
|----------|-------|
| **Action** | User clicks an SVG body region on the atlas |
| **Canonical Path** | `selectionStore.setSelectedRegion(regionId, meta)` → `'region:selected'` event → `handleRegionSelected()` → clears disease if region changed → B2 (body map) + B5 (region label) + B4 (filter chips) + B1 (drug grid) + B8 (disease view) |
| **Current Problem** | `handleRegionSelected()` triggers the full `applyFilters()` cascade (B2 + B1), meaning body map (B2) runs redundantly after its own explicit `updateBodyMapState()` call. See Section 7.2 Chain 3. |
| **Target Boundaries** | B2, B4, B5, B1, B8 (but B2 should NOT run via `applyFilters()`) |

#### A3: Click ATC tag

| Property | Value |
|----------|-------|
| **Action** | User clicks an ATC category tag |
| **Canonical Path** | `filterByCategory()` → `toggleCategory()` → `this.activeCategory = new` → B3 (ATC tags) + B4 (filter chips) + B1 (drug grid) via `applyFilters()` |
| **Current Problem** | ATC category is set directly on `this.activeCategory` without going through SelectionStore. No event emitted. Downstream renders are correct but there is no audit trail. |
| **Target Boundaries** | B3, B4, B1 |

#### A4: Type in search input

| Property | Value |
|----------|-------|
| **Action** | User types in the search box |
| **Canonical Path** | Input event handler → `this.searchQuery = value` → B4 (filter chips) + B1 (drug grid) via `applyFilters()` |
| **Current Problem** | Search query is set directly on `this.searchQuery` without going through SelectionStore. No event emitted. `applyFilters()` cascade includes B2 (body map) which is unnecessary for text search. See Section 7.2 Chain 1. |
| **Target Boundaries** | B4, B1 (NOT B2 — body map doesn't change on search) |

#### A5: Select disease (from panel)

| Property | Value |
|----------|-------|
| **Action** | User selects a disease from the disease panel dropdown |
| **Canonical Path** | `selectionStore.setSelectedDisease(id, disease)` → `'disease:selected'` event → `handleDiseaseSelected()` → resets `activeCategory` to "all" → B7 (disease panel) + B2 partial (disease highlights) + B3 (ATC tags) + B4 (filter chips) + B1 (drug grid via `applyFilters()`) + B8 (disease view) |
| **Current Problem** | `applyFilters()` cascade includes B2 body map update which is unnecessary for disease selection (disease doesn't change category/region filter). ATC tags are reset even if already "all". |
| **Target Boundaries** | B7, B2 (partial — highlights only), B4, B1, B8 (NOT B3 if already "all") |

#### A6: Remove disease filter chip

| Property | Value |
|----------|-------|
| **Action** | User clicks the ✕ on the disease chip in the filter bar |
| **Canonical Path** | Chip `onRemove` → `selectionStore.setSelectedDisease(null, null)` → `'disease:selected'` event → `handleDiseaseSelected()` → same cascade as A5 |
| **Current Problem** | Same as A5. Currently correct after T2 fix. |
| **Target Boundaries** | Same as A5 |

#### A7: Remove ATC filter chip

| Property | Value |
|----------|-------|
| **Action** | User clicks the ✕ on the ATC category chip |
| **Canonical Path** | Chip `onRemove` → `this.activeCategory = "all"` → B3 (ATC tags) + B4 (filter chips) + B1 (drug grid) |
| **Current Problem** | Mutation is direct (no store event). No audit trail. Correct render result. |
| **Target Boundaries** | B3, B4, B1 |

#### A8: Remove search chip

| Property | Value |
|----------|-------|
| **Action** | User clicks the ✕ on the search chip in the filter bar |
| **Canonical Path** | Chip `onRemove` → `this.searchQuery = ""` → clear search input → B4 (filter chips) + B1 (drug grid) |
| **Current Problem** | Mutation is direct (no store event). Correct render result. |
| **Target Boundaries** | B4, B1 |

#### A9: Remove region filter chip

| Property | Value |
|----------|-------|
| **Action** | User clicks the ✕ on the body region chip in the filter bar |
| **Canonical Path** | Chip `onRemove` → `selectionStore.setSelectedRegion(null, null)` → `'region:selected'` event → `handleRegionSelected()` → full cascade |
| **Current Problem** | Same as A2 (double B2 call). Otherwise correct after T2 fix. |
| **Target Boundaries** | B2, B4, B5, B1, B8 (single B2) |

#### A10: Click Clear All button

| Property | Value |
|----------|-------|
| **Action** | User clicks the "Clear" button in the topbar |
| **Canonical Path** | `clearFilters()` → `selectionStore.clear()` → `'selection:cleared'` event → `handleSelectionCleared()` → resets all state → B2 (clear highlights) + B7 (disease panel) + B5 (region label) + B4 (filter chips) + B1 (drug grid) + B8 (disease view) |
| **Current Problem** | **Double cascade**: `clearFilters()` calls B3, B4, B1, B5, B8 directly BEFORE calling `SelectionStore.clear()`, which triggers `handleSelectionCleared()` that calls the SAME five boundaries again. See Section 7.2 Chain 4. Every clear action double-renders 5 boundaries. |
| **Target Boundaries** | B2, B7, B5, B4, B1, B8 (each once only) |

#### A11: Switch view mode (genealogy ↔ disease)

| Property | Value |
|----------|-------|
| **Action** | User clicks the Genealogy or Disease view toggle button |
| **Canonical Path** | `setViewMode(mode)` → idempotent guard (skip if same) → `selectionStore.setViewMode(mode)` → `'view:changed'` event → `handleViewChanged()` → idempotent guard (skip if same) → `_applyViewModeUI(mode)` → B10 (section toggle) + B8 (disease view if switching to disease) |
| **Current Problem** | Correct after T3 fix (idempotent guards broke the infinite loop). |
| **Target Boundaries** | B10, B8 (conditional) |

#### A12: Switch display mode (public ↔ scientist)

| Property | Value |
|----------|-------|
| **Action** | User clicks the Public or Scientist mode button |
| **Canonical Path** | `switchMode(mode)` → `this.mode = mode` → body class toggle → B1 (drug grid) → B6 (re-render modal if open) |
| **Current Problem** | Mode is set directly on `this.mode` without store event. `renderDrugList()` rebuilds entire grid just to toggle card metadata visibility — should be CSS-only (card classes already respond to `mode-scientist` body class). Modal re-render via `showDrugModal()` is wasteful. |
| **Target Boundaries** | B1 (CSS toggle only), B6 (CSS toggle only if open) |

#### A13: Open drug modal

| Property | Value |
|----------|-------|
| **Action** | User action that triggers `handleDrugSelected()` (see A1) |
| **Canonical Path** | (same as A1 — opening modal is part of the drug selection flow) |
| **Current Problem** | None. Modal is correctly rendered as one-shot. |
| **Target Boundaries** | B6, B9 |

#### A14: Close drug modal

| Property | Value |
|----------|-------|
| **Action** | User clicks modal overlay, close button, or presses Escape |
| **Canonical Path** | Overlay click → `closeModal()`. Close button → `closeModal()`. Escape → `closeModal()` + `clearTransientPreviews()`. |
| **Current Problem** | None. Modal close is self-contained. |
| **Target Boundaries** | B6 (remove `.active` class) |

### 9.2 Direct State Mutation Exceptions

Every location in `app.js` where state is mutated without going through SelectionStore:

| # | Location | Method | Line | State Mutated | Status | Risk |
|---|----------|--------|------|---------------|--------|------|
| D1 | `filterByCategory()` | L804-809 | `this.activeCategory` | **To fix** — should route through store or emit event | Medium | Breaks audit trail for ATC changes |
| D2 | `setupSearch()` input handler | L619-622 | `this.searchQuery` | **To fix** — should route through store or emit event | Medium | Breaks audit trail for search changes |
| D3 | `switchMode()` | L834-847 | `this.mode` | **To fix** — should route through store or emit event | Low | Display mode is not currently tracked by any consumer |
| D4 | `clearFilters()` pre-store calls | L811-813 | `this.activeCategory`, `this.hoveredRegion`, `this.searchQuery` | **To fix** — these three mutations should happen inside `handleSelectionCleared()` only (eliminates double cascade) | High | Causes Section 7.2 Chain 4 double-render |
| D5 | `clearFilters()` search input clear | L816-818 | `searchInput.value = ""` | **Acceptable** — DOM sync for input element | None | Input must reflect empty state immediately |
| D6 | `handleBodyRegionClick()` fallback | L724-742 | `this.activeDisease`, `this.activeBodyRegion`, `this.hoveredRegion` | **Legacy guard** — only runs when `selectionStore` is null (should never happen after init) | Low | Dead code path; SelectionStore is always initialized |
| D7 | `updateActiveFiltersBar()` chip onRemove for ATC | L893-897 | `this.activeCategory` | **To fix** — should route through store | Low | Minor: causes correct render but no audit trail |
| D8 | `updateActiveFiltersBar()` chip onRemove for search | L905-912 | `this.searchQuery`, `searchInput.value` | **To fix** — should route through store | Low | Minor: causes correct render but no audit trail |
| D9 | `updateActiveFiltersBar()` chip onRemove for region | L920-923 | `selectionStore.setSelectedRegion(null, null)` | **Correct** — routes through store | None | Already compliant |

### 9.3 Key Architectural Changes

Priority-ordered list of changes needed to move from current broad rerenders to targeted event-driven renders:

**1. Decouple `updateBodyMapState()` from `applyFilters()` (HIGH)**
- `applyFilters()` currently calls `updateBodyMapState()` at L1046, meaning every search keystroke, disease selection, and ATC change triggers a 14-region O(n) body map recomputation.
- Remove the `updateBodyMapState()` call from `applyFilters()`.
- Call `updateBodyMapState()` explicitly only from: `handleRegionSelected()`, `handleDiseaseSelected()` (via highlight changes), `handleSelectionCleared()`, and `filterByCategory()`.
- Eliminates B2 from Chain 1 (search) and reduces B2 calls in Chain 2 (disease).

**2. Eliminate double-render cascade in `clearFilters()` (HIGH)**
- `clearFilters()` calls B3, B4, B1, B5, B8 directly, then `SelectionStore.clear()` triggers `handleSelectionCleared()` which calls the same 5 boundaries again.
- Move all state mutations (`activeCategory = "all"`, `hoveredRegion = null`, `searchQuery = ""`) into `handleSelectionCleared()` only.
- `clearFilters()` becomes a thin wrapper: reset search input, call `SelectionStore.clear()`.
- Eliminates 100% of redundant double-render in Chain 4.

**3. Add view-mode change guard to `applyFilters()` (MEDIUM)**
- `applyFilters()` always calls `renderDrugList()` regardless of whether the filter result actually changed.
- Add a shallow-equal check: if new `filteredDrugs` array is the same length as current and mode/disease/category/region haven't changed, skip `renderDrugList()`.
- Reduces unnecessary B1 grid rebuilds.

**4. Route ATC category and search through a FilterStore or SelectionStore (MEDIUM)**
- Currently `filterByCategory()` and `setupSearch()` directly mutate `this.activeCategory` and `this.searchQuery`.
- To enable audit trails and centralized state management, these should go through SelectionStore (which already emits events) or a dedicated FilterStore.
- This would convert A3 and A4 from direct mutations to event-driven paths.

**5. Make mode switch CSS-only (LOW)**
- `switchMode()` currently calls `renderDrugList()` which rebuilds the entire drug grid.
- Drug cards already respond to `body.mode-scientist` class via CSS. The grid rebuild is only needed to toggle metadata visibility.
- Replace with a body class toggle and let CSS handle the display mode change.
